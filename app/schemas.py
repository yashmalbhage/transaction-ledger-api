from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models import TransactionType

Money = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2, examples=["100.00"])]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class UTCTimestampMixin(BaseModel):
    """MySQL stores created_at as a naive UTC DATETIME; expose it as timezone-aware UTC."""

    @field_validator("created_at", check_fields=False)
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# ----- Accounts -------------------------------------------------------------

class AccountCreate(BaseModel):
    """Only `name` is accepted. Any attempt to set `balance` is rejected (extra="forbid")."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[NonEmptyStr, StringConstraints(max_length=255)]


class AccountResponse(UTCTimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    balance: Decimal
    created_at: datetime


class BalanceResponse(BaseModel):
    account_id: str
    balance: Decimal


# ----- Transactions ---------------------------------------------------------

class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TransactionType
    amount: Money
    description: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None
    reference_id: Annotated[NonEmptyStr, StringConstraints(max_length=100)]


class TransactionResponse(UTCTimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    type: TransactionType
    amount: Decimal
    description: str | None
    reference_id: str
    created_at: datetime


class TransactionCreatedResponse(TransactionResponse):
    """Transaction plus the account balance after it was applied."""

    balance_after: Decimal


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total_records: int
    total_pages: int


class TransactionListResponse(BaseModel):
    account_id: str
    data: list[TransactionResponse]
    pagination: PaginationMeta


# ----- Errors ---------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
