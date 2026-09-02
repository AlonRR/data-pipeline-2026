"""DB engine/session setup shared by the loader and api services.

Expected env var: DATABASE_URL. Schema is created with ``create_all`` on
service startup; there is no migration tool yet, so changing a column on a
live database is a manual job (see README).
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker

from shared.models import Base

DEFAULT_DATABASE_URL = "postgresql+psycopg2://salim:salim@postgres:5432/salim"


def database_url() -> str:
    # GitHub secrets copied from dashboards occasionally include a leading space
    # or trailing newline. Neither is part of a valid SQLAlchemy URL.
    value = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    if not value:
        raise RuntimeError("DATABASE_URL is empty")
    return value


def make_engine(url: str | None = None) -> Engine:
    value = url.strip() if url is not None else database_url()
    try:
        parsed = make_url(value)
    except ArgumentError as exc:
        raise RuntimeError(
            "DATABASE_URL is not a valid SQLAlchemy connection URL; expected "
            "postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DATABASE"
        ) from exc
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("DATABASE_URL must use PostgreSQL")
    return create_engine(parsed, pool_pre_ping=True, future=True)


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
