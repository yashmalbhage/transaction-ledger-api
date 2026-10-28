import uuid


def test_create_account_starts_with_zero_balance(client):
    res = client.post("/accounts", json={"name": "Alice"})
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Alice"
    assert body["balance"] == "0.00"
    assert body["created_at"]
    uuid.UUID(body["id"])  # valid unique identifier


def test_account_ids_are_unique(client):
    ids = {client.post("/accounts", json={"name": f"u{i}"}).json()["id"] for i in range(5)}
    assert len(ids) == 5


def test_name_is_required(client):
    assert client.post("/accounts", json={}).status_code == 422
    assert client.post("/accounts", json={"name": "   "}).status_code == 422


def test_client_cannot_set_initial_balance(client):
    res = client.post("/accounts", json={"name": "Bob", "balance": 500})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def test_get_balance(client, account):
    res = client.get(f"/accounts/{account['id']}/balance")
    assert res.status_code == 200
    assert res.json() == {"account_id": account["id"], "balance": "0.00"}


def test_get_balance_unknown_account(client):
    res = client.get("/accounts/does-not-exist/balance")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "account_not_found"
