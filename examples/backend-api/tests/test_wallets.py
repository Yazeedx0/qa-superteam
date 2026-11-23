def test_deposit_increases_balance(client, make_user):
    user = make_user()
    r = client.post("/wallets/me/deposit", json={"amount_cents": 2500}, headers=user.headers)
    assert r.status_code == 200
    assert r.json()["balance_cents"] == 2500

    r = client.post("/wallets/me/deposit", json={"amount_cents": 500}, headers=user.headers)
    assert r.json()["balance_cents"] == 3000


def test_deposit_must_be_positive(client, make_user):
    user = make_user()
    r = client.post("/wallets/me/deposit", json={"amount_cents": 0}, headers=user.headers)
    assert r.status_code == 422


def test_owner_can_read_wallet_by_id(client, make_user):
    alice = make_user(balance=700)
    r = client.get(f"/wallets/{alice.wallet_id}", headers=alice.headers)
    assert r.status_code == 200
    assert r.json() == {"id": alice.wallet_id, "owner_id": alice.user_id, "balance_cents": 700}


def test_cannot_read_someone_elses_wallet(client, make_user):
    alice = make_user(balance=700)
    bob = make_user()
    r = client.get(f"/wallets/{alice.wallet_id}", headers=bob.headers)
    assert r.status_code == 404
