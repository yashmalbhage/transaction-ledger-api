from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import init_db
from app.exceptions import register_exception_handlers
from app.routers import accounts


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "A simple transaction ledger: create accounts, post credit/debit transactions, "
        "and read balances and paginated history. Transactions are immutable."
    ),
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(accounts.router)


@app.get("/health", tags=["system"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}
