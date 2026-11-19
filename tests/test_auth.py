from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.settings import Settings


def test_development_login_protects_api_routes(monkeypatch):
    settings = Settings(
        app_env="test",
        auth_enabled=True,
        dev_auth_enabled=True,
        dev_admin_username="admin",
        dev_admin_password="admin",
        session_secret="unit-test-secret-that-is-long-enough",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    app = FastAPI()
    app.include_router(auth.router)
    app.add_middleware(auth.AuthMiddleware)

    @app.get("/v2/protected")
    def protected():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/v2/protected").status_code == 401
    bad_login = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad_login.status_code == 401

    login = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    assert login.json()["authenticated"] is True
    assert client.get("/v2/protected").json() == {"ok": True}

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert client.get("/v2/protected").status_code == 401


def test_google_login_is_reported_only_when_configured(monkeypatch):
    settings = Settings(app_env="test", auth_enabled=True, google_client_id="", google_client_secret="")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)
    response = client.get("/auth/config")
    assert response.json()["google_enabled"] is False
