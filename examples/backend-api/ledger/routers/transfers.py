from __future__ import annotations

import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, Path, Request, status

from .. import transfers, wallets
from ..auth import CurrentUser
from ..db import get_db
from ..errors import NotFound
from ..models import MAX_INT64, TransferRequest, TransferResponse

router = APIRouter(prefix="/transfers", tags=["transfers"])

Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TransferResponse)
def create_transfer(
    payload: TransferRequest,
    request: Request,
    user: CurrentUser,
    conn: Db,
    idempotency_key: Annotated[
        Optional[str], Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> TransferResponse:
    transfer = transfers.create_transfer(
        conn,
        sender=user,
        to_wallet_id=payload.to_wallet_id,
        amount_cents=payload.amount_cents,
        memo=payload.memo,
        house_wallet_id=request.app.state.house_wallet_id,
        idempotency_key=idempotency_key,
    )
    return TransferResponse.model_validate(transfer)


@router.get("", response_model=list[TransferResponse])
def list_transfers(user: CurrentUser, conn: Db) -> list[TransferResponse]:
    wallet = wallets.get_wallet_for_owner(conn, user.id)
    return [
        TransferResponse.model_validate(t)
        for t in transfers.list_transfers_for_wallet(conn, wallet.id)
    ]


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_transfer(
    transfer_id: Annotated[int, Path(gt=0, le=MAX_INT64)],
    user: CurrentUser,
    conn: Db,
) -> TransferResponse:
    transfer = transfers.get_transfer(conn, transfer_id)
    if transfer is None:
        raise NotFound("Transfer not found")
    return TransferResponse.model_validate(transfer)
