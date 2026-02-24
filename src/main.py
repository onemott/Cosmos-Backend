"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from src.api.v1 import router as api_v1_router
from src.core.config import settings
from src.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    print(f"DEBUG: Loaded CORS Origins: {settings.cors_origins}")
    async with engine.begin() as connection:
        has_task_messages = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).has_table("task_messages")
        )
        enum_exists_result = await connection.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'taskmessageauthortype'")
        )
        has_message_author_enum = enum_exists_result.first() is not None
        if not has_message_author_enum:
            await connection.execute(
                text(
                    "CREATE TYPE taskmessageauthortype AS ENUM ('EAM','CLIENT','SYSTEM')"
                )
            )
    if not has_task_messages:
        raise RuntimeError(
            "Database migration required: task_messages table is missing. "
            "Run alembic upgrade head."
        )
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="EAM Wealth Platform API",
    description="External Asset Manager Wealth Platform Backend",
    version="0.1.0",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# Standard CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


# Include API routers
app.include_router(api_v1_router, prefix="/api/v1")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": "HTTP_ERROR"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "code": "VALIDATION_ERROR",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    # In production, log this error
    print(f"Database error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Database error", "code": "DB_ERROR"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # In production, log this error
    print(f"Generic error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
    )


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}
