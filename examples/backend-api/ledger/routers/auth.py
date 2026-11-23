from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import auth
from ..db import get_db
from ..models import LoginRequest, RegisterRequest, RegisterResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
def register(payload: RegisterRequest, request: Request, conn: Db) -> RegisterResponse:
    user_id = auth.register_user(
        conn,
        payload.email,
        payload.password,
        iterations=request.app.state.password_iterations,
    )
    return RegisterResponse(user_id=user_id)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, conn: Db) -> TokenResponse:
    user = auth.authenticate(
        conn,
        payload.email,
        payload.password,
        iterations=request.app.state.password_iterations,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(token=auth.create_session(conn, user.id))
