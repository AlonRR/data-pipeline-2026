import os
import unittest
from unittest.mock import patch

from shared.db import database_url, make_engine


class DatabaseUrlTest(unittest.TestCase):
    def test_strips_whitespace_from_secret(self):
        value = "postgresql+psycopg2://user:password@example.com:5432/postgres"
        with patch.dict(os.environ, {"DATABASE_URL": f"  {value}\n"}):
            self.assertEqual(database_url(), value)
            self.assertEqual(make_engine().url.render_as_string(hide_password=False), value)

    def test_encodes_raw_at_sign_in_password(self):
        raw = "postgresql+psycopg2://postgres.project:abc@6@pooler.example.com:6543/postgres?sslmode=require"
        with patch.dict(os.environ, {"DATABASE_URL": raw}):
            engine = make_engine()
        self.assertEqual(engine.url.username, "postgres.project")
        self.assertEqual(engine.url.password, "abc@6")
        self.assertEqual(engine.url.host, "pooler.example.com")

    def test_preserves_already_encoded_at_sign(self):
        encoded = "postgresql+psycopg2://postgres.project:abc%406@pooler.example.com:6543/postgres"
        with patch.dict(os.environ, {"DATABASE_URL": encoded}):
            engine = make_engine()
        self.assertEqual(engine.url.password, "abc@6")
        self.assertEqual(engine.url.host, "pooler.example.com")

    def test_rejects_empty_secret(self):
        with patch.dict(os.environ, {"DATABASE_URL": "  \n"}):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is empty"):
                database_url()

    def test_rejects_malformed_secret_without_echoing_it(self):
        secret = "not a database URL"
        with self.assertRaises(RuntimeError) as raised:
            make_engine(secret)
        self.assertNotIn(secret, str(raised.exception))

    def test_rejects_non_postgres_url(self):
        with self.assertRaisesRegex(RuntimeError, "must use PostgreSQL"):
            make_engine("sqlite:///local.db")


if __name__ == "__main__":
    unittest.main()
