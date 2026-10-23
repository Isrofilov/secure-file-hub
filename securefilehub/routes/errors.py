from flask import Flask, render_template, request
from werkzeug.exceptions import HTTPException

from ..i18n import _

MESSAGES = {
    400: ("Bad request", "The request could not be processed. Reload the page and try again."),
    401: ("Unauthorized", "Sign in to continue."),
    403: ("Access denied", "You do not have access to this page."),
    404: ("Not found", "The page or file does not exist. It may have been moved or deleted."),
    405: ("Method not allowed", "This action is not supported here."),
    410: ("Link expired", "This link is no longer valid. Ask for a new one."),
    413: ("File too large", "The upload exceeds the allowed size."),
    429: ("Too many requests", "Slow down and try again in a moment."),
    500: ("Server error", "Something went wrong on the server. Try again later."),
}


def register(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        code = error.code or 500
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {"ok": False, "error": _(MESSAGES.get(code, ("Error", ""))[0])}, code
        title, text = MESSAGES.get(code, ("Error", "Something went wrong."))
        return render_template("error.html", code=code, title=_(title), text=_(text)), code
