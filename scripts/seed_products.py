#!/usr/bin/env python3
"""Seed script to create default product categories and products.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_products.py
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.db.session import async_session_factory
from src.models.module import Module
from src.models.product import ProductCategory, Product


# ============================================================================
# Default Product Categories (Platform-level, tenant_id=NULL)
# ============================================================================

DEFAULT_CATEGORIES = [
    {
        "code": "equity",
        "name": "Equity",
        "name_zh": "股票",
        "description": "Stocks and equity investments",
        "icon": "TrendingUp",
        "sort_order": 1,
    },
    {
        "code": "fixed_income",
        "name": "Fixed Income",
        "name_zh": "固定收益",
        "description": "Bonds and fixed income securities",
        "icon": "Landmark",
        "sort_order": 2,
    },
    {
        "code": "alternatives",
        "name": "Alternatives",
        "name_zh": "另类投资",
        "description": "Alternative investments including PE, hedge funds, and real assets",
        "icon": "Layers",
        "sort_order": 3,
    },
    {
        "code": "real_estate",
        "name": "Real Estate",
        "name_zh": "房地产",
        "description": "Real estate and property investments",
        "icon": "Building",
        "sort_order": 4,
    },
    {
        "code": "insurance",
        "name": "Insurance",
        "name_zh": "保险",
        "description": "Insurance and protection products",
        "icon": "Shield",
        "sort_order": 5,
    },
    {
        "code": "structured",
        "name": "Structured Products",
        "name_zh": "结构化产品",
        "description": "Structured notes and complex financial instruments",
        "icon": "Network",
        "sort_order": 6,
    },
    {
        "code": "cash",
        "name": "Cash & Equivalents",
        "name_zh": "现金及等价物",
        "description": "Cash, money market, and short-term instruments",
        "icon": "Banknote",
        "sort_order": 7,
    },
]


# ============================================================================
# Default Products by Module (Platform-level, tenant_id=NULL, is_default=True)
# ============================================================================

DEFAULT_PRODUCTS = {
    "custom_portfolio": [
        {
            "code": "diversified_growth",
            "name": "Diversified Growth Portfolio",
            "name_zh": "多元化增长组合",
            "description": "A balanced mix of global equities and bonds designed for long-term growth",
            "description_zh": "全球股票和债券的平衡组合,旨在实现长期增长",
            "category": "Balanced",
            "risk_level": "balanced",
            "min_investment": Decimal("100000"),
            "currency": "USD",
            "expected_return": "6-8% annually",
            "extra_data": {"tags": ["diversified", "long-term", "global"]},
        },
        {
            "code": "income_focus",
            "name": "Income Focus Portfolio",
            "name_zh": "收益聚焦组合",
            "description": "Emphasis on dividend-paying stocks and high-yield bonds for steady income",
            "description_zh": "重点投资派息股票和高收益债券,以获取稳定收入",
            "category": "Fixed Income",
            "risk_level": "moderate",
            "min_investment": Decimal("50000"),
            "currency": "USD",
            "expected_return": "4-6% annually",
            "extra_data": {"tags": ["income", "dividends", "yield"]},
        },
        {
            "code": "capital_preservation",
            "name": "Capital Preservation Portfolio",
            "name_zh": "资本保全组合",
            "description": "Conservative approach prioritizing capital preservation over growth",
            "description_zh": "优先考虑资本保全而非增长的保守策略",
            "category": "Conservative",
            "risk_level": "conservative",
            "min_investment": Decimal("25000"),
            "currency": "USD",
            "expected_return": "2-4% annually",
            "extra_data": {"tags": ["conservative", "capital-preservation", "low-risk"]},
        },
    ],
    "eam_products": [
        {
            "code": "eam_equity_fund",
            "name": "EAM Global Equity Fund",
            "name_zh": "EAM全球股票基金",
            "description": "Actively managed global equity fund focused on quality growth stocks",
            "description_zh": "积极管理的全球股票基金,专注于优质成长股",
            "category": "Equity",
            "risk_level": "growth",
            "min_investment": Decimal("100000"),
            "currency": "USD",
            "expected_return": "8-12% annually",
            "extra_data": {"tags": ["equity", "growth", "global"]},
        },
        {
            "code": "eam_bond_fund",
            "name": "EAM Investment Grade Bond Fund",
            "name_zh": "EAM投资级债券基金",
            "description": "Diversified portfolio of investment-grade corporate and government bonds",
            "description_zh": "投资级公司债和政府债券的多元化组合",
            "category": "Fixed Income",
            "risk_level": "moderate",
            "min_investment": Decimal("50000"),
            "currency": "USD",
            "expected_return": "4-6% annually",
            "extra_data": {"tags": ["bonds", "fixed-income", "investment-grade"]},
        },
        {
            "code": "eam_balanced",
            "name": "EAM Balanced Strategy",
            "name_zh": "EAM平衡策略",
            "description": "Strategic allocation between equities and fixed income for optimal risk-adjusted returns",
            "description_zh": "股票和固定收益之间的战略配置,以获得最佳风险调整回报",
            "category": "Balanced",
            "risk_level": "balanced",
            "min_investment": Decimal("75000"),
            "currency": "USD",
            "expected_return": "5-8% annually",
            "extra_data": {"tags": ["balanced", "multi-asset"]},
        },
    ],
    "insurance_services": [
        {
            "code": "term_life",
            "name": "Term Life Insurance",
            "name_zh": "定期寿险",
            "description": "Affordable life insurance coverage for a specified term",
            "description_zh": "在指定期限内提供经济实惠的人寿保险保障",
            "category": "Insurance",
            "risk_level": "conservative",
            "min_investment": Decimal("1000"),
            "currency": "USD",
            "expected_return": "N/A - Protection product",
            "extra_data": {"tags": ["insurance", "term-life", "protection"]},
        },
        {
            "code": "whole_life",
            "name": "Whole Life Insurance",
            "name_zh": "终身寿险",
            "description": "Permanent life insurance with cash value accumulation",
            "description_zh": "具有现金价值累积功能的永久性人寿保险",
            "category": "Insurance",
            "risk_level": "conservative",
            "min_investment": Decimal("5000"),
            "currency": "USD",
            "expected_return": "2-3% cash value growth",
            "extra_data": {"tags": ["insurance", "whole-life", "cash-value"]},
        },
    ],
    "cd_solutions": [
        {
            "code": "short_term_cd",
            "name": "Short-Term CD (3-6 months)",
            "name_zh": "短期存单 (3-6个月)",
            "description": "Certificate of deposit with 3-6 month maturity",
            "description_zh": "3-6个月到期的定期存单",
            "category": "Cash",
            "risk_level": "conservative",
            "min_investment": Decimal("10000"),
            "currency": "USD",
            "expected_return": "3.5-4.0% APY",
            "extra_data": {"tags": ["cd", "short-term", "guaranteed"]},
        },
        {
            "code": "medium_term_cd",
            "name": "Medium-Term CD (1-2 years)",
            "name_zh": "中期存单 (1-2年)",
            "description": "Certificate of deposit with 1-2 year maturity",
            "description_zh": "1-2年到期的定期存单",
            "category": "Cash",
            "risk_level": "conservative",
            "min_investment": Decimal("25000"),
            "currency": "USD",
            "expected_return": "4.0-4.5% APY",
            "extra_data": {"tags": ["cd", "medium-term", "guaranteed"]},
        },
        {
            "code": "long_term_cd",
            "name": "Long-Term CD (3-5 years)",
            "name_zh": "长期存单 (3-5年)",
            "description": "Certificate of deposit with 3-5 year maturity for higher yield",
            "description_zh": "3-5年到期的定期存单,收益更高",
            "category": "Cash",
            "risk_level": "conservative",
            "min_investment": Decimal("50000"),
            "currency": "USD",
            "expected_return": "4.5-5.0% APY",
            "extra_data": {"tags": ["cd", "long-term", "guaranteed"]},
        },
    ],
    "alternative_investments": [
        {
            "code": "pe_fund",
            "name": "Private Equity Access Fund",
            "name_zh": "私募股权准入基金",
            "description": "Diversified access to top-tier private equity investments",
            "description_zh": "多元化投资顶级私募股权",
            "category": "Alternatives",
            "risk_level": "aggressive",
            "min_investment": Decimal("500000"),
            "currency": "USD",
            "expected_return": "15-20% target IRR",
            "extra_data": {"tags": ["pe", "private-equity", "alternatives"]},
        },
        {
            "code": "hedge_fund",
            "name": "Multi-Strategy Hedge Fund",
            "name_zh": "多策略对冲基金",
            "description": "Diversified hedge fund strategies for absolute returns",
            "description_zh": "多元化对冲基金策略,追求绝对收益",
            "category": "Alternatives",
            "risk_level": "growth",
            "min_investment": Decimal("250000"),
            "currency": "USD",
            "expected_return": "8-12% annually",
            "extra_data": {"tags": ["hedge-fund", "absolute-return", "alternatives"]},
        },
        {
            "code": "real_assets",
            "name": "Real Assets Fund",
            "name_zh": "实物资产基金",
            "description": "Infrastructure, commodities, and real estate investments",
            "description_zh": "基础设施、大宗商品和房地产投资",
            "category": "Alternatives",
            "risk_level": "balanced",
            "min_investment": Decimal("100000"),
            "currency": "USD",
            "expected_return": "6-10% annually",
            "extra_data": {"tags": ["real-assets", "infrastructure", "commodities"]},
        },
    ],
    "macro_analysis": [
        {
            "code": "global_macro",
            "name": "Global Macro Strategy",
            "name_zh": "全球宏观策略",
            "description": "Investment strategy based on macroeconomic analysis and global trends",
            "description_zh": "基于宏观经济分析和全球趋势的投资策略",
            "category": "Alternatives",
            "risk_level": "growth",
            "min_investment": Decimal("150000"),
            "currency": "USD",
            "expected_return": "8-15% annually",
            "extra_data": {"tags": ["macro", "global", "tactical"]},
        },
        {
            "code": "emerging_markets",
            "name": "Emerging Markets Opportunity",
            "name_zh": "新兴市场机遇",
            "description": "Focused exposure to high-growth emerging market economies",
            "description_zh": "专注投资于高增长新兴市场经济体",
            "category": "Equity",
            "risk_level": "aggressive",
            "min_investment": Decimal("75000"),
            "currency": "USD",
            "expected_return": "10-15% annually",
            "extra_data": {"tags": ["emerging-markets", "growth", "global"]},
        },
    ],
    "ai_recommendations": [
        {
            "code": "ai_balanced",
            "name": "AI-Optimized Balanced Portfolio",
            "name_zh": "AI优化平衡组合",
            "description": "Machine learning driven portfolio optimization for balanced risk-return",
            "description_zh": "机器学习驱动的投资组合优化,实现风险收益平衡",
            "category": "Balanced",
            "risk_level": "balanced",
            "min_investment": Decimal("50000"),
            "currency": "USD",
            "expected_return": "6-9% annually",
            "extra_data": {"tags": ["ai", "machine-learning", "optimized"]},
        },
        {
            "code": "ai_growth",
            "name": "AI Growth Seeker",
            "name_zh": "AI增长追求者",
            "description": "AI-powered stock selection targeting high-growth opportunities",
            "description_zh": "AI驱动的股票选择,瞄准高增长机会",
            "category": "Equity",
            "risk_level": "growth",
            "min_investment": Decimal("75000"),
            "currency": "USD",
            "expected_return": "10-15% annually",
            "extra_data": {"tags": ["ai", "growth", "equity"]},
        },
    ],
}


async def seed_categories():
    """Create or update default product categories."""
    async with async_session_factory() as session:
        created = 0
        updated = 0

        for cat_data in DEFAULT_CATEGORIES:
            # Check if category exists
            query = select(ProductCategory).where(
                ProductCategory.code == cat_data["code"],
                ProductCategory.tenant_id.is_(None),
            )
            result = await session.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing
                changed = False
                for key, value in cat_data.items():
                    if key == "code":
                        continue
                    if getattr(existing, key) != value:
                        setattr(existing, key, value)
                        changed = True
                if changed:
                    updated += 1
                    print(f"  Updated category: {cat_data['code']}")
                else:
                    print(f"  Category exists: {cat_data['code']}")
            else:
                # Create new
                category = ProductCategory(**cat_data)
                category.tenant_id = None  # Platform default
                session.add(category)
                created += 1
                print(f"  Created category: {cat_data['code']}")

        await session.commit()
        return created, updated


async def seed_products():
    """Create or update default products."""
    async with async_session_factory() as session:
        created = 0
        updated = 0
        skipped = 0

        for module_code, products in DEFAULT_PRODUCTS.items():
            # Get module
            query = select(Module).where(Module.code == module_code)
            result = await session.execute(query)
            module = result.scalar_one_or_none()

            if not module:
                print(f"  ⚠️  Module not found: {module_code} - skipping products")
                skipped += len(products)
                continue

            print(f"\n  Module: {module_code}")

            for prod_data in products:
                # Check if product exists
                query = select(Product).where(
                    Product.code == prod_data["code"],
                    Product.module_id == module.id,
                    Product.tenant_id.is_(None),
                )
                result = await session.execute(query)
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing
                    changed = False
                    for key, value in prod_data.items():
                        if key == "code":
                            continue
                        if getattr(existing, key) != value:
                            setattr(existing, key, value)
                            changed = True
                    if changed:
                        updated += 1
                        print(f"    Updated: {prod_data['code']}")
                    else:
                        print(f"    Exists: {prod_data['code']}")
                else:
                    # Create new
                    product = Product(
                        module_id=module.id,
                        tenant_id=None,  # Platform default
                        is_default=True,
                        is_visible=True,
                        **prod_data,
                    )
                    session.add(product)
                    created += 1
                    print(f"    Created: {prod_data['code']}")

        await session.commit()
        return created, updated, skipped


async def main():
    """Main seed function."""
    print("=" * 60)
    print("Seeding Default Product Categories and Products")
    print("=" * 60)

    print("\n📁 Seeding Categories...")
    cat_created, cat_updated = await seed_categories()

    print("\n📦 Seeding Products...")
    prod_created, prod_updated, prod_skipped = await seed_products()

    print("\n" + "=" * 60)
    print("Seeding Complete!")
    print("=" * 60)
    print(f"\nCategories: {cat_created} created, {cat_updated} updated")
    print(f"Products: {prod_created} created, {prod_updated} updated, {prod_skipped} skipped")

    total_products = sum(len(products) for products in DEFAULT_PRODUCTS.values())
    print(f"\nTotal defined: {len(DEFAULT_CATEGORIES)} categories, {total_products} products")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
