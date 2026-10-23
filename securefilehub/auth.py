"""Login: TOTP and backup code verification, brute-force limiting, session checks."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import ipaddress
import logging
import os
import threading
import time
from collections import deque
from functools import wraps
from pathlib import Path

import pyotp
from flask import current_app, redirect, request, session, url_for

from .security import unsign

DEVICE_COOKIE = "sfh_device"
DEVICE_COOKIE_AGE = 365 * 24 * 3600

logger = logging.getLogger(__name__)


class Authenticator:
    """Verifies one-time codes.

    TOTP codes are accepted once (a replayed code is rejected) and each backup code
    works exactly once: used codes are recorded as hashes in the state directory.
    """

    def __init__(self, totp_secret: str, backup_codes: tuple[str, ...], state_dir: Path):
        self._totp = pyotp.TOTP(totp_secret)
        self._backup_codes = backup_codes
        self._used_codes_file = state_dir / "used_backup_codes"
        self._last_counter = 0
        self._lock = threading.Lock()

    def verify(self, code: str) -> str | None:
        """Returns "totp" or "backup" when the code is accepted, otherwise None."""
        code = (code or "").strip().replace(" ", "")
        if not code or len(code) > 64:
            return None
        if self._verify_totp(code):
            return "totp"
        if self._verify_backup_code(code):
            return "backup"
        return None

    def _verify_totp(self, code: str) -> bool:
        if not (len(code) == 6 and code.isdigit()):
            return False
        counter = int(time.time()) // self._totp.interval
        # Accept the previous, current and next 30-second step to tolerate clock drift
        for candidate in (counter - 1, counter, counter + 1):
            if hmac.compare_digest(code, self._totp.generate_otp(candidate)):
                with self._lock:
                    if candidate <= self._last_counter:
                        logger.warning("Rejected a replayed TOTP code")
                        return False
                    self._last_counter = candidate
                return True
        return False

    def _code_hash(self, code: str) -> str:
        return hashlib.sha256(f"securefilehub-backup:{code}".encode()).hexdigest()

    def _verify_backup_code(self, code: str) -> bool:
        matched = False
        for candidate in self._backup_codes:
            matched |= hmac.compare_digest(code.encode(), candidate.encode())
        if not matched:
            return False
        digest = self._code_hash(code)
        # The file lock makes the check-and-record atomic across worker processes too
        with self._lock, open(self._used_codes_file, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            used = set(f.read().split())
            if digest in used:
                logger.warning("Rejected an already used backup code")
                return False
            f.write(digest + "\n")
        remaining = sum(self._code_hash(c) not in used | {digest} for c in self._backup_codes)
        logger.warning("Backup code used for login, %d unused backup codes left", remaining)
        return True

    def provisioning_uri(self, issuer: str = "SecureFileHub") -> str:
        return self._totp.provisioning_uri(name="totp", issuer_name=issuer)


class RateLimiter:
    """Sliding-window limiter of failed login attempts, per client and in total."""

    def __init__(self, max_attempts: int, window_seconds: int, global_max_attempts: int = 0):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.global_max = global_max_attempts
        self._failures: dict[str, deque[float]] = {}
        self._global: deque[float] = deque()
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        while self._global and self._global[0] <= cutoff:
            self._global.popleft()
        for key in list(self._failures):
            attempts = self._failures[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                del self._failures[key]

    def retry_after(self, key: str, trusted: bool = False) -> int:
        """Seconds until the client may try again, 0 when it is not limited.

        Trusted devices (ones that signed in before) are not subject to the global cap,
        so an attacker hammering the login cannot lock the owner out.
        """
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            waits = [0.0]
            attempts = self._failures.get(key)
            if attempts and len(attempts) >= self.max_attempts:
                waits.append(attempts[-self.max_attempts] + self.window - now)
            if not trusted and self.global_max and len(self._global) >= self.global_max:
                waits.append(self._global[-self.global_max] + self.window - now)
            return max(1, int(max(waits) + 0.999)) if max(waits) > 0 else 0

    def add_failure(self, key: str, trusted: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            self._failures.setdefault(key, deque()).append(now)
            if not trusted:
                self._global.append(now)
            self._prune(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def client_key() -> str:
    """Identifies the client for rate limiting.

    ``request.remote_addr`` is already corrected by ProxyFix when TRUSTED_PROXIES is set.
    IPv6 clients are grouped by /64, since a single host usually owns the whole prefix.
    """
    # A client-supplied header is only meaningful when a trusted proxy sets it
    header = current_app.config["REAL_IP_HEADER"] if current_app.config["TRUSTED_PROXIES"] else ""
    raw = (request.headers.get(header) if header else None) or request.remote_addr or ""
    try:
        ip = ipaddress.ip_address(raw.strip())
    except ValueError:
        return raw
    if ip.version == 6:
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


class SessionEpoch:
    """A counter stored on disk; bumping it on logout invalidates every existing session."""

    def __init__(self, path: Path):
        self.path = path

    def current(self) -> int:
        try:
            return int(self.path.read_text(encoding="ascii").strip() or 0)
        except (FileNotFoundError, ValueError):
            return 0

    def bump(self) -> None:
        with open(self.path.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(str(self.current() + 1), encoding="ascii")
            os.replace(tmp, self.path)


def is_authenticated() -> bool:
    if session.get("auth") is not True:
        return False
    lifetime = current_app.permanent_session_lifetime.total_seconds()
    if time.time() - session.get("auth_at", 0) > lifetime:
        return False
    return session.get("epoch") == current_app.extensions["sfh"]["epoch"].current()


def is_trusted_device() -> bool:
    return unsign("device", request.cookies.get(DEVICE_COOKIE, ""), max_age=DEVICE_COOKIE_AGE) == 1


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            if request.accept_mimetypes.best == "application/json" or request.is_json:
                return {"ok": False, "error": "unauthorized"}, 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapper


def log_totp_setup(uri: str, secret: str) -> None:
    """Prints the newly generated TOTP secret and a scannable QR code to the log."""
    import io

    import qrcode

    qr = qrcode.QRCode(border=1)
    qr.add_data(uri)
    qr.make(fit=True)
    buffer = io.StringIO()
    qr.print_ascii(out=buffer)
    logger.warning("A new TOTP secret was generated and saved: %s", secret)
    logger.warning("Scan this QR code with your authenticator app:\n%s", buffer.getvalue())
