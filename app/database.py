from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine: Engine = create_engine(settings.database_url, echo=settings.sql_echo, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# Database-level guard for transaction immutability. Even if someone bypasses the API
# and talks to the DB directly, a ledger entry can never be edited or removed.
IMMUTABILITY_TRIGGERS = [
    """
    CREATE TRIGGER IF NOT EXISTS trg_transactions_no_update
    BEFORE UPDATE ON transactions
    FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Transactions are immutable and cannot be updated'
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_transactions_no_delete
    BEFORE DELETE ON transactions
    FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Transactions are immutable and cannot be deleted'
    """,
]


def init_db(target_engine: Engine = engine) -> None:
    """Create tables and immutability triggers if they do not exist yet."""
    # Import models so they are registered on Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=target_engine)
    with target_engine.begin() as conn:
        for ddl in IMMUTABILITY_TRIGGERS:
            conn.execute(text(ddl))


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing a request-scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
