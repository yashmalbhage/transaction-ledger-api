from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class LedgerError(Exception):
    """Base class for domain errors that map to a specific HTTP response."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "ledger_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AccountNotFound(LedgerError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "account_not_found"

    def __init__(self, account_id: str):
        super().__init__(f"Account '{account_id}' does not exist")


class InsufficientBalance(LedgerError):
    status_code = 422
    code = "insufficient_balance"


class DuplicateTransaction(LedgerError):
    status_code = status.HTTP_409_CONFLICT
    code = "duplicate_transaction"

    def __init__(self, reference_id: str, existing_transaction_id: str):
        super().__init__(
            f"A transaction with reference_id '{reference_id}' already exists for this account"
        )
        self.existing_transaction_id = existing_transaction_id


def _error_body(code: str, message: str, **extra: object) -> dict:
    return {"error": {"code": code, "message": message, **extra}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(LedgerError)
    async def ledger_error_handler(_: Request, exc: LedgerError) -> JSONResponse:
        extra = {}
        if isinstance(exc, DuplicateTransaction):
            extra["existing_transaction_id"] = exc.existing_transaction_id
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message, **extra))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body("validation_error", "Request validation failed", details=jsonable_encoder(exc.errors())),
        )
