from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import get_store, list_stores


def test_list_stores_http_returns_expected_shape(client: TestClient) -> None:
    response = client.get("/stores", params={"limit": 1, "offset": 0})

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "chain_id": "7290058103393",
                "name": "Rami Levi",
                "slug": "rami-levi",
            }
        ],
        "total": 2,
        "limit": 1,
        "offset": 0,
    }


def test_list_stores_http_filters_by_query_parameters(client: TestClient) -> None:
    response = client.get("/stores", params={"city": "hod", "name": "shuf"})

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "chain_id": "7290027600007",
            "name": "Shufersal",
            "slug": "shufersal",
        }
    ]


def test_list_stores_http_accepts_branch_name_alias(client: TestClient) -> None:
    response = client.get("/stores", params={"branchName": "gan"})

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "chain_id": "7290058103393",
            "name": "Rami Levi",
            "slug": "rami-levi",
        }
    ]


def test_list_stores_http_accepts_is_active_alias(client: TestClient) -> None:
    response = client.get("/stores", params={"isActive": "false"})

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "chain_id": "7290027600007",
            "name": "Shufersal",
            "slug": "shufersal",
        }
    ]


def test_get_store_http_includes_branches(client: TestClient) -> None:
    response = client.get("/stores/7290027600007")

    assert response.status_code == 200
    assert [branch["branch_id"] for branch in response.json()["branches"]] == ["001", "002"]


def test_get_store_http_returns_json_404(client: TestClient) -> None:
    response = client.get("/stores/missing-store")

    assert response.status_code == 404
    assert response.json() == {"detail": "Store 'missing-store' not found"}


def test_list_stores_returns_paginated_items(db_session) -> None:
    response = asyncio.run(list_stores(limit=1, offset=0, db=db_session))

    assert response.model_dump() == {
        "items": [
            {
                "chain_id": "7290058103393",
                "name": "Rami Levi",
                "slug": "rami-levi",
            }
        ],
        "total": 2,
        "limit": 1,
        "offset": 0,
    }


def test_list_stores_filters_by_branch_fields(db_session) -> None:
    response = asyncio.run(
        list_stores(
            city="hod",
            branch_name="gan",
            is_active=True,
            limit=50,
            offset=0,
            db=db_session,
        )
    )

    assert response.model_dump()["items"] == [
        {
            "chain_id": "7290058103393",
            "name": "Rami Levi",
            "slug": "rami-levi",
        }
    ]


def test_get_store_returns_store_detail(db_session) -> None:
    response = asyncio.run(get_store("7290027600007", db=db_session))

    assert response.chain_id == "7290027600007"
    assert response.name == "Shufersal"
    assert response.slug == "shufersal"


def test_get_store_includes_branches(db_session) -> None:
    response = asyncio.run(get_store("7290027600007", db=db_session))

    assert response.model_dump(mode="json")["branches"] == [
        {
            "chain_id": "7290027600007",
            "branch_id": "001",
            "name": "Hod Hasharon Downtown",
            "city": "Hod Hasharon",
            "address": "1 HaHarash St",
            "latitude": 32.1541,
            "longitude": 34.8935,
            "timezone": "Asia/Jerusalem",
            "is_active": True,
            "metadata_updated_at": "2026-09-01T09:00:00",
        },
        {
            "chain_id": "7290027600007",
            "branch_id": "002",
            "name": "Dizengoff Center",
            "city": "Tel Aviv",
            "address": "50 Dizengoff St",
            "latitude": 32.074,
            "longitude": 34.774,
            "timezone": "Asia/Jerusalem",
            "is_active": False,
            "metadata_updated_at": "2026-09-01T10:00:00",
        },
    ]


def test_get_store_returns_404_for_missing_store(db_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_store("missing-store", db=db_session))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Store 'missing-store' not found"
