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
    assert 'id="root"' in workspace.text
    assert "/static/app/workspace.js" in workspace.text

    already_signed_in = client.get("/login", follow_redirects=False)
    assert already_signed_in.status_code == 303
    assert already_signed_in.headers["location"] == "/"


def test_signed_in_browser_deep_links_serve_react_shell_and_unknown_api_paths_stay_404(monkeypatch):
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
    anonymous = client.get("/workspace/overview", follow_redirects=False)
    assert anonymous.status_code == 303
    assert "/login?next=" in anonymous.headers["location"]

    login = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    assert login.headers["cache-control"] == "no-store"
    assert client.get("/auth/me").json()["authenticated"] is True

    deep_link = client.get("/workspace/overview", follow_redirects=False)
    assert deep_link.status_code == 200
    assert 'id="root"' in deep_link.text
    assert client.get("/v2/this-route-does-not-exist").status_code == 404
    assert client.get("/static/missing-asset.js").status_code == 404


def test_workspace_opens_directly_when_authentication_is_disabled(monkeypatch):
    settings = Settings(app_env="test", auth_enabled=False)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    client = TestClient(main.app)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert 'id="root"' in response.text
    assert "/static/app/workspace.js" in response.text
