from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models import Transaction


def post_tx(client, account_id, type_, amount, ref, description=None):
    return client.post(
        f"/accounts/{account_id}/transactions",
        json={"type": type_, "amount": amount, "reference_id": ref, "description": description},
    )


def balance(client, account_id) -> str:
    return client.get(f"/accounts/{account_id}/balance").json()["balance"]


# ----- credit / debit rules -------------------------------------------------

def test_credit_increases_balance(client, account):
    post_tx(client, account["id"], "credit", "100", "r1")
    res = post_tx(client, account["id"], "credit", "50", "r2")
    assert res.status_code == 201
    assert res.json()["balance_after"] == "150.00"
    assert balance(client, account["id"]) == "150.00"


def test_debit_decreases_balance(client, account):
    post_tx(client, account["id"], "credit", "100", "r1")
    res = post_tx(client, account["id"], "debit", "30", "r2")
    assert res.status_code == 201
    assert res.json()["balance_after"] == "70.00"
    assert balance(client, account["id"]) == "70.00"


def test_debit_rejected_when_insufficient_balance(client, account):
    post_tx(client, account["id"], "credit", "100", "r1")
    res = post_tx(client, account["id"], "debit", "150", "r2")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "insufficient_balance"
    assert balance(client, account["id"]) == "100.00"
    # the rejected transaction was not stored
    history = client.get(f"/accounts/{account['id']}/transactions").json()
    assert history["pagination"]["total_records"] == 1


def test_debit_on_empty_account_rejected(client, account):
    assert post_tx(client, account["id"], "debit", "1", "r1").status_code == 422
    assert balance(client, account["id"]) == "0.00"


def test_balance_consistency_example(client, account):
    for type_, amount, ref in [("credit", "100", "a"), ("credit", "50", "b"), ("debit", "30", "c"), ("debit", "20", "d")]:
        assert post_tx(client, account["id"], type_, amount, ref).status_code == 201
    assert balance(client, account["id"]) == "100.00"


def test_transaction_for_unknown_account(client):
    res = post_tx(client, "nope", "credit", "10", "r1")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "account_not_found"


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "credit", "amount": "0", "reference_id": "r"},
        {"type": "credit", "amount": "-5", "reference_id": "r"},
        {"type": "transfer", "amount": "5", "reference_id": "r"},
        {"type": "credit", "amount": "5"},
        {"type": "credit", "amount": "5", "reference_id": ""},
        {"type": "credit", "amount": "5.123", "reference_id": "r"},
        {"type": "credit", "amount": "abc", "reference_id": "r"},
    ],
)
def test_invalid_transaction_payloads(client, account, payload):
    res = client.post(f"/accounts/{account['id']}/transactions", json=payload)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"
    assert balance(client, account["id"]) == "0.00"


def test_response_contains_all_fields(client, account):
    body = post_tx(client, account["id"], "credit", "10.50", "inv-1", "Invoice 1").json()
    assert set(body) >= {"id", "account_id", "type", "amount", "description", "reference_id", "created_at"}
    assert body["account_id"] == account["id"]
    assert body["type"] == "credit"
    assert body["amount"] == "10.50"
    assert body["description"] == "Invoice 1"
    assert body["reference_id"] == "inv-1"


# ----- duplicates -----------------------------------------------------------

def test_duplicate_reference_rejected_without_changing_balance(client, account):
    first = post_tx(client, account["id"], "credit", "100", "dup")
    assert first.status_code == 201
    second = post_tx(client, account["id"], "credit", "100", "dup")
    assert second.status_code == 409
    err = second.json()["error"]
    assert err["code"] == "duplicate_transaction"
    assert err["existing_transaction_id"] == first.json()["id"]
    assert balance(client, account["id"]) == "100.00"
    history = client.get(f"/accounts/{account['id']}/transactions").json()
    assert history["pagination"]["total_records"] == 1


def test_duplicate_check_applies_even_if_type_or_amount_differ(client, account):
    post_tx(client, account["id"], "credit", "100", "dup")
    assert post_tx(client, account["id"], "debit", "5", "dup").status_code == 409
    assert balance(client, account["id"]) == "100.00"


def test_same_reference_allowed_for_different_accounts(client):
    a = client.post("/accounts", json={"name": "A"}).json()
    b = client.post("/accounts", json={"name": "B"}).json()
    assert post_tx(client, a["id"], "credit", "10", "shared").status_code == 201
    assert post_tx(client, b["id"], "credit", "20", "shared").status_code == 201
    assert balance(client, a["id"]) == "10.00"
    assert balance(client, b["id"]) == "20.00"


# ----- history: filtering, pagination, sorting --------------------------------

@pytest.fixture
def seeded(client, account):
    post_tx(client, account["id"], "credit", "100", "c1")
    post_tx(client, account["id"], "credit", "50", "c2")
    post_tx(client, account["id"], "debit", "30", "d1")
    post_tx(client, account["id"], "credit", "10", "c3")
    post_tx(client, account["id"], "debit", "20", "d2")
    return account


def test_history_returns_all_types_latest_first(client, seeded):
    res = client.get(f"/accounts/{seeded['id']}/transactions")
    assert res.status_code == 200
    body = res.json()
    refs = [t["reference_id"] for t in body["data"]]
    assert refs == ["d2", "c3", "d1", "c2", "c1"]
    timestamps = [t["created_at"] for t in body["data"]]
    assert timestamps == sorted(timestamps, reverse=True)
    assert body["pagination"] == {"page": 1, "limit": 10, "total_records": 5, "total_pages": 1}


def test_history_filter_by_type(client, seeded):
    credits = client.get(f"/accounts/{seeded['id']}/transactions", params={"type": "credit"}).json()
    assert [t["reference_id"] for t in credits["data"]] == ["c3", "c2", "c1"]
    assert all(t["type"] == "credit" for t in credits["data"])

    debits = client.get(f"/accounts/{seeded['id']}/transactions", params={"type": "debit"}).json()
    assert [t["reference_id"] for t in debits["data"]] == ["d2", "d1"]
    assert debits["pagination"]["total_records"] == 2


def test_history_invalid_type_filter(client, seeded):
    assert client.get(f"/accounts/{seeded['id']}/transactions", params={"type": "refund"}).status_code == 422


def test_history_pagination(client, seeded):
    url = f"/accounts/{seeded['id']}/transactions"
    p1 = client.get(url, params={"page": 1, "limit": 2}).json()
    p2 = client.get(url, params={"page": 2, "limit": 2}).json()
    p3 = client.get(url, params={"page": 3, "limit": 2}).json()
    p4 = client.get(url, params={"page": 4, "limit": 2}).json()

    assert p1["pagination"] == {"page": 1, "limit": 2, "total_records": 5, "total_pages": 3}
    assert [t["reference_id"] for t in p1["data"]] == ["d2", "c3"]
    assert [t["reference_id"] for t in p2["data"]] == ["d1", "c2"]
    assert [t["reference_id"] for t in p3["data"]] == ["c1"]
    assert p4["data"] == []  # past the end: empty page, same metadata
    assert p4["pagination"]["total_pages"] == 3


def test_history_empty_account(client, account):
    body = client.get(f"/accounts/{account['id']}/transactions").json()
    assert body["data"] == []
    assert body["pagination"] == {"page": 1, "limit": 10, "total_records": 0, "total_pages": 0}


def test_history_invalid_pagination_params(client, account):
    url = f"/accounts/{account['id']}/transactions"
    assert client.get(url, params={"page": 0}).status_code == 422
    assert client.get(url, params={"limit": 0}).status_code == 422
    assert client.get(url, params={"limit": 1000}).status_code == 422


def test_history_unknown_account(client):
    assert client.get("/accounts/missing/transactions").status_code == 404


# ----- immutability -----------------------------------------------------------

def test_no_update_or_delete_endpoints_for_transactions(client, account):
    tx = post_tx(client, account["id"], "credit", "10", "r1").json()
    url = f"/accounts/{account['id']}/transactions/{tx['id']}"
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(url).status_code in (404, 405)
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"/accounts/{account['id']}/transactions").status_code == 405
    assert balance(client, account["id"]) == "10.00"


def test_database_rejects_update_and_delete_of_transactions(client, account, db):
    tx = post_tx(client, account["id"], "credit", "10", "r1").json()
    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(text("UPDATE transactions SET amount = 999 WHERE id = :id"), {"id": tx["id"]})
    db.rollback()
    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(text("DELETE FROM transactions WHERE id = :id"), {"id": tx["id"]})
    db.rollback()
    row = db.get(Transaction, tx["id"])
    assert row is not None and row.amount == Decimal("10.00")


# ----- concurrency / consistency ----------------------------------------------

def test_concurrent_debits_never_overdraw(client, account):
    post_tx(client, account["id"], "credit", "100", "seed")

    def debit(i):
        return post_tx(client, account["id"], "debit", "30", f"con-{i}").status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(debit, range(10)))

    assert codes.count(201) == 3  # only three 30s fit into 100
    assert codes.count(422) == 7
    assert balance(client, account["id"]) == "10.00"


def test_concurrent_duplicate_submissions_create_one_transaction(client, account):
    def submit(_):
        return post_tx(client, account["id"], "credit", "10", "same-ref").status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(submit, range(8)))

    assert codes.count(201) == 1
    assert codes.count(409) == 7
    assert balance(client, account["id"]) == "10.00"


def test_balance_equals_sum_of_stored_transactions(client, seeded, db):
    rows = db.execute(
        text("SELECT type, amount FROM transactions WHERE account_id = :id"), {"id": seeded["id"]}
    ).all()
    expected = sum((r.amount if r.type == "credit" else -r.amount) for r in rows)
    assert Decimal(balance(client, seeded["id"])) == expected == Decimal("110.00")
