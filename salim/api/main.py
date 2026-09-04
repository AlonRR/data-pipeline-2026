# FastAPI read API over the prices data.
# Expected env var: DATABASE_URL

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from api import repository as repo
from api.deps import get_session
from api.schemas import PriceOut, ProductOut, ProductPromotionsOut

app = FastAPI(title="Salim Price API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/products", response_model=list[ProductOut])
def list_products(
    q: str | None = Query(None, description="Search product name or slug"),
    manufacturer: str | None = Query(None, description="Exact manufacturer match (case-insensitive)"),
    has_promotion: bool | None = Query(None, description="Only products currently on promotion (true) or not (false)"),
    limit: int = Query(repo.DEFAULT_LIST_LIMIT, ge=1, le=repo.MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    return repo.list_products(
        session, q=q, manufacturer=manufacturer, has_promotion=has_promotion, limit=limit, offset=offset
    )


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: str, session: Session = Depends(get_session)):
    product = repo.get_product(session, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return product


@app.get("/products/{product_id}/prices/lowest", response_model=list[PriceOut])
def product_lowest_prices(
    product_id: str,
    limit: int = Query(repo.DEFAULT_PRICE_LIMIT, ge=1, le=repo.MAX_PRICE_LIMIT),
    session: Session = Depends(get_session),
):
    """The N cheapest current prices for this product, across every chain and store."""
    _require_product(session, product_id)
    return repo.product_prices(session, product_id, order="asc", limit=limit)


@app.get("/products/{product_id}/prices/highest", response_model=list[PriceOut])
def product_highest_prices(
    product_id: str,
    limit: int = Query(repo.DEFAULT_PRICE_LIMIT, ge=1, le=repo.MAX_PRICE_LIMIT),
    session: Session = Depends(get_session),
):
    """The N priciest current prices for this product, across every chain and store."""
    _require_product(session, product_id)
    return repo.product_prices(session, product_id, order="desc", limit=limit)


@app.get("/products/{product_id}/promotions", response_model=ProductPromotionsOut)
def product_promotions(
    product_id: str,
    active_only: bool = Query(True, description="Only currently active promotions"),
    session: Session = Depends(get_session),
):
    """Whether this product currently has a promotion, and the promotions themselves."""
    _require_product(session, product_id)
    promotions = repo.product_promotions(session, product_id, active_only=active_only)
    return {"has_promotion": len(promotions) > 0, "promotions": promotions}


def _require_product(session: Session, product_id: str) -> None:
    if repo.get_product(session, product_id) is None:
        raise HTTPException(status_code=404, detail="product not found")
