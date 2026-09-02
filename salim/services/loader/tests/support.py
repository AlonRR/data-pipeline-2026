"""Shared Postgres fixture for the DB-backed tests.

Set TEST_DATABASE_URL to run them, e.g.
    TEST_DATABASE_URL=postgresql+psycopg2://salim:salim@localhost:5432/salim
They are skipped otherwise.
"""
import os
import unittest

from sqlalchemy import text

from shared.db import init_db, make_engine, make_session_factory
from shared.models import Base

URL = os.environ.get("TEST_DATABASE_URL")

_TABLES = (
    "promotion_item_history",
    "promotion_history",
    "promotion_items",
    "promotions",
    "price_history",
    "prices",
    "products",
    "product_aliases",
    "catalog_products",
    "manufacturers",
    "branch_opening_exceptions",
    "branch_opening_hours",
    "branches",
    "chains",
)


@unittest.skipUnless(URL, "TEST_DATABASE_URL not set")
class PostgresTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = make_engine(URL)
        Base.metadata.drop_all(cls.engine)
        init_db(cls.engine)
        cls.sessions = make_session_factory(cls.engine)

    def setUp(self):
        with self.engine.begin() as conn:
            for table in _TABLES:
                conn.execute(text(f"TRUNCATE {table} CASCADE"))
