import itertools
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ledger.app import create_app

PASSWORD = "correct-horse-battery"


@pytest.fixture
def client(tmp_path):
    # Fewer PBKDF2 rounds keep the suite fast; production uses the default.
    app = create_app(str(tmp_path / "t.db"), password_iterations=1_000)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user(client):
    """Register and log in a user, optionally funding their wallet."""
    counter = itertools.count(1)

    def _make(email=None, password=PASSWORD, balance=0):
        email = email or f"user{next(counter)}@example.com"
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201, r.text
        user_id = r.json()["user_id"]

        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        headers = {"Authorization": f"Bearer {r.json()['token']}"}

        if balance:
            r = client.post("/wallets/me/deposit", json={"amount_cents": balance}, headers=headers)
            assert r.status_code == 200, r.text

        wallet = client.get("/wallets/me", headers=headers).json()
        return SimpleNamespace(email=email, user_id=user_id, headers=headers, wallet_id=wallet["id"])

    return _make
