"""Data integrity: unique accounts, input limits, idempotency conflicts.

BA-3: test_email_uniqueness_is_case_insensitive, test_login_email_is_case_insensitive
"""

import pytest

PASSWORD = "qa-password-123"


def _register(client, email, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def test_email_uniqueness_is_case_insensitive(client):
    assert _register(client, "alice@example.com").status_code == 201

    r = _register(client, "Alice@Example.com")

    assert r.status_code == 409, (
        "'Alice@Example.com' registered as a second account although 'alice@example.com' "
        f"already exists (emails must be unique case-insensitively); got {r.status_code} {r.text}"
    )


def test_login_email_is_case_insensitive(client):
    assert _register(client, "Carol@Example.com").status_code == 201

    r = client.post("/auth/login", json={"email": "carol@example.com", "password": PASSWORD})

    assert r.status_code == 200, (
        "login with a different letter case of a registered email was rejected; "
        f"got {r.status_code} {r.text}"
    )


def test_exact_duplicate_email_conflict(client):
    assert _register(client, "dave@example.com").status_code == 201
    assert _register(client, "dave@example.com").status_code == 409


def test_password_minimum_length(client):
    assert _register(client, "short@example.com", password="1234567").status_code == 422
    assert _register(client, "ok@example.com", password="12345678").status_code == 201


def test_wrong_password_and_unknown_email_look_the_same(client):
    assert _register(client, "erin@example.com").status_code == 201
    wrong = client.post("/auth/login", json={"email": "erin@example.com", "password": "nope-nope"})
    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@pytest.mark.parametrize("amount, status", [(1_000_000, 200), (1_000_001, 422), (0, 422), (-1, 422)])
def test_deposit_limits(client, new_user, balance_of, amount, status):
    user = new_user()
    r = client.post("/wallets/me/deposit", json={"amount_cents": amount}, headers=user.headers)
    assert r.status_code == status
    assert balance_of(user) == (amount if status == 200 else 0)


@pytest.mark.parametrize("memo_length, status", [(140, 201), (141, 422)])
def test_memo_max_length(client, new_user, memo_length, status):
    alice = new_user(balance=1_000)
    bob = new_user()
    r = client.post(
        "/transfers",
        json={"to_wallet_id": bob.wallet_id, "amount_cents": 10, "memo": "m" * memo_length},
        headers=alice.headers,
    )
    assert r.status_code == status


def test_idempotency_key_reuse_with_different_body_conflicts(client, new_user, balance_of):
    alice = new_user(balance=5_000)
    bob = new_user()
    headers = {**alice.headers, "Idempotency-Key": "qa-key-2"}
    first = client.post("/transfers", json={"to_wallet_id": bob.wallet_id, "amount_cents": 100}, headers=headers)
    other = client.post("/transfers", json={"to_wallet_id": bob.wallet_id, "amount_cents": 900}, headers=headers)
    assert first.status_code == 201
    assert other.status_code == 409
    assert balance_of(alice) == 5_000 - 101
