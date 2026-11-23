"""Password hashing, sessions and the `current_user` dependency."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status

from .db import get_db, transaction, utcnow
from .errors import Conflict

PBKDF2_HASH = "sha256"
DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 16
SESSION_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class User:
    id: int
    email: str


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(PBKDF2_HASH, password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_{PBKDF2_HASH}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        rounds = int(iterations)
    except ValueError:
        return False
    if algorithm != f"pbkdf2_{PBKDF2_HASH}" or rounds <= 0:
        return False
    candidate = hashlib.pbkdf2_hmac(PBKDF2_HASH, password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(candidate, expected)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_user(
    conn: sqlite3.Connection, email: str, password: str, *, iterations: int = DEFAULT_ITERATIONS
) -> int:
    """Create a user together with their (empty) wallet. Returns the user id."""
    password_hash = hash_password(password, iterations=iterations)
    try:
        with transaction(conn):
            exists = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                raise Conflict("Email already registered")
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, password_hash, utcnow()),
            )
            user_id = cur.lastrowid
            conn.execute(
                "INSERT INTO wallets (owner_id, balance_cents) VALUES (?, 0)", (user_id,)
            )
    except sqlite3.IntegrityError:
        raise Conflict("Email already registered") from None
    return user_id


def authenticate(
    conn: sqlite3.Connection, email: str, password: str, *, iterations: int = DEFAULT_ITERATIONS
) -> Optional[User]:
    row = conn.execute(
        "SELECT id, email, password_hash FROM users WHERE email = ? AND is_system = 0",
        (email,),
    ).fetchone()
    if row is None:
        # Spend the same time as a real check so response timing does not
        # reveal which emails are registered.
        hash_password(password, iterations=iterations)
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return User(id=row["id"], email=row["email"])


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    with transaction(conn):
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_hash_token(token), user_id, expires_at),
        )
    return token


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    authorization: Annotated[Optional[str], Header()] = None,
) -> User:
    if not authorization:
        raise _unauthorized()
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    row = conn.execute(
        "SELECT u.id, u.email FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ? AND s.expires_at > ?",
        (_hash_token(token), int(time.time())),
    ).fetchone()
    if row is None:
        raise _unauthorized("Invalid or expired token")
    return User(id=row["id"], email=row["email"])


CurrentUser = Annotated[User, Depends(current_user)]
