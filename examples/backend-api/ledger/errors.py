"""Domain errors raised by the service layer and mapped to HTTP responses."""

from __future__ import annotations


class LedgerError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFound(LedgerError):
    status_code = 404


class Conflict(LedgerError):
    status_code = 409


class Unprocessable(LedgerError):
    status_code = 422
