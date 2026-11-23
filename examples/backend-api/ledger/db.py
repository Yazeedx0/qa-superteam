"""SQLite persistence: connections, schema and transaction helper."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from fastapi import Request

HOUSE_EMAIL = "house@ledger.internal"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    is_system     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id);

CREATE TABLE IF NOT EXISTS wallets (
    id            INTEGER PRIMARY KEY,
    owner_id      INTEGER NOT NULL UNIQUE REFERENCES users(id),
    balance_cents INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transfers (
    id             INTEGER PRIMARY KEY,
    from_wallet_id INTEGER NOT NULL REFERENCES wallets(id),
    to_wallet_id   INTEGER NOT NULL REFERENCES wallets(id),
    amount_cents   INTEGER NOT NULL CHECK (amount_cents > 0),
    fee_cents      INTEGER NOT NULL CHECK (fee_cents >= 0),
    memo           TEXT,
    created_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_transfers_from_wallet ON transfers(from_wallet_id);
CREATE INDEX IF NOT EXISTS ix_transfers_to_wallet ON transfers(to_wallet_id);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    key                 TEXT    NOT NULL,
    request_fingerprint TEXT    NOT NULL,
    transfer_id         INTEGER NOT NULL REFERENCES transfers(id),
    created_at          TEXT    NOT NULL,
    UNIQUE (user_id, key)
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str) -> sqlite3.Connection:
    # isolation_level=None: we issue BEGIN/COMMIT ourselves (see `transaction`).
    conn = sqlite3.connect(
        db_path,
        timeout=10,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block inside BEGIN IMMEDIATE ... COMMIT, rolling back on error.

    IMMEDIATE takes the write lock up front so that read-then-write sequences
    (balance checks, idempotency lookups) cannot interleave with another writer.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db(db_path: str) -> int:
    """Create the schema if needed and make sure the house account exists.

    Returns the id of the house wallet, which collects transfer fees.
    """
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        with transaction(conn):
            row = conn.execute(
                "SELECT w.id FROM wallets w JOIN users u ON u.id = w.owner_id "
                "WHERE u.email = ? AND u.is_system = 1",
                (HOUSE_EMAIL,),
            ).fetchone()
            if row is not None:
                return row["id"]
            # The house account has no usable password and cannot log in.
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, is_system, created_at) "
                "VALUES (?, '!', 1, ?)",
                (HOUSE_EMAIL, utcnow()),
            )
            cur = conn.execute(
                "INSERT INTO wallets (owner_id, balance_cents) VALUES (?, 0)",
                (cur.lastrowid,),
            )
            return cur.lastrowid
    finally:
        conn.close()


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request."""
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()
