from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from .. import wallets
from ..auth import CurrentUser
from ..db import get_db
from ..models import MAX_INT64, DepositRequest, WalletResponse

router = APIRouter(prefix="/wallets", tags=["wallets"])

Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/me", response_model=WalletResponse)
def my_wallet(user: CurrentUser, conn: Db) -> WalletResponse:
    wallet = wallets.get_wallet_for_owner(conn, user.id)
    return WalletResponse.model_validate(wallet)


@router.post("/me/deposit", response_model=WalletResponse)
def deposit(payload: DepositRequest, user: CurrentUser, conn: Db) -> WalletResponse:
    wallet = wallets.deposit(conn, user.id, payload.amount_cents)
    return WalletResponse.model_validate(wallet)


@router.get("/{wallet_id}", response_model=WalletResponse)
def read_wallet(
    wallet_id: Annotated[int, Path(gt=0, le=MAX_INT64)],
    user: CurrentUser,
    conn: Db,
) -> WalletResponse:
    wallet = wallets.require_owner(wallets.get_wallet(conn, wallet_id), user)
    return WalletResponse.model_validate(wallet)
