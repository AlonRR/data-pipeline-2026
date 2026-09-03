from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chain_id: str
    branch_id: str
    name: str | None
    city: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    timezone: str
    is_active: bool
    metadata_updated_at: datetime | None


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chain_id: str
    name: str
    slug: str | None


class StoreDetailOut(StoreOut):
    branches: list[BranchOut]


class StoreListOut(BaseModel):
    items: list[StoreOut]
    total: int
    limit: int
    offset: int
