"""API route tests: same Postgres fixture as test_repository.py, driven through TestClient."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from api.main import app
from api.deps import get_session
from shared.models import CatalogProduct, Chain, Price, Product, Promotion, PromotionItem
from api.tests.support import PostgresTestCase

NOW = datetime.now(timezone.utc)  # promotion windows are relative to real "now"


class ProductRoutesTest(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.sessions()
        self.session.add(Chain(chain_id="7290", name="שופרסל"))
        self.session.commit()

        def override_get_session():
            yield self.session

        app.dependency_overrides[get_session] = override_get_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.session.close()

    def _seed_product_with_price_and_promo(self):
        self.session.add(CatalogProduct(product_id="gtin:111", gtin="111", slug="milk-3", display_name="חלב תנובה 3%", manufacturer="תנובה"))
        self.session.add(Product(provider="7290", item_code="111", catalog_product_id="gtin:111", item_name="חלב תנובה 3%", item_type=1))
        self.session.flush()  # product must exist before price/promotion_items reference it
        self.session.add(Price(provider="7290", store_id="001", item_code="111", price=Decimal("6.90"), update_time=NOW))
        self.session.add(Promotion(provider="7290", store_id="001", promotion_id="p1", description="2 ב-20",
                                    start_time=NOW - timedelta(days=1), end_time=NOW + timedelta(days=1)))
        self.session.flush()  # promotion must exist before its items reference it
        self.session.add(PromotionItem(provider="7290", store_id="001", promotion_id="p1", item_code="111", discount_price=Decimal("20")))
        self.session.commit()

    def test_list_products(self):
        self._seed_product_with_price_and_promo()

        resp = self.client.get("/products")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["product_id"], "gtin:111")

    def test_list_products_filters_with_q(self):
        self._seed_product_with_price_and_promo()

        self.assertEqual(len(self.client.get("/products", params={"q": "חלב"}).json()), 1)
        self.assertEqual(len(self.client.get("/products", params={"q": "no-such-thing"}).json()), 0)

    def test_get_product_404_when_missing(self):
        resp = self.client.get("/products/gtin:does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_get_product_found(self):
        self._seed_product_with_price_and_promo()

        resp = self.client.get("/products/gtin:111")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["display_name"], "חלב תנובה 3%")

    def test_lowest_and_highest_prices(self):
        self._seed_product_with_price_and_promo()
        self.session.add(Price(provider="7290", store_id="002", item_code="111", price=Decimal("4.50"), update_time=NOW))
        self.session.commit()

        lowest = self.client.get("/products/gtin:111/prices/lowest", params={"limit": 10}).json()
        highest = self.client.get("/products/gtin:111/prices/highest", params={"limit": 10}).json()
        self.assertEqual([row["price"] for row in lowest], ["4.50", "6.90"])
        self.assertEqual([row["price"] for row in highest], ["6.90", "4.50"])

    def test_prices_404_for_unknown_product(self):
        resp = self.client.get("/products/gtin:missing/prices/lowest")
        self.assertEqual(resp.status_code, 404)

    def test_promotions_reports_has_promotion(self):
        self._seed_product_with_price_and_promo()

        resp = self.client.get("/products/gtin:111/promotions")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["has_promotion"])
        self.assertEqual(len(body["promotions"]), 1)
        self.assertEqual(body["promotions"][0]["items"][0]["item_code"], "111")

    def test_promotions_false_when_none(self):
        self.session.add(CatalogProduct(product_id="gtin:222", gtin="222", slug="s2", display_name="קוטג'"))
        self.session.flush()
        self.session.add(Product(provider="7290", item_code="222", catalog_product_id="gtin:222", item_name="קוטג'"))
        self.session.commit()

        resp = self.client.get("/products/gtin:222/promotions")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["has_promotion"])
        self.assertEqual(body["promotions"], [])

    def test_promotions_404_for_unknown_product(self):
        resp = self.client.get("/products/gtin:missing/promotions")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
