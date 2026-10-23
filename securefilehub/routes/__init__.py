from flask import current_app

from ..auth import Authenticator, RateLimiter, SessionEpoch
from ..config import Settings
from ..storage import Storage


def settings() -> Settings:
    return current_app.config["SETTINGS"]


def storage() -> Storage:
    return current_app.extensions["sfh"]["storage"]


def authenticator() -> Authenticator:
    return current_app.extensions["sfh"]["auth"]


def epoch() -> SessionEpoch:
    return current_app.extensions["sfh"]["epoch"]


def limiter() -> RateLimiter:
    return current_app.extensions["sfh"]["limiter"]
