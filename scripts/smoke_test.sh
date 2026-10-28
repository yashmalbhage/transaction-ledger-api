#!/usr/bin/env bash
# Hits every endpoint of a running API with curl and prints the responses.
# Usage: ./scripts/smoke_test.sh [base_url]   (default http://127.0.0.1:8000)
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"

req() { # method path [json]
  echo; echo "### $1 $2 ${3:-}"
  if [ -n "${3:-}" ]; then
    curl -s -w '\n-> HTTP %{http_code}\n' -X "$1" "$BASE$2" -H 'Content-Type: application/json' -d "$3"
  else
    curl -s -w '\n-> HTTP %{http_code}\n' -X "$1" "$BASE$2"
  fi
}

req GET /health

echo; echo "### POST /accounts"
ACC=$(curl -s -X POST "$BASE/accounts" -H 'Content-Type: application/json' -d '{"name":"Alice"}')
echo "$ACC"; ID=$(echo "$ACC" | sed -E 's/.*"id":"([^"]+)".*/\1/')

req POST /accounts '{"name":"Bob","balance":500}'            # rejected: client cannot set balance
req POST /accounts '{}'                                      # rejected: name required

req POST "/accounts/$ID/transactions" '{"type":"credit","amount":100,"description":"Salary","reference_id":"ref-1"}'
req POST "/accounts/$ID/transactions" '{"type":"credit","amount":50,"description":"Bonus","reference_id":"ref-2"}'
req POST "/accounts/$ID/transactions" '{"type":"debit","amount":30,"description":"Groceries","reference_id":"ref-3"}'
req POST "/accounts/$ID/transactions" '{"type":"debit","amount":20,"description":"Coffee","reference_id":"ref-4"}'
req POST "/accounts/$ID/transactions" '{"type":"debit","amount":150,"description":"Too much","reference_id":"ref-5"}'  # insufficient
req POST "/accounts/$ID/transactions" '{"type":"credit","amount":100,"description":"Replay","reference_id":"ref-1"}'   # duplicate

req GET "/accounts/$ID/balance"                               # expect 100.00
req GET "/accounts/$ID/transactions"
req GET "/accounts/$ID/transactions?type=credit"
req GET "/accounts/$ID/transactions?type=debit&page=1&limit=1"
req GET "/accounts/$ID/transactions?page=2&limit=2"
req GET "/accounts/unknown/balance"                          # 404
req DELETE "/accounts/$ID/transactions"                      # 405: immutable
