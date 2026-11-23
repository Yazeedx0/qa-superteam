"""Transfers between wallets, fees and idempotent retries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Optional

from .auth import User
from .db import transaction, utcnow
from .errors import Conflict, NotFound, Unprocessable

FEE_PERCENT = 1
MIN_FEE_CENTS = 1

_COLUMNS = "id, from_wallet_id, to_wallet_id, amount_cents, fee_cents, memo, created_at"


@dataclass(frozen=True)
class Transfer:
    id: int
    from_wallet_id: int
    to_wallet_id: int
    amount_cents: int
    fee_cents: int
    memo: Optional[str]
    created_at: str


def compute_fee(amount_cents: int) -> int:
    """1% of the amount, rounded up to the next whole cent, never below 1 cent."""
    fee = -(-amount_cents * FEE_PERCENT // 100)
    return max(fee, MIN_FEE_CENTS)


def _to_transfer(row: sqlite3.Row) -> Transfer:
    return Transfer(**{key: row[key] for key in row.keys()})


def _fingerprint(to_wallet_id: int, amount_cents: int, memo: Optional[str]) -> str:
    body = json.dumps(
        {"to_wallet_id": to_wallet_id, "amount_cents": amount_cents, "memo": memo},
        sort_keys=True,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def get_transfer(conn: sqlite3.Connection, transfer_id: int) -> Optional[Transfer]:
    row = conn.execute(f"SELECT {_COLUMNS} FROM transfers WHERE id = ?", (transfer_id,)).fetchone()
    return _to_transfer(row) if row else None


def list_transfers_for_wallet(conn: sqlite3.Connection, wallet_id: int) -> list[Transfer]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM transfers "
        "WHERE from_wallet_id = ? OR to_wallet_id = ? ORDER BY id DESC",
        (wallet_id, wallet_id),
    ).fetchall()
    return [_to_transfer(row) for row in rows]


def create_transfer(
    conn: sqlite3.Connection,
    *,
    sender: User,
    to_wallet_id: int,
    amount_cents: int,
    memo: Optional[str],
    house_wallet_id: int,
    idempotency_key: Optional[str] = None,
) -> Transfer:
    """Move `amount_cents` from the sender's wallet to `to_wallet_id`.

    The sender additionally pays the fee, which is credited to the house wallet.
    If `idempotency_key` was already used by this sender for the same request,
    the original transfer is returned and no money moves.
    """
    fingerprint = _fingerprint(to_wallet_id, amount_cents, memo)

    with transaction(conn):
        if idempotency_key is not None:
            previous = conn.execute(
                "SELECT transfer_id, request_fingerprint FROM idempotency_keys "
                "WHERE user_id = ? AND key = ?",
                (sender.id, idempotency_key),
            ).fetchone()
            if previous is not None:
                if previous["request_fingerprint"] != fingerprint:
                    raise Conflict("Idempotency-Key was already used for a different request")
                return get_transfer(conn, previous["transfer_id"])

        source = conn.execute(
            "SELECT id, balance_cents FROM wallets WHERE owner_id = ?", (sender.id,)
        ).fetchone()
        if source is None:
            raise NotFound("Wallet not found")
        if source["id"] == to_wallet_id:
            raise Unprocessable("Cannot transfer to your own wallet")

        destination = conn.execute(
            "SELECT id FROM wallets WHERE id = ?", (to_wallet_id,)
        ).fetchone()
        if destination is None:
            raise NotFound("Destination wallet not found")

        if source["balance_cents"] < amount_cents:
            raise Unprocessable("Insufficient funds")

        fee_cents = compute_fee(amount_cents)
        conn.execute(
            "UPDATE wallets SET balance_cents = balance_cents - ? WHERE id = ?",
            (amount_cents + fee_cents, source["id"]),
        )
        conn.execute(
            "UPDATE wallets SET balance_cents = balance_cents + ? WHERE id = ?",
            (amount_cents, to_wallet_id),
        )
        conn.execute(
            "UPDATE wallets SET balance_cents = balance_cents + ? WHERE id = ?",
            (fee_cents, house_wallet_id),
        )

        created_at = utcnow()
        cur = conn.execute(
            "INSERT INTO transfers "
            "(from_wallet_id, to_wallet_id, amount_cents, fee_cents, memo, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source["id"], to_wallet_id, amount_cents, fee_cents, memo, created_at),
        )
        transfer_id = cur.lastrowid

        if idempotency_key is not None:
            conn.execute(
                "INSERT INTO idempotency_keys "
                "(user_id, key, request_fingerprint, transfer_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (sender.id, idempotency_key, fingerprint, transfer_id, created_at),
            )

    return Transfer(
        id=transfer_id,
        from_wallet_id=source["id"],
        to_wallet_id=to_wallet_id,
        amount_cents=amount_cents,
        fee_cents=fee_cents,
        memo=memo,
        created_at=created_at,
    )
