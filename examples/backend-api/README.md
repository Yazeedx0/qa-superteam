# Ledger

A small wallet-transfer API built with FastAPI and SQLite.

Users register, receive a wallet, deposit funds and send money to other
wallets. Each transfer carries a 1% fee (rounded up, minimum 1 cent) that is
paid by the sender and credited to a house wallet. Business rules live in
[`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md).

## Layout

```
ledger/
  app.py          application factory (create_app) and the ASGI `app`
  db.py           sqlite3 connection, schema, BEGIN IMMEDIATE transactions
  auth.py         password hashing, sessions, `current_user` dependency
  models.py       request/response schemas
  wallets.py      wallet queries and deposits
  transfers.py    transfers, fees and idempotency
  routers/        HTTP endpoints
tests/            pytest suite
docs/             product requirements
```

## Running

```bash
pip install -r requirements.txt
LEDGER_DB=./ledger.db uvicorn ledger.app:app --reload
```

`LEDGER_DB` defaults to `ledger.db` in the working directory. The schema and
the house account are created on startup. Interactive docs are served at
`http://127.0.0.1:8000/docs`.

## Testing

```bash
python3 -m pytest tests
```

Tests build a fresh app per test with `create_app(tmp_path / "t.db")`.

## API

| Method | Path                    | Auth | Description                                   |
|--------|-------------------------|------|-----------------------------------------------|
| POST   | `/auth/register`        | no   | `{email, password}` → `201 {user_id}`         |
| POST   | `/auth/login`           | no   | `{email, password}` → `200 {token}`           |
| GET    | `/wallets/me`           | yes  | The caller's wallet                           |
| GET    | `/wallets/{wallet_id}`  | yes  | A wallet the caller owns                      |
| POST   | `/wallets/me/deposit`   | yes  | `{amount_cents}` → updated wallet             |
| POST   | `/transfers`            | yes  | `{to_wallet_id, amount_cents, memo?}` → `201` |
| GET    | `/transfers`            | yes  | Transfers the caller sent or received         |
| GET    | `/transfers/{id}`       | yes  | A single transfer                             |

Authenticated endpoints expect `Authorization: Bearer <token>`.
`POST /transfers` accepts an optional `Idempotency-Key` header.

### Example

```bash
curl -s -X POST localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email": "alice@example.com", "password": "correct-horse"}'
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email": "alice@example.com", "password": "correct-horse"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -X POST localhost:8000/wallets/me/deposit -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"amount_cents": 5000}'
```
