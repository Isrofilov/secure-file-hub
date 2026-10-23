"""Application settings, read once from the environment (and an optional .env file)."""

from __future__ import annotations

import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Hidden directory inside the upload folder that holds application state:
# persisted secrets, used backup codes, thumbnail cache and in-flight uploads.
STATE_DIR_NAME = ".securefilehub"

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)
_BACKUP_CODE_RE = re.compile(r"^[A-Za-z0-9-]{6,64}$")


class ConfigError(ValueError):
    pass


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int = 0) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from exc
    if number < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {number}")
    return number


def _domain(name: str) -> str:
    value = os.environ.get(name, "").strip().lower()
    if value and not _DOMAIN_RE.match(value):
        logger.warning("%s=%r is not a valid domain name and is ignored", name, value)
        return ""
    return value


def _backup_codes(raw: str) -> tuple[str, ...]:
    codes = tuple(code.strip() for code in raw.split(",") if code.strip())
    invalid = [code for code in codes if not _BACKUP_CODE_RE.match(code)]
    if invalid:
        raise ConfigError(
            "BACKUP_CODES must be a comma-separated list of 6-64 character codes "
            "(letters, digits and dashes)"
        )
    return codes


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown TIMEZONE %r, falling back to UTC", name)
        return ZoneInfo("UTC")


def _read_or_create_secret(path: Path, factory) -> str:
    """Returns the secret stored at ``path``, creating it atomically on first use.

    The file is written to a temporary name and hard-linked into place, so concurrent
    workers starting at the same time all end up with the same value.
    """
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except FileNotFoundError:
        pass

    tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(factory())
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
    finally:
        tmp.unlink(missing_ok=True)
    return path.read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class Settings:
    upload_folder: Path
    state_dir: Path
    secret_key: str
    totp_secret: str
    totp_generated: bool
    backup_codes: tuple[str, ...]
    timezone: ZoneInfo
    image_preview: bool
    domain: str
    upload_domain: str
    max_upload_mb: int
    session_lifetime_hours: int
    share_link_ttl_hours: int
    secure_cookies: bool
    trusted_proxies: int
    real_ip_header: str
    login_max_attempts: int
    login_window_seconds: int
    login_global_max_attempts: int
    languages: tuple[str, ...] = field(default=("en", "ru"))

    @property
    def cloudflare_bypass(self) -> bool:
        return bool(self.domain and self.upload_domain)

    @property
    def incoming_dir(self) -> Path:
        return self.state_dir / "incoming"

    @property
    def thumbs_dir(self) -> Path:
        return self.state_dir / "thumbs"


def load_settings() -> Settings:
    upload_folder = Path(os.environ.get("UPLOAD_FOLDER", "uploads")).resolve()
    state_dir = upload_folder / STATE_DIR_NAME
    for directory in (upload_folder, state_dir, state_dir / "incoming", state_dir / "thumbs"):
        directory.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    if not os.access(upload_folder, os.W_OK):
        raise ConfigError(f"No write permission for UPLOAD_FOLDER {upload_folder}")

    secret_key = os.environ.get("SECRET_KEY", "").strip()
    if not secret_key:
        secret_key = _read_or_create_secret(state_dir / "secret_key", lambda: secrets.token_urlsafe(48))
        logger.info("SECRET_KEY not set, using the key persisted in %s", state_dir)
    elif len(secret_key) < 32:
        logger.warning("SECRET_KEY is shorter than 32 characters; use a longer random value")

    import pyotp

    totp_secret = os.environ.get("TOTP_SECRET", "").strip().replace(" ", "").upper()
    totp_generated = False
    if totp_secret:
        try:
            pyotp.TOTP(totp_secret).now()
        except Exception as exc:
            raise ConfigError("TOTP_SECRET is not a valid base32 string") from exc
    else:
        secret_file = state_dir / "totp_secret"
        totp_generated = not secret_file.exists()
        totp_secret = _read_or_create_secret(secret_file, pyotp.random_base32)

    domain, upload_domain = _domain("DOMAIN"), _domain("UPLOAD_DOMAIN")
    if domain and domain == upload_domain:
        logger.warning("DOMAIN and UPLOAD_DOMAIN are the same, upload bypass is disabled")
        domain = upload_domain = ""

    return Settings(
        upload_folder=upload_folder,
        state_dir=state_dir,
        secret_key=secret_key,
        totp_secret=totp_secret,
        totp_generated=totp_generated,
        backup_codes=_backup_codes(os.environ.get("BACKUP_CODES", "")),
        timezone=_timezone(os.environ.get("TIMEZONE", "").strip() or "Europe/Moscow"),
        image_preview=_bool("IMAGE_PREVIEW_ENABLED", True),
        domain=domain,
        upload_domain=upload_domain,
        max_upload_mb=_int("MAX_UPLOAD_SIZE_MB", 0),
        session_lifetime_hours=_int("SESSION_LIFETIME_HOURS", 12, minimum=1),
        share_link_ttl_hours=_int("SHARE_LINK_TTL_HOURS", 24, minimum=1),
        secure_cookies=_bool("SECURE_COOKIES", False),
        trusted_proxies=_int("TRUSTED_PROXIES", 0),
        real_ip_header=os.environ.get("REAL_IP_HEADER", "").strip(),
        login_max_attempts=_int("LOGIN_MAX_ATTEMPTS", 5, minimum=1),
        login_window_seconds=_int("LOGIN_WINDOW_SECONDS", 300, minimum=1),
        login_global_max_attempts=_int("LOGIN_GLOBAL_MAX_ATTEMPTS", 30),
    )
