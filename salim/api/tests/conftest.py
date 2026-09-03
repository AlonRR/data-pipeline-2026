from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

SALIM_ROOT = Path(__file__).resolve().parents[2]
if str(SALIM_ROOT) not in sys.path:
    sys.path.insert(0, str(SALIM_ROOT))

from api.main import app
from shared.db import get_db
from shared.models import Base, Branch, Chain


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    database_path = tmp_path / "stores-test.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    Base.metadata.create_all(engine)

    with TestingSessionLocal() as session:
        seed_data(session)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def seed_data(session: Session) -> None:
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
