import pytest


def balance(client, user):
    return client.get("/wallets/me", headers=user.headers).json()["balance_cents"]


def test_transfer_moves_money_and_charges_fee(client, make_user):
    alice = make_user(balance=2000)
    bob = make_user()

    r = client.post(
        "/transfers",
        json={"to_wallet_id": bob.wallet_id, "amount_cents": 500, "memo": "lunch"},
        headers=alice.headers,
    )
    assert r.status_code == 201, r.text
    transfer = r.json()
    assert transfer["from_wallet_id"] == alice.wallet_id
    assert transfer["to_wallet_id"] == bob.wallet_id
    assert transfer["amount_cents"] == 500
    assert transfer["fee_cents"] == 5
    assert transfer["memo"] == "lunch"

    assert balance(client, alice) == 1495
    assert balance(client, bob) == 500


def test_transfer_with_insufficient_funds_is_rejected(client, make_user):
    alice = make_user(balance=300)
    bob = make_user()
    r = client.post(
        "/transfers", json={"to_wallet_id": bob.wallet_id, "amount_cents": 5000}, headers=alice.headers
    )
    assert r.status_code == 422
    assert balance(client, alice) == 300


def test_list_transfers_shows_sent_and_received(client, make_user):
    alice = make_user(balance=5000)
    bob = make_user(balance=5000)
    carol = make_user()

    client.post("/transfers", json={"to_wallet_id": bob.wallet_id, "amount_cents": 100}, headers=alice.headers)
    client.post("/transfers", json={"to_wallet_id": alice.wallet_id, "amount_cents": 200}, headers=bob.headers)

    alice_list = client.get("/transfers", headers=alice.headers).json()
    assert [t["amount_cents"] for t in alice_list] == [200, 100]
    assert len(client.get("/transfers", headers=bob.headers).json()) == 2
    assert client.get("/transfers", headers=carol.headers).json() == []


def test_get_transfer_by_id(client, make_user):
    alice = make_user(balance=1000)
    bob = make_user()
    created = client.post(
        "/transfers", json={"to_wallet_id": bob.wallet_id, "amount_cents": 250}, headers=alice.headers
    ).json()

    r = client.get(f"/transfers/{created['id']}", headers=alice.headers)
    assert r.status_code == 200
    assert r.json() == created


def test_idempotent_retry_does_not_charge_twice(client, make_user):
    alice = make_user(balance=2000)
    bob = make_user()
    body = {"to_wallet_id": bob.wallet_id, "amount_cents": 500}
    headers = {**alice.headers, "Idempotency-Key": "order-42"}

    first = client.post("/transfers", json=body, headers=headers)
    retry = client.post("/transfers", json=body, headers=headers)

    assert first.status_code == retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert balance(client, alice) == 1495
    assert balance(client, bob) == 500


@pytest.mark.skip(reason="pagination not implemented yet")
def test_list_transfers_is_paginated(client, make_user):
    alice = make_user(balance=100_000)
    bob = make_user()
    for _ in range(30):
        client.post("/transfers", json={"to_wallet_id": bob.wallet_id, "amount_cents": 10}, headers=alice.headers)

    page = client.get("/transfers", params={"limit": 10}, headers=alice.headers).json()
    assert len(page) == 10
