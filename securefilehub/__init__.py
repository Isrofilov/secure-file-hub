"""SecureFileHub: a small self-hosted file manager protected by TOTP."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from flask import Flask, g, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from . import i18n
from .auth import Authenticator, RateLimiter, is_authenticated, log_totp_setup
from .config import Settings, load_settings
from .security import add_security_headers, check_csrf, content_security_policy, csrf_token
from .storage import Storage

__version__ = "2.0.0"

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_dotenv() -> None:
    env_file = Path.cwd() / ".env"
    if env_file.is_file():
        from dotenv import load_dotenv

        load_dotenv(env_file)


def create_app(settings: Settings | None = None) -> Flask:
    configure_logging()
    if settings is None:
        _load_dotenv()
        settings = load_settings()

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SETTINGS=settings,
        SESSION_COOKIE_NAME="sfh_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.secure_cookies,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=settings.session_lifetime_hours),
        MAX_CONTENT_LENGTH=settings.max_upload_mb * 1024 * 1024 or None,
        SEND_FILE_MAX_AGE_DEFAULT=timedelta(days=365),
        REAL_IP_HEADER=settings.real_ip_header,
        CSP=content_security_policy(settings.upload_domain if settings.cloudflare_bypass else ""),
        TEMPLATES_AUTO_RELOAD=False,
    )
    if settings.trusted_proxies:
        n = settings.trusted_proxies
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    storage = Storage(settings.upload_folder, settings.incoming_dir, settings.thumbs_dir)
    for leftover in settings.incoming_dir.iterdir():  # interrupted uploads
        leftover.unlink(missing_ok=True)
    authenticator = Authenticator(settings.totp_secret, settings.backup_codes, settings.state_dir)
    limiter = RateLimiter(
        settings.login_max_attempts, settings.login_window_seconds, settings.login_global_max_attempts
    )
    app.extensions["sfh"] = {"storage": storage, "auth": authenticator, "limiter": limiter}

    if settings.totp_generated:
        log_totp_setup(authenticator.provisioning_uri(), settings.totp_secret)
    if not settings.backup_codes:
        logger.info("No BACKUP_CODES configured")
    if settings.cloudflare_bypass:
        logger.info("Upload bypass enabled: %s -> %s", settings.domain, settings.upload_domain)

    i18n.load_catalogs()
    _register_template_helpers(app)

    from .routes import auth, errors, files

    app.register_blueprint(auth.bp)
    app.register_blueprint(files.bp)
    errors.register(app)

    @app.before_request
    def _before():
        g.started = time.perf_counter()
        check_csrf()

    @app.after_request
    def _after(response):
        if "started" in g:
            elapsed = (time.perf_counter() - g.started) * 1000
            response.headers["Server-Timing"] = f"app;dur={elapsed:.1f}"
        return add_security_headers(response)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def _register_template_helpers(app: Flask) -> None:
    static_root = Path(app.static_folder)

    @lru_cache(maxsize=None)
    def _asset_hash(filename: str) -> str:
        return hashlib.sha256((static_root / filename).read_bytes()).hexdigest()[:10]

    def asset(filename: str) -> str:
        """URL of a static file that changes with its content, so it can be cached forever."""
        return url_for("static", filename=filename, v=_asset_hash(filename))

    app.jinja_env.globals.update(
        _=i18n.gettext,
        asset=asset,
        csrf_token=csrf_token,
        get_locale=i18n.get_locale,
        is_authenticated=is_authenticated,
        LANGUAGE_NAMES=i18n.LANGUAGE_NAMES,
        version=__version__,
    )
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    @app.template_filter("filesize")
    def filesize(size: int) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                number = f"{value:.0f}" if unit == "B" else f"{value:.1f}"
                return f"{number} {i18n.gettext(unit)}"
            value /= 1024
        return str(size)

    @app.template_filter("localtime")
    def localtime(timestamp: float) -> str:
        from datetime import datetime

        tz = app.config["SETTINGS"].timezone
        return datetime.fromtimestamp(timestamp, tz).strftime("%Y-%m-%d %H:%M")

    @app.context_processor
    def _inject():
        return {"current_path": request.full_path.rstrip("?")}
