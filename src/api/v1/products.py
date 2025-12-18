"""Product endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.api.deps import (
    get_current_user,
    get_current_superuser,
    get_current_tenant_admin,
)
from src.db.repositories.product_repo import ProductRepository, ProductCategoryRepository
from src.models.module import Module, TenantModule
from src.models.product import TenantProduct, Product
from src.models.tenant import Tenant
from src.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductVisibilityUpdate,
    PlatformProductCreate,
    PlatformProductUpdate,
    ProductSyncUpdate,
)
from src.schemas.document import (
    DocumentUploadResponse,
    ProductDocumentSummary,
    ProductDocumentList,
)
from src.services.document_service import DocumentService
from src.services.storage.local import LocalStorageBackend

router = APIRouter()


def _build_product_response(
    product,
    tenant_product: Optional[TenantProduct] = None,
    synced_tenant_ids: Optional[list[str]] = None,
) -> ProductResponse:
    """Build product response with joined fields.

    Args:
        product: The Product model instance
        tenant_product: Optional TenantProduct for visibility override (platform products)
        synced_tenant_ids: Optional list of synced tenant IDs (for platform admin view)
    """
    # Determine effective visibility
    # For platform products with TenantProduct, use TenantProduct.is_visible
    # Otherwise use Product.is_visible
    effective_visibility = product.is_visible
    if tenant_product is not None:
        effective_visibility = tenant_product.is_visible

    return ProductResponse(
        id=product.id,
        module_id=product.module_id,
        tenant_id=product.tenant_id,
        category_id=product.category_id,
        code=product.code,
        name=product.name,
        name_zh=product.name_zh,
        description=product.description,
        description_zh=product.description_zh,
        category=product.category,
        risk_level=product.risk_level,
        min_investment=product.min_investment,
        currency=product.currency,
        expected_return=product.expected_return,
        is_visible=effective_visibility,
        is_default=product.is_default,
        is_unlocked_for_all=product.is_unlocked_for_all,
        extra_data=product.extra_data,
        created_at=product.created_at,
        updated_at=product.updated_at,
        module_code=product.module.code if product.module else None,
        module_name=product.module.name if product.module else None,
        category_name=product.category_rel.name if product.category_rel else None,
        synced_tenant_ids=synced_tenant_ids,
    )


# ============================================================================
# Product Listing Endpoints
# ============================================================================


@router.get("/", response_model=List[ProductResponse])
async def list_products(
    module_id: Optional[str] = Query(None, description="Filter by module ID"),
    module_code: Optional[str] = Query(None, description="Filter by module code"),
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    visible_only: bool = Query(True, description="Only show visible products"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[ProductResponse]:
    """List products available to the current user's tenant.

    Returns:
    - Platform products that are unlocked_for_all OR synced to this tenant
    - Tenant-specific products created by this tenant
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    # If module_code provided, resolve to module_id
    resolved_module_id = module_id
    if module_code and not module_id:
        query = select(Module).where(Module.code == module_code)
        result = await db.execute(query)
        module = result.scalar_one_or_none()
        if module:
            resolved_module_id = module.id

    repo = ProductRepository(db)
    product_tuples = await repo.get_products_for_tenant(
        tenant_id=tenant_id,
        module_id=resolved_module_id,
        category_id=category_id,
        risk_level=risk_level,
        visible_only=visible_only,
        skip=skip,
        limit=limit,
    )

    # product_tuples is a list of (Product, TenantProduct) tuples
    # Check if user is platform admin to include synced_tenant_ids
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )
    
    responses = []
    for p, tp in product_tuples:
        synced_ids = None
        # For platform products (tenant_id is None), include synced_tenant_ids for platform admins
        if is_platform_admin and p.tenant_id is None:
            synced_ids = await repo.get_synced_tenant_ids(p.id)
        responses.append(_build_product_response(p, tp, synced_tenant_ids=synced_ids))
    
    return responses


@router.get("/defaults", response_model=List[ProductResponse])
async def list_default_products(
    module_id: Optional[str] = Query(None, description="Filter by module ID"),
    visible_only: bool = Query(True, description="Only show visible products"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> List[ProductResponse]:
    """List all platform default products (platform admin only).

    Platform default products have tenant_id=NULL and is_default=True.
    Includes synced_tenant_ids for each product.
    """
    repo = ProductRepository(db)
    products = await repo.get_default_products(
        module_id=module_id,
        visible_only=visible_only,
    )

    # Build response with synced tenant IDs for each product
    responses = []
    for product in products:
        synced_ids = await repo.get_synced_tenant_ids(product.id)
        responses.append(_build_product_response(product, synced_tenant_ids=synced_ids))

    return responses


# ============================================================================
# Product CRUD Endpoints
# ============================================================================


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ProductResponse:
    """Get a specific product by ID.

    Access rules:
    - Tenant products: Only accessible by users from that tenant
    - Platform products: Only accessible if module is enabled AND product is synced/unlocked
    - Platform admins can access all products
    """
    tenant_id = current_user.get("tenant_id")
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )

    repo = ProductRepository(db)
    product = await repo.get_with_relations(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Platform admins can access everything
    if is_platform_admin:
        synced_ids = None
        if product.is_default:
            synced_ids = await repo.get_synced_tenant_ids(product.id)
        return _build_product_response(product, synced_tenant_ids=synced_ids)

    # For tenant products, check tenant ownership
    if product.tenant_id is not None:
        if product.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        return _build_product_response(product)

    # For platform products, check:
    # 1. Module is enabled for this tenant
    # 2. Product is unlocked_for_all OR synced to this tenant
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    # Check module is enabled for tenant
    module = product.module
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product module not found",
        )

    # Module must be active AND (core OR enabled for tenant)
    if not module.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Module is not active",
        )

    if not module.is_core:
        tm_query = select(TenantModule).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_id == module.id,
            TenantModule.is_enabled == True,
        )
        tm_result = await db.execute(tm_query)
        if not tm_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Module not enabled for this tenant",
            )

    # Check product is unlocked for this tenant
    if product.is_unlocked_for_all:
        # Check if tenant has visibility preference
        tenant_product = await repo.get_tenant_product(tenant_id, product_id)
        return _build_product_response(product, tenant_product)

    # Check if synced via TenantProduct
    tenant_product = await repo.get_tenant_product(tenant_id, product_id)
    if not tenant_product:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Product not available for this tenant",
        )

    return _build_product_response(product, tenant_product)


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ProductResponse:
    """Create a new tenant-specific product (tenant admin only).

    The product will be created with the current user's tenant_id and is_default=False.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    # Verify module exists
    module = await db.get(Module, product_in.module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    repo = ProductRepository(db)

    # Check if code already exists for this module and tenant
    existing = await repo.get_by_code(product_in.code, product_in.module_id, tenant_id)
    if existing and existing.tenant_id == tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product with code '{product_in.code}' already exists in this module",
        )

    # Validate category if provided
    if product_in.category_id:
        cat_repo = ProductCategoryRepository(db)
        category = await cat_repo.get(product_in.category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category not found",
            )

    # Create tenant-specific product
    product = await repo.create_tenant_product(product_in.model_dump(), tenant_id)
    await db.commit()

    # Reload with relations
    product = await repo.get_with_relations(product.id)
    return _build_product_response(product)


@router.post("/defaults", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_default_product(
    product_in: PlatformProductCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> ProductResponse:
    """Create a new platform default product (platform admin only).

    Platform admin chooses:
    - is_unlocked_for_all=True: Available to all tenants
    - is_unlocked_for_all=False + tenant_ids: Available only to specified tenants
    """
    # Verify module exists
    module = await db.get(Module, product_in.module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    repo = ProductRepository(db)

    # Check if code already exists as platform default for this module
    existing = await repo.get_by_code(product_in.code, product_in.module_id, tenant_id=None)
    if existing and existing.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Default product with code '{product_in.code}' already exists in this module",
        )

    # Validate tenant_ids if provided
    tenant_ids = product_in.tenant_ids or []
    if tenant_ids and not product_in.is_unlocked_for_all:
        for tid in tenant_ids:
            tenant = await db.get(Tenant, tid)
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tenant '{tid}' not found",
                )

    # Create platform default product
    product_data = product_in.model_dump(exclude={"tenant_ids"})
    product = await repo.create_default_product(product_data)

    # Sync to specified tenants (if not unlocked_for_all)
    if not product_in.is_unlocked_for_all and tenant_ids:
        await repo.sync_product_to_tenants(product.id, tenant_ids)

    await db.commit()

    # Reload with relations and get synced tenant IDs
    product = await repo.get_with_relations(product.id)
    synced_ids = await repo.get_synced_tenant_ids(product.id)
    return _build_product_response(product, synced_tenant_ids=synced_ids)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_in: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ProductResponse:
    """Update a product (tenant admin for tenant products, platform admin for defaults).

    Note: code and module_id cannot be changed after creation.
    """
    tenant_id = current_user.get("tenant_id")
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )

    repo = ProductRepository(db)
    product = await repo.get_with_relations(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Check permissions
    if product.tenant_id is None:
        # Platform default - only platform admins can update
        if not is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform admins can update default products",
            )
    else:
        # Tenant product - must belong to user's tenant
        if product.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    # Validate category if being updated
    if product_in.category_id:
        cat_repo = ProductCategoryRepository(db)
        category = await cat_repo.get(product_in.category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category not found",
            )

    # Update product
    update_data = product_in.model_dump(exclude_unset=True)
    product = await repo.update(product, update_data)
    await db.commit()

    # Reload with relations
    product = await repo.get_with_relations(product.id)
    return _build_product_response(product)


@router.patch("/{product_id}/visibility", response_model=ProductResponse)
async def update_product_visibility(
    product_id: str,
    visibility_in: ProductVisibilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ProductResponse:
    """Toggle product visibility (tenant admin only).

    For tenant-created products: Updates Product.is_visible directly.
    For platform products: Updates TenantProduct.is_visible for this tenant.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    repo = ProductRepository(db)
    product = await repo.get_with_relations(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Handle tenant-created products
    if product.tenant_id is not None:
        if product.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        # Update Product.is_visible directly
        product = await repo.toggle_visibility(product, visibility_in.is_visible)
        await db.commit()
        product = await repo.get_with_relations(product.id)
        return _build_product_response(product)

    # Handle platform products
    # Check if tenant has access (either unlocked_for_all or synced via TenantProduct)
    tenant_product = await repo.get_tenant_product(tenant_id, product_id)

    if product.is_unlocked_for_all:
        # For unlocked_for_all products, we need to create a TenantProduct record
        # to track this tenant's visibility preference
        if not tenant_product:
            # Create TenantProduct with the desired visibility
            await repo.sync_product_to_tenants(product_id, [tenant_id])
            tenant_product = await repo.get_tenant_product(tenant_id, product_id)

        tenant_product.is_visible = visibility_in.is_visible
        await db.commit()
        product = await repo.get_with_relations(product.id)
        return _build_product_response(product, tenant_product)

    # For synced products (not unlocked_for_all), must have TenantProduct record
    if not tenant_product:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Product not synced to this tenant",
        )

    tenant_product.is_visible = visibility_in.is_visible
    await db.commit()
    product = await repo.get_with_relations(product.id)
    return _build_product_response(product, tenant_product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Delete a product (tenant admin for tenant products, platform admin for defaults).

    Tenant admins cannot delete platform default products.
    """
    tenant_id = current_user.get("tenant_id")
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )

    repo = ProductRepository(db)
    product = await repo.get(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Check permissions
    if product.tenant_id is None:
        # Platform default - only platform admins can delete
        if not is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform admins can delete default products",
            )
    else:
        # Tenant product - must belong to user's tenant
        if product.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    await repo.delete(product)
    await db.commit()


# ============================================================================
# Platform Product Sync Endpoints
# ============================================================================


@router.patch("/{product_id}/sync", response_model=ProductResponse)
async def update_product_sync(
    product_id: str,
    sync_in: ProductSyncUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> ProductResponse:
    """Update sync settings for a platform product (platform admin only).

    Allows updating:
    - is_unlocked_for_all: If True, available to all tenants
    - tenant_ids: List of specific tenants to sync to (only used if is_unlocked_for_all=False)
    """
    repo = ProductRepository(db)
    product = await repo.get_with_relations(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Only platform products can have sync settings updated
    if product.tenant_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only platform products can have sync settings",
        )

    # Update is_unlocked_for_all if provided
    if sync_in.is_unlocked_for_all is not None:
        product.is_unlocked_for_all = sync_in.is_unlocked_for_all

    # Update tenant syncs if provided
    if sync_in.tenant_ids is not None:
        # Validate tenant IDs
        for tid in sync_in.tenant_ids:
            tenant = await db.get(Tenant, tid)
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tenant '{tid}' not found",
                )

        # Set the exact list of synced tenants
        await repo.set_synced_tenants(product_id, sync_in.tenant_ids)

    await db.commit()

    # Reload with relations and get synced tenant IDs
    product = await repo.get_with_relations(product.id)
    synced_ids = await repo.get_synced_tenant_ids(product.id)
    return _build_product_response(product, synced_tenant_ids=synced_ids)


# ============================================================================
# Product Document Endpoints
# ============================================================================


async def _get_product_for_documents(
    product_id: str,
    db: AsyncSession,
    current_user: dict,
    require_admin: bool = False,
) -> Product:
    """Helper to get product and verify access for document operations.
    
    Args:
        product_id: Product UUID
        db: Database session
        current_user: Current user dict
        require_admin: If True, require tenant_admin or platform_admin role
        
    Returns:
        Product model instance
        
    Raises:
        HTTPException: If product not found or access denied
    """
    tenant_id = current_user.get("tenant_id")
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )
    is_tenant_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin", "tenant_admin"]
    )
    
    if require_admin and not is_tenant_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    
    repo = ProductRepository(db)
    product = await repo.get_with_relations(product_id)
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    
    # Platform admins can access all products
    if is_platform_admin:
        return product
    
    # For tenant products, check tenant ownership
    if product.tenant_id is not None:
        if product.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        return product
    
    # For platform products, check if accessible to this tenant
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )
    
    # Check module is enabled for tenant
    module = product.module
    if not module or not module.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Module not active",
        )
    
    if not module.is_core:
        tm_query = select(TenantModule).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_id == module.id,
            TenantModule.is_enabled == True,
        )
        tm_result = await db.execute(tm_query)
        if not tm_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Module not enabled for this tenant",
            )
    
    # Check product is unlocked for this tenant
    if product.is_unlocked_for_all:
        return product
    
    tenant_product = await repo.get_tenant_product(tenant_id, product_id)
    if not tenant_product:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Product not available for this tenant",
        )
    
    return product


@router.get("/{product_id}/documents", response_model=ProductDocumentList)
async def list_product_documents(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ProductDocumentList:
    """List all documents for a product.
    
    Access follows product access rules - users who can view the product
    can also view its documents.
    """
    product = await _get_product_for_documents(product_id, db, current_user)
    
    # Get the tenant_id for the product (platform products use None)
    product_tenant_id = product.tenant_id
    
    doc_service = DocumentService(db)
    documents = await doc_service.get_product_documents(
        product_id=product_id,
        tenant_id=product_tenant_id,
    )
    
    return ProductDocumentList(
        documents=[
            ProductDocumentSummary(
                id=doc.id,
                name=doc.name,
                file_name=doc.file_name,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
                description=doc.description,
                created_at=doc.created_at,
                uploaded_by_id=doc.uploaded_by_id,
            )
            for doc in documents
        ],
        total_count=len(documents),
    )


@router.post(
    "/{product_id}/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_product_document(
    product_id: str,
    file: UploadFile = File(..., description="File to upload (PDF, Word, images)"),
    name: Optional[str] = Form(None, description="Display name (defaults to filename)"),
    description: Optional[str] = Form(None, description="Document description"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> DocumentUploadResponse:
    """Upload a document for a product.
    
    Requires tenant_admin role for tenant products, or platform_admin for platform products.
    Allowed file types: PDF, Word (.doc, .docx), Images (PNG, JPG, GIF, WebP)
    Maximum file size: 50MB
    """
    product = await _get_product_for_documents(
        product_id, db, current_user, require_admin=True
    )
    
    # Additional check: only platform admins can upload to platform products
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )
    
    if product.tenant_id is None and not is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can upload documents to platform products",
        )
    
    # Check file size before reading into memory (prevent memory attacks)
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 50MB limit",
        )
    
    # Read file content
    file_content = await file.read()
    
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )
    
    # Determine tenant_id for storage path and document record
    # For platform products, use the platform tenant (seeded in seed_admin.py)
    PLATFORM_TENANT_ID = "00000000-0000-0000-0000-000000000000"
    storage_tenant_id = product.tenant_id or PLATFORM_TENANT_ID
    
    doc_service = DocumentService(db)
    
    try:
        document = await doc_service.save_product_document(
            file_content=file_content,
            file_name=file.filename or "document",
            product_id=product_id,
            tenant_id=storage_tenant_id,
            document_name=name,
            description=description,
            uploaded_by_id=current_user.get("user_id"),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return DocumentUploadResponse(
        id=document.id,
        name=document.name,
        file_name=document.file_name,
        file_size=document.file_size,
        mime_type=document.mime_type,
        document_type=document.document_type.value,
        status=document.status.value,
        description=document.description,
        created_at=document.created_at,
        uploaded_by_id=document.uploaded_by_id,
    )


@router.get("/{product_id}/documents/{document_id}")
async def get_product_document(
    product_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ProductDocumentSummary:
    """Get details of a specific product document."""
    product = await _get_product_for_documents(product_id, db, current_user)
    
    doc_service = DocumentService(db)
    document = await doc_service.verify_product_access(document_id, product_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    return ProductDocumentSummary(
        id=document.id,
        name=document.name,
        file_name=document.file_name,
        file_size=document.file_size,
        mime_type=document.mime_type,
        description=document.description,
        created_at=document.created_at,
        uploaded_by_id=document.uploaded_by_id,
    )


@router.get("/{product_id}/documents/{document_id}/download")
async def download_product_document(
    product_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Download a product document.
    
    For local storage: Returns the file directly.
    For S3 storage: Redirects to a presigned URL.
    """
    product = await _get_product_for_documents(product_id, db, current_user)
    
    doc_service = DocumentService(db)
    document = await doc_service.verify_product_access(document_id, product_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    # Check if using local storage
    file_path = doc_service.get_file_path(document)
    
    if file_path:
        # Local storage - return file directly
        return FileResponse(
            path=str(file_path),
            filename=document.file_name,
            media_type=document.mime_type,
        )
    else:
        # S3 storage - redirect to presigned URL
        download_url = doc_service.get_download_url(document)
        return RedirectResponse(url=download_url, status_code=status.HTTP_302_FOUND)


@router.delete(
    "/{product_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product_document(
    product_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Delete a product document.
    
    Requires tenant_admin role for tenant products, or platform_admin for platform products.
    """
    product = await _get_product_for_documents(
        product_id, db, current_user, require_admin=True
    )
    
    # Additional check: only platform admins can delete from platform products
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )
    
    if product.tenant_id is None and not is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can delete documents from platform products",
        )
    
    doc_service = DocumentService(db)
    document = await doc_service.verify_product_access(document_id, product_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    await doc_service.delete_document(document)
