import unittest
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app, get_store, list_stores
from api.deps import get_session
from api.tests.support import PostgresTestCase
from shared.models import Branch, Chain


def seed_stores(session) -> None:
    session.add_all(
        [
            Chain(chain_id="7290027600007", name="Shufersal", slug="shufersal"),
            Chain(chain_id="7290058103393", name="Rami Levi", slug="rami-levi"),
        ]
    )
    session.add_all(
        [
            Branch(
                chain_id="7290027600007",
                branch_id="001",
                name="Hod Hasharon Downtown",
                city="Hod Hasharon",
                address="1 HaHarash St",
                latitude=32.1541,
                longitude=34.8935,
                timezone="Asia/Jerusalem",
                is_active=True,
                metadata_updated_at=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
            ),
            Branch(
                chain_id="7290027600007",
                branch_id="002",
                name="Dizengoff Center",
                city="Tel Aviv",
                address="50 Dizengoff St",
                latitude=32.074,
                longitude=34.774,
                timezone="Asia/Jerusalem",
                is_active=False,
                metadata_updated_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            ),
            Branch(
                chain_id="7290058103393",
                branch_id="010",
                name="Ganim",
                city="Hod Hasharon",
                address="8 HaBanim St",
                latitude=32.151,
                longitude=34.892,
                timezone="Asia/Jerusalem",
                is_active=True,
                metadata_updated_at=datetime(2026, 9, 2, 8, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()


class StoreRoutesTest(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.sessions()
        seed_stores(self.session)

        def override_get_session():
            yield self.session

        app.dependency_overrides[get_session] = override_get_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.session.close()

    def test_list_stores_http_returns_expected_shape(self):
        response = self.client.get("/stores", params={"limit": 1, "offset": 0})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
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
            },
        )

    def test_list_stores_http_filters_by_query_parameters(self):
        response = self.client.get("/stores", params={"city": "hod", "name": "shuf"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"],
            [
                {
                    "chain_id": "7290027600007",
                    "name": "Shufersal",
                    "slug": "shufersal",
                }
            ],
        )

    def test_list_stores_http_accepts_branch_name_alias(self):
        response = self.client.get("/stores", params={"branchName": "gan"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"],
            [
                {
                    "chain_id": "7290058103393",
                    "name": "Rami Levi",
                    "slug": "rami-levi",
                }
            ],
        )

    def test_list_stores_http_accepts_is_active_alias(self):
        response = self.client.get("/stores", params={"isActive": "false"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"],
            [
                {
                    "chain_id": "7290027600007",
                    "name": "Shufersal",
                    "slug": "shufersal",
                }
            ],
        )

    def test_get_store_http_includes_branches(self):
        response = self.client.get("/stores/7290027600007")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([branch["branch_id"] for branch in response.json()["branches"]], ["001", "002"])

    def test_get_store_http_returns_json_404(self):
        response = self.client.get("/stores/missing-store")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Store 'missing-store' not found"})

    def test_list_stores_returns_paginated_items(self):
        response = list_stores(limit=1, offset=0, session=self.session)

        self.assertEqual(response["total"], 2)
        self.assertEqual(response["limit"], 1)
        self.assertEqual(response["offset"], 0)
        self.assertEqual(
            [(store.chain_id, store.name, store.slug) for store in response["items"]],
            [("7290058103393", "Rami Levi", "rami-levi")],
        )

    def test_list_stores_filters_by_branch_fields(self):
        response = list_stores(
            city="hod",
            branch_name="gan",
            is_active=True,
            limit=50,
            offset=0,
            session=self.session,
        )

        self.assertEqual(
            [(store.chain_id, store.name, store.slug) for store in response["items"]],
            [("7290058103393", "Rami Levi", "rami-levi")],
        )

    def test_get_store_returns_store_detail(self):
        response = get_store("7290027600007", session=self.session)

        self.assertEqual(response.chain_id, "7290027600007")
        self.assertEqual(response.name, "Shufersal")
        self.assertEqual(response.slug, "shufersal")

    def test_get_store_includes_branches(self):
        response = get_store("7290027600007", session=self.session)

        self.assertEqual(
            [
                {
                    "chain_id": branch.chain_id,
                    "branch_id": branch.branch_id,
                    "name": branch.name,
                    "city": branch.city,
                    "address": branch.address,
                    "latitude": branch.latitude,
                    "longitude": branch.longitude,
                    "timezone": branch.timezone,
                    "is_active": branch.is_active,
                    "metadata_updated_at": branch.metadata_updated_at.isoformat() if branch.metadata_updated_at else None,
                }
                for branch in response.branches
            ],
            [
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
                    "metadata_updated_at": "2026-09-01T09:00:00+00:00",
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
                    "metadata_updated_at": "2026-09-01T10:00:00+00:00",
                },
            ],
        )

    def test_get_store_returns_404_for_missing_store(self):
        with self.assertRaises(HTTPException) as exc_info:
            get_store("missing-store", session=self.session)

        self.assertEqual(exc_info.exception.status_code, 404)
        self.assertEqual(exc_info.exception.detail, "Store 'missing-store' not found")


if __name__ == "__main__":
    unittest.main()
