# Pydantic response models for the API endpoints.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ProductOut(BaseModel):
    """A canonical, cross-chain product from ``catalog_products``."""

    model_config = ConfigDict(from_attributes=True)

    product_id: str
    gtin: str | None = None
    slug: str | None = None
    display_name: str | None = None
    manufacturer: str | None = None
    updated_at: datetime | None = None


class PriceOut(BaseModel):
    """One chain SKU's current price for a product, in one store."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    chain_name: str | None = None
    store_id: str
    item_name: str | None = None
    price: Decimal
    update_time: datetime | None = None


class PromotionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_code: str
    item_name: str | None = None
    discount_type: int | None = None
    min_qty: Decimal | None = None
    max_qty: Decimal | None = None
    discount_price: Decimal | None = None
    discounted_price_per_mida: Decimal | None = None


class PromotionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    chain_name: str | None = None
    store_id: str
    promotion_id: str
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    items: list[PromotionItemOut] = []


class ProductPromotionsOut(BaseModel):
    """Answers "does this product have promotions right now" plus the list itself."""

    has_promotion: bool
    promotions: list[PromotionOut]
