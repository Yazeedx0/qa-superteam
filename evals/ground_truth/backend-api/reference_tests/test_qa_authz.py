"""Authorization: users may only see transfers and wallets they are party to.

BA-1: test_outsider_cannot_read_transfer, test_transfer_ids_cannot_be_enumerated
"""


def _send(client, sender, recipient, amount, memo=None):
    body = {"to_wallet_id": recipient.wallet_id, "amount_cents": amount}
    if memo is not None:
        body["memo"] = memo
    r = client.post("/transfers", json=body, headers=sender.headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_outsider_cannot_read_transfer(client, new_user):
    alice = new_user(balance=10_000)
    bob = new_user()
    mallory = new_user()
    transfer = _send(client, alice, bob, 4_200, memo="rent for March")

    r = client.get(f"/transfers/{transfer['id']}", headers=mallory.headers)

    assert r.status_code in (403, 404), (
        f"user C (not sender or recipient) could read transfer {transfer['id']} between "
        f"A and B: GET /transfers/{{id}} returned {r.status_code} {r.text}"
    )


def test_transfer_ids_cannot_be_enumerated(client, new_user):
    alice = new_user(balance=10_000)
    bob = new_user()
    mallory = new_user()
    ids = [_send(client, alice, bob, 100 + i, memo=f"private #{i}")["id"] for i in range(3)]

    leaked = [
        tid for tid in range(1, max(ids) + 3)
        if client.get(f"/transfers/{tid}", headers=mallory.headers).status_code == 200
    ]

    assert leaked == [], (
        f"user C enumerated sequential transfer ids and read other users' transfers: {leaked}"
    )


def test_sender_and_recipient_can_read_transfer(client, new_user):
    alice = new_user(balance=10_000)
    bob = new_user()
    transfer = _send(client, alice, bob, 1_000, memo="dinner")

    for party in (alice, bob):
        r = client.get(f"/transfers/{transfer['id']}", headers=party.headers)
        assert r.status_code == 200, r.text
        assert r.json() == transfer


def test_unknown_transfer_is_404(client, new_user):
    alice = new_user()
    assert client.get("/transfers/999999", headers=alice.headers).status_code == 404


def test_transfer_read_requires_authentication(client, new_user):
    alice = new_user(balance=1_000)
    bob = new_user()
    transfer = _send(client, alice, bob, 100)
    assert client.get(f"/transfers/{transfer['id']}").status_code == 401
    assert client.get(
        f"/transfers/{transfer['id']}", headers={"Authorization": "Bearer forged"}
    ).status_code == 401


def test_transfer_list_only_contains_own_transfers(client, new_user):
    alice = new_user(balance=10_000)
    bob = new_user(balance=10_000)
    carol = new_user(balance=10_000)
    _send(client, alice, bob, 100)
    _send(client, bob, carol, 200)
    _send(client, carol, alice, 300)

    for user in (alice, bob, carol):
        listed = client.get("/transfers", headers=user.headers).json()
        assert len(listed) == 2
        assert all(user.wallet_id in (t["from_wallet_id"], t["to_wallet_id"]) for t in listed)


def test_non_owner_cannot_read_wallet(client, new_user):
    alice = new_user(balance=5_000)
    bob = new_user()
    r = client.get(f"/wallets/{alice.wallet_id}", headers=bob.headers)
    assert r.status_code in (403, 404), f"user B read user A's wallet: {r.status_code} {r.text}"
    assert "balance_cents" not in r.text
