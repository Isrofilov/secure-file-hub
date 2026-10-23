import logging
import secrets
import time
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..auth import DEVICE_COOKIE, DEVICE_COOKIE_AGE, client_key, is_authenticated, is_trusted_device
from ..i18n import LANGUAGE_NAMES, _
from ..security import sign
from . import authenticator, epoch, limiter, settings

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None, fallback: str) -> str:
    """Only allows redirects to a local path, never to another host."""
    if not target:
        return fallback
    parts = urlsplit(target)
    if any(ord(c) < 32 or ord(c) == 127 for c in target):
        return fallback
    if parts.scheme or parts.netloc or not target.startswith("/") or target[1:2] in ("/", "\\"):
        return fallback
    return target


@bp.get("/")
def index():
    return redirect(url_for("files.index" if is_authenticated() else "auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if is_authenticated():
        return redirect(url_for("files.index"))

    status = 200
    if request.method == "POST":
        key = client_key()
        trusted = is_trusted_device()
        wait = limiter().retry_after(key, trusted)
        if wait:
            flash(_("Too many failed attempts. Try again in %(minutes)d min %(seconds)d sec.",
                    minutes=wait // 60, seconds=wait % 60), "error")
            status = 429
        else:
            method = authenticator().verify(request.form.get("code", ""))
            if method:
                limiter().reset(key)
                lang = session.get("lang")
                session.clear()  # new session on login prevents session fixation
                session.permanent = True
                session.update(auth=True, auth_at=int(time.time()), epoch=epoch().current(),
                               csrf=secrets.token_urlsafe(32))
                if lang:
                    session["lang"] = lang
                logger.info("Login from %s using %s", key, method)
                if method == "backup" and not settings().backup_codes_reusable:
                    flash(_("You signed in with a backup code. Each backup code works only once."), "warning")
                response = redirect(url_for("files.index"))
                response.set_cookie(DEVICE_COOKIE, sign("device", 1), max_age=DEVICE_COOKIE_AGE, httponly=True,
                                    samesite="Lax", secure=settings().secure_cookies)
                return response
            limiter().add_failure(key, trusted)
            logger.warning("Failed login from %s", key)
            flash(_("Invalid code"), "error")
            status = 401
    return render_template("login.html", backup_codes_reusable=settings().backup_codes_reusable), status


@bp.post("/logout")
def logout():
    if is_authenticated():
        epoch().bump()  # signs out every session, including copied cookies
    lang = session.get("lang")
    session.clear()
    if lang:
        session["lang"] = lang
    flash(_("You have signed out"), "info")
    return redirect(url_for("auth.login"))


@bp.get("/lang/<lang>")
def set_language(lang):
    if lang in LANGUAGE_NAMES:
        session["lang"] = lang
    return redirect(_safe_next(request.args.get("next"), url_for("auth.index")))
