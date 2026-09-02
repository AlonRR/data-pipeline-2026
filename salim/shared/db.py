"""DB engine/session setup shared by the loader and api services.

Expected env var: DATABASE_URL. Schema is created with ``create_all`` on
service startup; there is no migration tool yet, so changing a column on a
live database is a manual job (see README).
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from shared.models import Base

DEFAULT_DATABASE_URL = "postgresql+psycopg2://salim:salim@postgres:5432/salim"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True, future=True)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    # Supabase exposes the public schema through its Data API. Keep every table
    # closed to API roles by default; this service writes through the privileged
    # Postgres connection and does not need an anon/authenticated RLS policy.
    with engine.begin() as connection:
        preparer = engine.dialect.identifier_preparer
        for table in Base.metadata.sorted_tables:
            table_name = preparer.quote(table.name)
            if table.schema:
                table_name = f"{preparer.quote_schema(table.schema)}.{table_name}"
            connection.exec_driver_sql(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
