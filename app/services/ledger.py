"""Business logic for the ledger. All balance changes go through here."""

import math
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions import AccountNotFound, DuplicateTransaction, InsufficientBalance
from app.models import Account, Transaction, TransactionType
from app.schemas import AccountCreate, TransactionCreate


def create_account(db: Session, payload: AccountCreate) -> Account:
    account = Account(name=payload.name, balance=Decimal("0.00"))
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def get_account(db: Session, account_id: str) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise AccountNotFound(account_id)
    return account


def _find_duplicate(db: Session, account_id: str, reference_id: str) -> Transaction | None:
    stmt = select(Transaction).where(
        Transaction.account_id == account_id, Transaction.reference_id == reference_id
    )
    return db.execute(stmt).scalar_one_or_none()


def add_transaction(db: Session, account_id: str, payload: TransactionCreate) -> Transaction:
    """Apply a credit/debit atomically.

    The account row is locked with SELECT ... FOR UPDATE so concurrent requests on the
    same account are serialised: two debits cannot both pass the balance check and
    overdraw the account. The transaction insert and balance update commit together,
    so the balance always equals the sum of stored transactions.
    """
    with db.begin():
        account = db.execute(
            select(Account).where(Account.id == account_id).with_for_update()
        ).scalar_one_or_none()
        if account is None:
            raise AccountNotFound(account_id)

        existing = _find_duplicate(db, account_id, payload.reference_id)
        if existing is not None:
            raise DuplicateTransaction(payload.reference_id, existing.id)

        if payload.type is TransactionType.debit:
            if account.balance < payload.amount:
                raise InsufficientBalance(
                    f"Insufficient balance: current balance is {account.balance}, "
                    f"requested debit is {payload.amount}"
                )
            account.balance -= payload.amount
        else:
            account.balance += payload.amount

        transaction = Transaction(
            account_id=account.id,
            type=payload.type,
            amount=payload.amount,
            description=payload.description,
            reference_id=payload.reference_id,
        )
        db.add(transaction)
        try:
            db.flush()
        except IntegrityError as exc:
            # Safety net for a race where two identical requests arrive at once; the
            # unique (account_id, reference_id) constraint guarantees only one wins.
            db.rollback()
            existing = _find_duplicate(db, account_id, payload.reference_id)
            if existing is not None:
                raise DuplicateTransaction(payload.reference_id, existing.id) from exc
            raise

    db.refresh(transaction)
    db.refresh(account)
    transaction.balance_after = account.balance  # type: ignore[attr-defined]
    return transaction


def list_transactions(
    db: Session,
    account_id: str,
    *,
    type_filter: TransactionType | None,
    page: int,
    limit: int,
) -> tuple[list[Transaction], int, int]:
    """Return (items, total_records, total_pages) for an account, latest first."""
    get_account(db, account_id)

    filters = [Transaction.account_id == account_id]
    if type_filter is not None:
        filters.append(Transaction.type == type_filter)

    total = db.execute(select(func.count()).select_from(Transaction).where(*filters)).scalar_one()
    total_pages = max(1, math.ceil(total / limit)) if total else 0

    items = (
        db.execute(
            select(Transaction)
            .where(*filters)
            # id as a tiebreaker keeps ordering deterministic for identical timestamps.
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(items), total, total_pages
