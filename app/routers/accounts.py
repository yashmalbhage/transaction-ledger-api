from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TransactionType
from app.schemas import (
    AccountCreate,
    AccountResponse,
    BalanceResponse,
    ErrorResponse,
    PaginationMeta,
    TransactionCreate,
    TransactionCreatedResponse,
    TransactionListResponse,
)
from app.services import ledger

router = APIRouter(prefix="/accounts", tags=["accounts"])

AccountId = Annotated[str, Path(description="Account identifier (UUID)")]
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Account not found"}}


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create account",
    responses={422: {"model": ErrorResponse, "description": "Validation error"}},
)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> AccountResponse:
    """Create a new account. The initial balance is always 0 and cannot be set by the client."""
    return ledger.create_account(db, payload)


@router.get("/{account_id}", response_model=AccountResponse, summary="Get account", responses=NOT_FOUND)
def get_account(account_id: AccountId, db: Session = Depends(get_db)) -> AccountResponse:
    return ledger.get_account(db, account_id)


@router.get(
    "/{account_id}/balance",
    response_model=BalanceResponse,
    summary="Get account balance",
    responses=NOT_FOUND,
)
def get_balance(account_id: AccountId, db: Session = Depends(get_db)) -> BalanceResponse:
    account = ledger.get_account(db, account_id)
    return BalanceResponse(account_id=account.id, balance=account.balance)


@router.post(
    "/{account_id}/transactions",
    response_model=TransactionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add transaction",
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Duplicate reference_id for this account"},
        422: {"model": ErrorResponse, "description": "Insufficient balance or validation error"},
    },
)
def add_transaction(
    account_id: AccountId, payload: TransactionCreate, db: Session = Depends(get_db)
) -> TransactionCreatedResponse:
    """Credit or debit an account.

    - A debit exceeding the balance is rejected (422) and the balance is unchanged.
    - A repeated `reference_id` for the same account is rejected (409) and nothing is created.
    """
    return ledger.add_transaction(db, account_id, payload)


@router.get(
    "/{account_id}/transactions",
    response_model=TransactionListResponse,
    summary="Get transaction history",
    responses=NOT_FOUND,
)
def list_transactions(
    account_id: AccountId,
    db: Session = Depends(get_db),
    type: Annotated[TransactionType | None, Query(description="Filter by credit or debit")] = None,
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Records per page")] = 10,
) -> TransactionListResponse:
    """List an account's transactions, latest first, with optional type filter and pagination."""
    items, total, total_pages = ledger.list_transactions(
        db, account_id, type_filter=type, page=page, limit=limit
    )
    return TransactionListResponse(
        account_id=account_id,
        data=items,
        pagination=PaginationMeta(page=page, limit=limit, total_records=total, total_pages=total_pages),
    )
