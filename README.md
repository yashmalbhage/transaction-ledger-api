# Transaction Ledger API

A backend API for a simple transaction ledger: create accounts, post credit/debit
transactions, and read balances and paginated transaction history.

**Stack:** Python 3.12+ · FastAPI · SQLAlchemy 2 · MySQL 8 (Docker) · pytest

## Quick start

### 1. Start MySQL (Docker)

```bash
docker compose up -d db
```

This starts a `mysql:8` container (`ledger-mysql`) on `127.0.0.1:3308` with:

| Database      | Purpose              | User / password   |
|---------------|----------------------|-------------------|
| `ledger`      | application data     | `ledger / ledger` |
| `ledger_test` | automated test suite | `ledger / ledger` |

### 2. Install dependencies and run the API

```bash
python3 -m venv .venv            # or: uv venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # or: uv pip install -r requirements.txt
cp .env.example .env             # optional, defaults already point at the container
uvicorn app.main:app --reload
```

Tables and database triggers are created automatically on startup.

- API: http://127.0.0.1:8000
- Interactive docs (Swagger): http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

### Alternative: run everything in Docker

```bash
docker compose --profile full up --build
```

### 3. Run the tests

```bash
pytest            # 35 tests, run against the real MySQL `ledger_test` database
```

A curl-based smoke test that hits every endpoint of a running server:

```bash
./scripts/smoke_test.sh            # default http://127.0.0.1:8000
```

## Endpoints

| Method | Path                                   | Description                                    |
|--------|----------------------------------------|------------------------------------------------|
| POST   | `/accounts`                            | Create account (balance always starts at 0)    |
| GET    | `/accounts/{account_id}`               | Get account                                    |
| GET    | `/accounts/{account_id}/balance`       | Get current balance                            |
| POST   | `/accounts/{account_id}/transactions`  | Add a credit or debit transaction              |
| GET    | `/accounts/{account_id}/transactions`  | Transaction history (filter, paginate, sorted) |
| GET    | `/health`                              | Health check                                   |

There are intentionally **no** `PUT`/`PATCH`/`DELETE` endpoints for transactions.

### Create account — `POST /accounts`

```json
{ "name": "Alice" }
```

`201 Created`

```json
{
  "id": "1c0f7db7-e121-43f0-bde6-ef86a7ad2b69",
  "name": "Alice",
  "balance": "0.00",
  "created_at": "2026-10-28T18:33:42.728838Z"
}
```

- `name` is required and must be non-blank.
- Sending `balance` (or any other unknown field) is rejected with `422`.

### Add transaction — `POST /accounts/{account_id}/transactions`

```json
{ "type": "credit", "amount": 100, "description": "Salary", "reference_id": "ref-1" }
```

`201 Created` — the created transaction plus `balance_after`:

```json
{
  "id": "338f226d-0e01-431e-8f77-7ec491e12e59",
  "account_id": "1c0f7db7-e121-43f0-bde6-ef86a7ad2b69",
  "type": "credit",
  "amount": "100.00",
  "description": "Salary",
  "reference_id": "ref-1",
  "created_at": "2026-10-28T18:33:42.789260Z",
  "balance_after": "100.00"
}
```

| Situation                                           | Status | `error.code`            |
|-----------------------------------------------------|--------|-------------------------|
| Account does not exist                              | 404    | `account_not_found`     |
| Debit larger than current balance                   | 422    | `insufficient_balance`  |
| Same `reference_id` already used on this account    | 409    | `duplicate_transaction` |
| Invalid body (amount ≤ 0, bad type, missing fields) | 422    | `validation_error`      |

A duplicate response includes `existing_transaction_id` so the client can look up the
original. The same `reference_id` **may** be reused on a different account.

### Get balance — `GET /accounts/{account_id}/balance`

```json
{ "account_id": "1c0f7db7-e121-43f0-bde6-ef86a7ad2b69", "balance": "100.00" }
```

Unknown account → `404 account_not_found`.

### Transaction history — `GET /accounts/{account_id}/transactions`

Query parameters:

| Param   | Type                 | Default | Notes                         |
|---------|----------------------|---------|-------------------------------|
| `type`  | `credit` \| `debit`  | both    | Filter by transaction type    |
| `page`  | int ≥ 1              | 1       | 1-based page number           |
| `limit` | int 1–100            | 10      | Page size                     |

Results are always **latest first** (`created_at DESC`, with `id` as a tiebreaker).

```json
{
  "account_id": "1c0f7db7-…",
  "data": [ { "id": "…", "type": "debit", "amount": "20.00", "reference_id": "ref-4", "created_at": "…" } ],
  "pagination": { "page": 1, "limit": 10, "total_records": 4, "total_pages": 1 }
}
```

### Error format

All errors share one shape:

```json
{ "error": { "code": "insufficient_balance", "message": "Insufficient balance: current balance is 100.00, requested debit is 150" } }
```

## Design notes

### Data integrity

- **Atomic balance updates.** Adding a transaction locks the account row
  (`SELECT … FOR UPDATE`), checks the balance, inserts the transaction and updates the
  balance inside one database transaction. Either everything commits or nothing does, so a
  rejected or failed transaction can never change the balance.
- **Concurrency-safe.** Because the account row is locked, parallel debits on the same
  account are serialised and cannot overdraw it (covered by
  `test_concurrent_debits_never_overdraw`). Parallel identical submissions are also caught
  by the database unique constraint, so exactly one is created.
- **Duplicates.** `UNIQUE (account_id, reference_id)` enforces per-account uniqueness at the
  database level in addition to the application check.
- **Non-negative balance** and **positive amount** are enforced with `CHECK` constraints.
- **Money as `DECIMAL(18,2)`**, never floats, to avoid rounding errors.

### Transaction immutability

- The API exposes no update/delete routes for transactions (`405 Method Not Allowed`).
- MySQL `BEFORE UPDATE` / `BEFORE DELETE` triggers on the `transactions` table raise an
  error, so even direct SQL access cannot alter or remove a ledger entry
  (covered by `test_database_rejects_update_and_delete_of_transactions`).

### Timestamps

`created_at` is generated by the database (`CURRENT_TIMESTAMP(6)`, microsecond precision)
and returned as timezone-aware UTC ISO-8601.

## Project layout

```
app/
  main.py            FastAPI app, lifespan (schema init), router registration
  config.py          Settings (DATABASE_URL via env / .env)
  database.py        Engine, session, table + trigger creation
  models.py          SQLAlchemy models: Account, Transaction
  schemas.py         Pydantic request/response models
  exceptions.py      Domain errors and their HTTP mapping
  routers/accounts.py  HTTP endpoints
  services/ledger.py   Business rules (credit/debit/duplicate/pagination)
tests/               pytest suite (runs against MySQL `ledger_test`)
scripts/smoke_test.sh  curl walkthrough of every endpoint
docker-compose.yml   MySQL (+ optional API) containers
Dockerfile           API image
```

## Configuration

| Variable       | Default                                              |
|----------------|------------------------------------------------------|
| `DATABASE_URL` | `mysql+pymysql://ledger:ledger@127.0.0.1:3308/ledger` |
| `SQL_ECHO`     | `false`                                              |
# transaction-ledger-api
