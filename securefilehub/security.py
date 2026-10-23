"""CSRF protection, signed tokens and HTTP security headers."""

from __future__ import annotations

import hmac
import secrets

from flask import abort, current_app, request, session
from itsdangerous import BadSignature, URLSafeTimedSerializer

CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_token() -> str:
    token = session.get("csrf")
    if not token:
        token = session["csrf"] = secrets.token_urlsafe(32)
    return token


def check_csrf() -> None:
    """Rejects state-changing requests without a valid CSRF token."""
    if request.method not in UNSAFE_METHODS:
        return
    view = current_app.view_functions.get(request.endpoint)
    if view is None or getattr(view, "csrf_exempt", False):
        return
    expected = session.get("csrf")
    sent = request.headers.get(CSRF_HEADER) or request.form.get(CSRF_FIELD, "")
    if not expected or not hmac.compare_digest(sent.encode(), expected.encode()):
        abort(400, description="csrf")


def csrf_exempt(view):
    view.csrf_exempt = True
    return view


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=f"securefilehub.{salt}")


def sign(purpose: str, payload) -> str:
    return _serializer(purpose).dumps(payload)


def unsign(purpose: str, token: str, max_age: int):
    """Returns the payload of a valid, unexpired token, otherwise None."""
    try:
        return _serializer(purpose).loads(token, max_age=max_age)
    except BadSignature:
        return None


def content_security_policy(upload_domain: str = "") -> str:
    connect = "'self'" + (f" https://{upload_domain}" if upload_domain else "")
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "img-src 'self' data: blob:",
            "media-src 'self' blob:",
            "font-src 'self'",
            f"connect-src {connect}",
            "frame-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'self'",
        ]
    )


# Served files never run scripts or load anything when opened directly
FILE_CSP = "sandbox; default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'"


def add_security_headers(response):
    headers = response.headers
    headers.setdefault("Content-Security-Policy", current_app.config["CSP"])
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    headers.setdefault("Referrer-Policy", "same-origin")
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    if request.is_secure:
        headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.endpoint != "static" and "Cache-Control" not in headers:
        headers["Cache-Control"] = "no-store"
    return response
