"""Wallet queries and balance changes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from .auth import User
from .db import transaction
from .errors import NotFound


@dataclass(frozen=True)
class Wallet:
    id: int
    owner_id: int
    balance_cents: int


def _to_wallet(row: sqlite3.Row) -> Wallet:
    return Wallet(id=row["id"], owner_id=row["owner_id"], balance_cents=row["balance_cents"])


def get_wallet(conn: sqlite3.Connection, wallet_id: int) -> Optional[Wallet]:
    row = conn.execute(
        "SELECT id, owner_id, balance_cents FROM wallets WHERE id = ?", (wallet_id,)
    ).fetchone()
    return _to_wallet(row) if row else None


def get_wallet_for_owner(conn: sqlite3.Connection, owner_id: int) -> Wallet:
    row = conn.execute(
        "SELECT id, owner_id, balance_cents FROM wallets WHERE owner_id = ?", (owner_id,)
    ).fetchone()
    if row is None:
        raise NotFound("Wallet not found")
    return _to_wallet(row)


def require_owner(wallet: Optional[Wallet], user: User) -> Wallet:
    """Return the wallet if `user` owns it.

    Wallets that exist but belong to someone else are reported exactly like
    wallets that do not exist, so ids cannot be probed.
    """
    if wallet is None or wallet.owner_id != user.id:
        raise NotFound("Wallet not found")
    return wallet


def deposit(conn: sqlite3.Connection, owner_id: int, amount_cents: int) -> Wallet:
    with transaction(conn):
        cur = conn.execute(
            "UPDATE wallets SET balance_cents = balance_cents + ? WHERE owner_id = ?",
            (amount_cents, owner_id),
        )
        if cur.rowcount != 1:
            raise NotFound("Wallet not found")
        return get_wallet_for_owner(conn, owner_id)
