"""Business invariants: balances never go negative; fees; conservation of money.

BA-2: test_transfer_of_entire_balance_rejected_when_fee_not_covered,
      test_balance_never_negative_when_fee_exceeds_remaining_funds
"""

import pytest


def _transfer(client, sender, to_wallet_id, amount, headers=None):
    return client.post(
        "/transfers",
        json={"to_wallet_id": to_wallet_id, "amount_cents": amount},
        headers=headers or sender.headers,
    )


def test_transfer_of_entire_balance_rejected_when_fee_not_covered(client, new_user, balance_of):
    alice = new_user(balance=1_000)
    bob = new_user()

    r = _transfer(client, alice, bob.wallet_id, 1_000)  # fee 10 -> needs 1010

    after = balance_of(alice)
    assert r.status_code == 422 and after == 1_000, (
        "transfer of the entire balance must be rejected because amount + fee (1010) exceeds "
        f"the balance (1000); got status {r.status_code} and sender balance {after}"
    )


def test_balance_never_negative_when_fee_exceeds_remaining_funds(client, new_user, balance_of):
    alice = new_user(balance=1_000)
    bob = new_user()

    _transfer(client, alice, bob.wallet_id, 995)  # fee 10 -> needs 1005

    after = balance_of(alice)
    assert after >= 0, f"sender balance went negative ({after}) after paying amount + fee"


def test_transfer_of_balance_minus_fee_succeeds(client, new_user, balance_of):
    alice = new_user(balance=1_000)
    bob = new_user()

    r = _transfer(client, alice, bob.wallet_id, 990)  # fee 10 -> exactly 1000

    assert r.status_code == 201, r.text
    assert r.json()["fee_cents"] == 10
    assert balance_of(alice) == 0
    assert balance_of(bob) == 990


def test_amount_above_balance_rejected(client, new_user, balance_of):
    alice = new_user(balance=1_000)
    bob = new_user()
    r = _transfer(client, alice, bob.wallet_id, 1_001)
    assert r.status_code == 422
    assert balance_of(alice) == 1_000
    assert balance_of(bob) == 0


@pytest.mark.parametrize(
    "amount, fee",
    [(1, 1), (99, 1), (100, 1), (101, 2), (199, 2), (200, 2), (201, 3), (12_345, 124)],
)
def test_fee_is_one_percent_rounded_up_min_one_cent(client, new_user, balance_of, amount, fee):
    alice = new_user(balance=20_000)
    bob = new_user()
    r = _transfer(client, alice, bob.wallet_id, amount)
    assert r.status_code == 201, r.text
    assert r.json()["fee_cents"] == fee
    assert balance_of(alice) == 20_000 - amount - fee
    assert balance_of(bob) == amount


def test_money_is_conserved_across_transfers(client, new_user, balance_of):
    users = [new_user(balance=5_000) for _ in range(3)]
    fees = 0
    for sender, recipient, amount in [(0, 1, 1_234), (1, 2, 2_000), (2, 0, 777), (0, 2, 50)]:
        r = _transfer(client, users[sender], users[recipient].wallet_id, amount)
        assert r.status_code == 201, r.text
        fees += r.json()["fee_cents"]
    assert sum(balance_of(u) for u in users) + fees == 15_000


def test_self_transfer_rejected(client, new_user, balance_of):
    alice = new_user(balance=1_000)
    r = _transfer(client, alice, alice.wallet_id, 100)
    assert r.status_code == 422
    assert balance_of(alice) == 1_000


def test_transfer_to_unknown_wallet_is_404(client, new_user, balance_of):
    alice = new_user(balance=1_000)
    r = _transfer(client, alice, 999_999, 100)
    assert r.status_code == 404
    assert balance_of(alice) == 1_000


@pytest.mark.parametrize("amount", [0, -5, 10.5, "100", True, None])
def test_invalid_transfer_amounts_rejected(client, new_user, balance_of, amount):
    alice = new_user(balance=1_000)
    bob = new_user()
    r = _transfer(client, alice, bob.wallet_id, amount)
    assert r.status_code == 422
    assert balance_of(alice) == 1_000


def test_idempotent_retry_moves_money_once(client, new_user, balance_of):
    alice = new_user(balance=2_000)
    bob = new_user()
    headers = {**alice.headers, "Idempotency-Key": "qa-key-1"}
    first = _transfer(client, alice, bob.wallet_id, 700, headers=headers)
    second = _transfer(client, alice, bob.wallet_id, 700, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert balance_of(alice) == 2_000 - 707
    assert balance_of(bob) == 700
    assert len(client.get("/transfers", headers=alice.headers).json()) == 1


def test_idempotency_key_is_scoped_per_user(client, new_user, balance_of):
    alice = new_user(balance=2_000)
    bob = new_user(balance=2_000)
    carol = new_user()
    for sender in (alice, bob):
        headers = {**sender.headers, "Idempotency-Key": "shared-key"}
        assert _transfer(client, sender, carol.wallet_id, 100, headers=headers).status_code == 201
    assert balance_of(carol) == 200
