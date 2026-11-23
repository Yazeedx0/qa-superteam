"""Request and response schemas."""

from __future__ import annotations

import re
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# SQLite INTEGER is a signed 64-bit value; larger ids/amounts can never exist.
MAX_INT64 = 2**63 - 1

MAX_DEPOSIT_CENTS = 1_000_000  # $10,000.00
MAX_MEMO_LENGTH = 140

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def clean_email(value: str) -> str:
    value = value.strip()
    if not _EMAIL_RE.fullmatch(value):
        raise ValueError("value is not a valid email address")
    return value


Email = Annotated[str, Field(max_length=254), AfterValidator(clean_email)]
Id = Annotated[int, Field(strict=True, gt=0, le=MAX_INT64)]
PositiveCents = Annotated[int, Field(strict=True, gt=0, le=MAX_INT64)]


class RegisterRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    user_id: int


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    token: str


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    balance_cents: int


class DepositRequest(BaseModel):
    amount_cents: Annotated[int, Field(strict=True, gt=0, le=MAX_DEPOSIT_CENTS)]


class TransferRequest(BaseModel):
    to_wallet_id: Id
    amount_cents: PositiveCents
    memo: Optional[str] = Field(default=None, max_length=MAX_MEMO_LENGTH)


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_wallet_id: int
    to_wallet_id: int
    amount_cents: int
    fee_cents: int
    memo: Optional[str]
    created_at: str
