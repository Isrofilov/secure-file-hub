import logging
import secrets
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..auth import client_key, is_authenticated
from ..i18n import LANGUAGE_NAMES, _
from . import authenticator, limiter

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None, fallback: str) -> str:
    """Only allows redirects to a local path, never to another host."""
    if not target:
        return fallback
    parts = urlsplit(target)
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
        wait = limiter().retry_after(key)
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
                session.update(auth=True, csrf=secrets.token_urlsafe(32))
                if lang:
                    session["lang"] = lang
                logger.info("Login from %s using %s", key, method)
                if method == "backup":
                    flash(_("You signed in with a backup code. Each backup code works only once."), "warning")
                return redirect(url_for("files.index"))
            limiter().add_failure(key)
            logger.warning("Failed login from %s", key)
            flash(_("Invalid code"), "error")
            status = 401
    return render_template("login.html"), status


@bp.post("/logout")
def logout():
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
