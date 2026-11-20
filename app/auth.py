from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .settings import get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE = "pinky_bread_session"
STATE_COOKIE = "pinky_bread_oauth_state"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(payload: dict[str, Any]) -> str:
    settings = get_settings()
    raw = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64(hmac.new(settings.session_secret.encode("utf-8"), raw.encode("ascii"), hashlib.sha256).digest())
    return f"{raw}.{signature}"


def _verify(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    raw, supplied = token.rsplit(".", 1)
    settings = get_settings()
    expected = _b64(hmac.new(settings.session_secret.encode("utf-8"), raw.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(supplied, expected):
        return None
    try:
        payload = json.loads(_unb64(raw))
        expires_at = int(payload.get("exp", 0)) if isinstance(payload, dict) else 0
    except (ValueError, TypeError, binascii.Error):
        return None
    if not isinstance(payload, dict) or expires_at <= int(time.time()):
        return None
    return payload


def session_user(request: Request) -> dict[str, Any] | None:
    return _verify(request.cookies.get(SESSION_COOKIE))


def _set_session(response: Response, *, subject: str, email: str | None = None, provider: str, secure: bool = False) -> None:
    settings = get_settings()
    token = _sign({"sub": subject, "email": email, "provider": provider, "exp": int(time.time()) + 43200})
    response.set_cookie(
        SESSION_COOKIE, token, max_age=43200, httponly=True, secure=secure,
        samesite="lax", path="/",
    )


def _dev_login_enabled() -> bool:
    settings = get_settings()
    return settings.dev_auth_enabled and settings.app_env.lower() in {"development", "docker", "dev", "test"}


@router.get("/config")
def auth_config() -> dict[str, bool]:
    settings = get_settings()
    return {
        "enabled": settings.auth_enabled,
        "dev_login_enabled": _dev_login_enabled(),
        "google_enabled": bool(settings.google_client_id and settings.google_client_secret),
    }


@router.get("/me")
def auth_me(request: Request) -> dict[str, Any]:
    settings = get_settings()
    if not settings.auth_enabled:
        return {"authenticated": True, "user": {"sub": "local-development", "provider": "disabled"}}
    user = session_user(request)
    return {"authenticated": bool(user), "user": user}


@router.post("/login")
def dev_login(request: Request, credentials: LoginRequest) -> Response:
    settings = get_settings()
    if not settings.auth_enabled or not _dev_login_enabled():
        raise HTTPException(404, "Development sign-in is disabled")
    username_ok = hmac.compare_digest(credentials.username, settings.dev_admin_username)
    password_ok = hmac.compare_digest(credentials.password, settings.dev_admin_password)
    if not (username_ok and password_ok):
        raise HTTPException(401, "Invalid username or password")
    response = JSONResponse({"authenticated": True, "user": {"sub": settings.dev_admin_username, "provider": "development"}})
    _set_session(response, subject=settings.dev_admin_username, provider="development", secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https")
    return response


@router.post("/logout")
def logout() -> Response:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/google")
def google_login(request: Request) -> Response:
    settings = get_settings()
    if not settings.auth_enabled or not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(404, "Google sign-in is not configured")
    state = secrets.token_urlsafe(32)
    state_token = _sign({"state": state, "exp": int(time.time()) + 600})
    redirect_uri = settings.google_redirect_uri or str(request.url_for("google_callback"))
    from urllib.parse import urlencode
    params = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}", status_code=302)
    response.set_cookie(STATE_COOKIE, state_token, max_age=600, httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/auth")
    return response


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request, code: str = "", state: str = "", error: str = "") -> Response:
    settings = get_settings()
    state_payload = _verify(request.cookies.get(STATE_COOKIE))
    if error:
        raise HTTPException(400, f"Google sign-in was not completed: {error}")
    if not code or not state_payload or not hmac.compare_digest(str(state_payload.get("state", "")), state):
        raise HTTPException(400, "Google sign-in state validation failed. Please try again.")
    redirect_uri = settings.google_redirect_uri or str(request.url_for("google_callback"))
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        if token_response.is_error:
            raise HTTPException(502, "Google token exchange failed")
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise HTTPException(502, "Google did not return an access token")
        profile_response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if profile_response.is_error:
            raise HTTPException(502, "Unable to retrieve Google account profile")
        profile = profile_response.json()
    if not profile.get("email") or profile.get("email_verified") is not True:
        raise HTTPException(403, "Google account must have a verified email address")
    response = RedirectResponse("/", status_code=303)
    _set_session(response, subject=str(profile.get("sub")), email=str(profile["email"]), provider="google", secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https")
    response.delete_cookie(STATE_COOKIE, path="/auth")
    return response


class AuthMiddleware:
    """Protect API routes with a signed, short-lived browser session cookie."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not get_settings().auth_enabled:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        protected = path.startswith("/v1/") or path.startswith("/v2/")
        if not protected:
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        cookie_header = headers.get("cookie", "")
        cookies = {}
        for part in cookie_header.split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                cookies[key] = value
        if _verify(cookies.get(SESSION_COOKIE)):
            await self.app(scope, receive, send)
            return
        response = JSONResponse({"detail": "Sign in is required to access this workspace."}, status_code=401)
        await response(scope, receive, send)
