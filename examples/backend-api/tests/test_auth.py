PASSWORD = "correct-horse-battery"


def test_register_creates_user_with_empty_wallet(client):
    r = client.post("/auth/register", json={"email": "alice@example.com", "password": PASSWORD})
    assert r.status_code == 201
    assert isinstance(r.json()["user_id"], int)

    token = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    ).json()["token"]
    wallet = client.get("/wallets/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert wallet["owner_id"] == r.json()["user_id"]
    assert wallet["balance_cents"] == 0


def test_register_duplicate_email_conflict(client):
    body = {"email": "bob@example.com", "password": PASSWORD}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409


def test_login_wrong_password_is_rejected(client, make_user):
    user = make_user()
    r = client.post("/auth/login", json={"email": user.email, "password": "not-the-password"})
    assert r.status_code == 401


def test_endpoints_require_token(client):
    assert client.get("/wallets/me").status_code == 401
    assert client.get("/wallets/me", headers={"Authorization": "Bearer nope"}).status_code == 401
