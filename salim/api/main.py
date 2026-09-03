from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from api.schemas import StoreDetailOut, StoreListOut
from shared.db import get_db
from shared.models import Branch, Chain

app = FastAPI(title="Salim Price API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stores", response_model=StoreListOut)
async def list_stores(
    chain_id: str | None = None,
    slug: str | None = None,
    name: str | None = None,
    city: str | None = None,
    branch_name: Annotated[str | None, Query(alias="branchName")] = None,
    is_active: Annotated[bool | None, Query(alias="isActive")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> StoreListOut:
    filters = []
    needs_branch_join = False

    if chain_id:
        filters.append(Chain.chain_id == chain_id)
    if slug:
        filters.append(Chain.slug == slug)
    if name:
        filters.append(Chain.name.ilike(f"%{name}%"))
    if city:
        filters.append(Branch.city.ilike(f"%{city}%"))
        needs_branch_join = True
    if branch_name:
        filters.append(Branch.name.ilike(f"%{branch_name}%"))
        needs_branch_join = True
    if is_active is not None:
        filters.append(Branch.is_active == is_active)
        needs_branch_join = True

    items_stmt = select(Chain)
    if needs_branch_join:
        items_stmt = items_stmt.join(Branch, Branch.chain_id == Chain.chain_id)

    if filters:
        items_stmt = items_stmt.where(*filters)

    items_stmt = (
        items_stmt.distinct()
        .order_by(Chain.name.asc(), Chain.chain_id.asc())
        .offset(offset)
        .limit(limit)
    )

    if needs_branch_join:
        total_stmt = (
            select(func.count(func.distinct(Chain.chain_id)))
            .select_from(Chain)
            .join(Branch, Branch.chain_id == Chain.chain_id)
        )
    else:
        total_stmt = select(func.count()).select_from(Chain)

    if filters:
        total_stmt = total_stmt.where(*filters)

    items = db.execute(items_stmt).scalars().all()
    total = db.scalar(total_stmt) or 0

    return StoreListOut(items=items, total=total, limit=limit, offset=offset)


@app.get(
    "/stores/{store_id}",
    response_model=StoreDetailOut,
    responses={404: {"description": "Store not found"}},
)
async def get_store(store_id: str, db: Session = Depends(get_db)) -> StoreDetailOut:
    stmt = (
        select(Chain)
        .options(selectinload(Chain.branches))
        .where(Chain.chain_id == store_id)
    )
    store = db.execute(stmt).scalar_one_or_none()

    if store is None:
        raise HTTPException(status_code=404, detail=f"Store '{store_id}' not found")

    return StoreDetailOut.model_validate(store)
