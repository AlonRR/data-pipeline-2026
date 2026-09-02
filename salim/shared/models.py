"""SQLAlchemy models shared by the loader and api services.

``provider`` everywhere is the numeric ``ChainId`` the price-transparency XML
carries (e.g. ``7290027600007``), not a crawler name: it is what the extractor
emits, it never changes, and ``chains`` maps it to a name for display.
Chains number stores and internal items from 001, so every business key is
scoped by ``provider``.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    func,
    text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

MANUFACTURER_PENDING = "pending"
MANUFACTURER_RESOLVED = "resolved"
MANUFACTURER_UNKNOWN = "unknown"


class Chain(Base):
    __tablename__ = "chains"

    chain_id = Column(String(32), primary_key=True)
    name = Column(String(64), nullable=False)
    slug = Column(String(64), unique=True)


class Branch(Base):
    """Store metadata owned by a separate metadata pipeline, never by prices-q."""

    __tablename__ = "branches"

    chain_id = Column(String(32), primary_key=True)
    branch_id = Column(String(32), primary_key=True)
    name = Column(String(256))
    city = Column(String(128), index=True)
    address = Column(String(512))
    latitude = Column(Float)
    longitude = Column(Float)
    timezone = Column(String(64), nullable=False, server_default=text("'Asia/Jerusalem'"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    metadata_updated_at = Column(DateTime(timezone=True))

    __table_args__ = (ForeignKeyConstraint(["chain_id"], ["chains.chain_id"]),)


class BranchOpeningHour(Base):
    __tablename__ = "branch_opening_hours"

    chain_id = Column(String(32), primary_key=True)
    branch_id = Column(String(32), primary_key=True)
    weekday = Column(Integer, primary_key=True)  # ISO weekday: Monday=1, Sunday=7
    interval_index = Column(Integer, primary_key=True, server_default=text("0"))
    opens_at = Column(Time, nullable=False)
    closes_at = Column(Time, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["chain_id", "branch_id"], ["branches.chain_id", "branches.branch_id"], ondelete="CASCADE"),
    )


class BranchOpeningException(Base):
    __tablename__ = "branch_opening_exceptions"

    chain_id = Column(String(32), primary_key=True)
    branch_id = Column(String(32), primary_key=True)
    date = Column(Date, primary_key=True)
    interval_index = Column(Integer, primary_key=True, server_default=text("0"))
    is_closed = Column(Boolean, nullable=False, server_default=text("false"))
    opens_at = Column(Time)
    closes_at = Column(Time)
    reason = Column(String(256))

    __table_args__ = (
        ForeignKeyConstraint(["chain_id", "branch_id"], ["branches.chain_id", "branches.branch_id"], ondelete="CASCADE"),
    )


class CatalogProduct(Base):
    """Canonical cross-chain product used by product and basket APIs."""

    __tablename__ = "catalog_products"

    product_id = Column(String(160), primary_key=True)
    gtin = Column(String(32), unique=True)
    slug = Column(String(160), unique=True, index=True)
    display_name = Column(String(512))
    manufacturer = Column(String(256))
    source_update_time = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    alias = Column(String(160), primary_key=True)
    product_id = Column(String(160), nullable=False, index=True)

    __table_args__ = (ForeignKeyConstraint(["product_id"], ["catalog_products.product_id"], ondelete="CASCADE"),)


class Product(Base):
    """One chain SKU mapped to a canonical catalog product."""

    __tablename__ = "products"

    provider = Column(String(32), primary_key=True)
    item_code = Column(String(32), primary_key=True)
    catalog_product_id = Column(String(160), nullable=False, index=True)

    item_name = Column(String(512))
    # 1 = barcode item (comparable across chains), 0 = chain-internal code.
    item_type = Column(Integer)
    unit_quantity = Column(String(64))
    unit_of_measure = Column(String(64))
    quantity = Column(Numeric(12, 3))
    weighted = Column(Boolean)
    in_package = Column(Numeric(12, 3))

    manufacturer = Column(String(256))
    manufacturer_raw = Column(String(256))
    manufacturer_status = Column(
        String(16), nullable=False, default=MANUFACTURER_PENDING, server_default=text("'pending'")
    )
    manufacturer_attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    manufacturer_checked_at = Column(DateTime(timezone=True))

    # Source publication timestamp. This prevents an older queue message from
    # rolling slowly-changing product metadata back after a newer one arrived.
    source_update_time = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["catalog_product_id"], ["catalog_products.product_id"]),
        Index("ix_products_manufacturer_status", "manufacturer_status"),
    )


class Price(Base):
    """Current price of one SKU in one store; older publications never overwrite newer ones."""

    __tablename__ = "prices"

    provider = Column(String(32), primary_key=True)
    store_id = Column(String(32), primary_key=True)
    item_code = Column(String(32), primary_key=True)

    price = Column(Numeric(12, 2))
    update_time = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["provider", "item_code"], ["products.provider", "products.item_code"]),
    )


class PriceHistory(Base):
    """Append-only price observations; RabbitMQ redelivery is deduplicated by source time."""

    __tablename__ = "price_history"

    provider = Column(String(32), primary_key=True)
    store_id = Column(String(32), primary_key=True)
    item_code = Column(String(32), primary_key=True)
    update_time = Column(DateTime(timezone=True), primary_key=True)
    price = Column(Numeric(12, 2), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["provider", "item_code"], ["products.provider", "products.item_code"]),
        Index("ix_price_history_item_time", "item_code", "update_time"),
        Index("ix_price_history_branch_time", "provider", "store_id", "update_time"),
    )


class Promotion(Base):
    __tablename__ = "promotions"

    provider = Column(String(32), primary_key=True)
    store_id = Column(String(32), primary_key=True)
    promotion_id = Column(String(32), primary_key=True)

    description = Column(String(1024))
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    update_time = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_promotions_provider_store_end", "provider", "store_id", "end_time"),)


class PromotionItem(Base):
    """Deal terms per SKU; the whole set is replaced whenever its promotion is upserted."""

    __tablename__ = "promotion_items"

    provider = Column(String(32), primary_key=True)
    store_id = Column(String(32), primary_key=True)
    promotion_id = Column(String(32), primary_key=True)
    item_code = Column(String(32), primary_key=True)

    discount_type = Column(Integer)
    min_qty = Column(Numeric(12, 3))
    max_qty = Column(Numeric(12, 3))
    discount_price = Column(Numeric(12, 2))
    discounted_price_per_mida = Column(Numeric(12, 2))

    __table_args__ = (
        ForeignKeyConstraint(
            ["provider", "store_id", "promotion_id"],
            ["promotions.provider", "promotions.store_id", "promotions.promotion_id"],
            ondelete="CASCADE",
        ),
        Index("ix_promotion_items_item", "provider", "item_code"),
    )


class PromotionHistory(Base):
    __tablename__ = "promotion_history"

    provider = Column(String(32), primary_key=True)
    store_id = Column(String(32), primary_key=True)
    promotion_id = Column(String(32), primary_key=True)
    update_time = Column(DateTime(timezone=True), primary_key=True)
    description = Column(String(1024))
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    ingested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("ix_promotion_history_branch_time", "provider", "store_id", "update_time"),)


class PromotionItemHistory(Base):
    __tablename__ = "promotion_item_history"

    provider = Column(String(32), primary_key=True)
    store_id = Column(String(32), primary_key=True)
    promotion_id = Column(String(32), primary_key=True)
    update_time = Column(DateTime(timezone=True), primary_key=True)
    item_code = Column(String(32), primary_key=True)
    discount_type = Column(Integer)
    min_qty = Column(Numeric(12, 3))
    max_qty = Column(Numeric(12, 3))
    discount_price = Column(Numeric(12, 2))
    discounted_price_per_mida = Column(Numeric(12, 2))

    __table_args__ = (
        ForeignKeyConstraint(
            ["provider", "store_id", "promotion_id", "update_time"],
            [
                "promotion_history.provider",
                "promotion_history.store_id",
                "promotion_history.promotion_id",
                "promotion_history.update_time",
            ],
            ondelete="CASCADE",
        ),
        Index("ix_promotion_item_history_item", "provider", "item_code", "update_time"),
    )


class Manufacturer(Base):
    """Item name -> manufacturer, keyed on the normalized name so one answer serves every chain.

    ``source`` says who answered: ``dictionary`` rows are the seeded brand
    tokens (matched by whole-token containment), ``llm`` rows are answers the
    sweeper paid for (``model`` says which), ``manual`` rows are hand
    corrections that nothing overwrites. The XML's own ManufactureName is not
    cached here; it is kept per product in ``products.manufacturer_raw``.
    """

    __tablename__ = "manufacturers"

    normalized_name = Column(String(512), primary_key=True)
    manufacturer = Column(String(256))
    source = Column(String(16), nullable=False)
    model = Column(String(64))
    resolved_at = Column(DateTime(timezone=True), server_default=func.now())
