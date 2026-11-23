"""Self-contained fixtures for the backend-api reference tests.

Intended to be copied into <fixture copy>/tests/qa/ and run with the fixture
copy as rootdir (its pyproject.toml puts the fixture root on sys.path).
"""

import itertools
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ledger.app import create_app

PASSWORD = "qa-password-123"


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "qa.db"), password_iterations=1_000)
    with TestClient(app) as c:
        yield c


def _balance(client, user):
    r = client.get("/wallets/me", headers=user.headers)
    assert r.status_code == 200, r.text
    return r.json()["balance_cents"]


@pytest.fixture
def new_user(client):
    """Factory: register + login (+ optional deposit). Returns a namespace."""
    counter = itertools.count(1)

    def _new(email=None, password=PASSWORD, balance=0):
        email = email or f"qa{next(counter)}@example.com"
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201, f"register failed: {r.status_code} {r.text}"
        user_id = r.json()["user_id"]
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        if balance:
            r = client.post("/wallets/me/deposit", json={"amount_cents": balance}, headers=headers)
            assert r.status_code == 200, r.text
        wallet = client.get("/wallets/me", headers=headers).json()
        return SimpleNamespace(email=email, user_id=user_id, headers=headers, wallet_id=wallet["id"])

    return _new


@pytest.fixture
def balance_of(client):
    return lambda user: _balance(client, user)
