from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, main
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


def test_anonymous_visitors_are_sent_to_dedicated_login_page(monkeypatch):
    settings = Settings(
        app_env="test",
        auth_enabled=True,
        dev_auth_enabled=True,
        dev_admin_username="admin",
        dev_admin_password="admin",
        session_secret="unit-test-secret-that-is-long-enough",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    client = TestClient(main.app)
    landing = client.get("/", follow_redirects=False)
    assert landing.status_code == 303
    assert landing.headers["location"] == "/login"

    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert 'id="login-form"' in login_page.text
    assert 'id="login-google"' in login_page.text
    assert "/static/login.js" in login_page.text
    assert 'id="app-shell"' not in login_page.text

    login = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    workspace = client.get("/", follow_redirects=False)
    assert workspace.status_code == 200
    assert "app-shell" in workspace.text

    already_signed_in = client.get("/login", follow_redirects=False)
    assert already_signed_in.status_code == 303
    assert already_signed_in.headers["location"] == "/"


def test_workspace_opens_directly_when_authentication_is_disabled(monkeypatch):
    settings = Settings(app_env="test", auth_enabled=False)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    client = TestClient(main.app)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "app-shell" in response.text
