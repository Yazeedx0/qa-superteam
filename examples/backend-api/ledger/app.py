"""Application factory.

`uvicorn ledger.app:app` serves an app backed by the database file named in
the LEDGER_DB environment variable (default: ./ledger.db). The module-level
`app` is built on first access, so importing this module has no side effects.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .auth import DEFAULT_ITERATIONS
from .db import init_db
from .errors import LedgerError
from .routers import auth as auth_routes
from .routers import transfers as transfer_routes
from .routers import wallets as wallet_routes


async def _ledger_error_handler(request: Request, exc: LedgerError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def create_app(db_path: str, *, password_iterations: int = DEFAULT_ITERATIONS) -> FastAPI:
    db_path = str(db_path)
    house_wallet_id = init_db(db_path)

    app = FastAPI(title="Ledger", version=__version__)
    app.state.db_path = db_path
    app.state.house_wallet_id = house_wallet_id
    app.state.password_iterations = password_iterations

    app.add_exception_handler(LedgerError, _ledger_error_handler)
    app.include_router(auth_routes.router)
    app.include_router(wallet_routes.router)
    app.include_router(transfer_routes.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


_default_app: FastAPI | None = None


def __getattr__(name: str):
    if name == "app":
        global _default_app
        if _default_app is None:
            _default_app = create_app(os.environ.get("LEDGER_DB", "ledger.db"))
        return _default_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
