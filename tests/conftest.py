"""Test fixtures. Tests run against a real MySQL database (`ledger_test`) so that
locks, unique constraints and immutability triggers are exercised for real."""

import os

os.environ.setdefault("DATABASE_URL", "mysql+pymysql://ledger:ledger@127.0.0.1:3308/ledger_test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    init_db(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Wipe data between tests. Triggers block DELETE on transactions, so use TRUNCATE
    with FK checks disabled (TRUNCATE does not fire row triggers)."""
    yield
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.execute(text("TRUNCATE TABLE transactions"))
        conn.execute(text("TRUNCATE TABLE accounts"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def account(client):
    return client.post("/accounts", json={"name": "Alice"}).json()
