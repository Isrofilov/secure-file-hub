import hmac
import logging
from datetime import datetime

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.formparser import parse_form_data

from ..auth import login_required
from ..i18n import _
from ..security import CSRF_FIELD, CSRF_HEADER, FILE_CSP, csrf_exempt, sign, unsign
from ..storage import FileEntry
from . import epoch, settings, storage

logger = logging.getLogger(__name__)

bp = Blueprint("files", __name__)


def _wants_json() -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"


def _entry_or_404(name: str) -> FileEntry:
    entry = storage().get(name)
    if entry is None:
        abort(404)
    return entry


def _send(entry: FileEntry, inline: bool = False) -> Response:
    kind = entry.preview if inline else None
    mimetype = {"text": "text/plain; charset=utf-8", "pdf": "application/pdf"}.get(kind)
    response = send_file(
        storage().path(entry),
        mimetype=mimetype,
        as_attachment=kind is None,
        download_name=entry.name,
        conditional=True,
        etag=f"{entry.version}",
        last_modified=entry.mtime,
        max_age=0,
    )
    # A PDF needs the browser's own viewer, which a sandbox would block; nothing else may run
    if kind != "pdf":
        response.headers["Content-Security-Policy"] = FILE_CSP
    response.headers["Cache-Control"] = "private, no-cache"
    return response


@bp.get("/files")
@login_required
def index():
    entries = storage().list()
    return render_template(
        "files.html",
        files=entries,
        total_size=sum(e.size for e in entries),
        thumbnails=settings().image_preview,
    )


@bp.get("/files/<name>")
@login_required
def download(name):
    return _send(_entry_or_404(name), inline=request.args.get("inline") == "1")


@bp.get("/thumb/<name>")
@login_required
def thumbnail(name):
    entry = _entry_or_404(name)
    if not settings().image_preview or not entry.has_thumbnail:
        abort(404)
    path = storage().thumbnail(entry)
    if path is None:
        abort(404)
    response = send_file(path, mimetype="image/webp", conditional=True, max_age=0)
    # The URL carries the file version, so a cached thumbnail never goes stale
    cache = "private, max-age=31536000, immutable" if request.args.get("v") == entry.version else "private, no-cache"
    response.headers["Cache-Control"] = cache
    return response


@bp.post("/share/<name>")
@login_required
def share(name):
    entry = _entry_or_404(name)
    token = sign("share", [entry.name, entry.version])
    hours = settings().share_link_ttl_hours
    return {"ok": True, "url": url_for("files.shared", token=token, _external=True), "hours": hours}


@bp.get("/s/<token>")
def shared(token):
    payload = unsign("share", token, max_age=settings().share_link_ttl_hours * 3600)
    if not (isinstance(payload, list) and len(payload) == 2):
        abort(410)
    name, version = payload
    entry = storage().get(name)
    if entry is None or entry.version != version:
        abort(410)
    response = _send(entry)
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@bp.post("/download")
@login_required
def download_many():
    names = request.form.getlist("name")
    entries = [e for e in map(storage().get, dict.fromkeys(names)) if e is not None]
    if not entries:
        flash(_("No files selected"), "warning")
        return redirect(url_for("files.index"))
    if len(entries) == 1:
        return _send(entries[0])
    filename = datetime.now(settings().timezone).strftime("files-%Y%m%d-%H%M%S.zip")
    return Response(
        storage().zip_stream(entries),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@bp.post("/delete")
@login_required
def delete():
    names = list(dict.fromkeys(request.form.getlist("name")))
    deleted, failed = [], []
    for name in names:
        entry = storage().get(name)
        try:
            if entry is None:
                raise FileNotFoundError(name)
            storage().delete(entry)
            deleted.append(name)
        except OSError as exc:
            logger.warning("Could not delete %r: %s", name, exc)
            failed.append(name)
    if deleted:
        logger.info("Deleted %d file(s)", len(deleted))
    if _wants_json():
        return {"ok": not failed, "deleted": deleted, "failed": failed}, 200 if deleted or not failed else 404
    if len(deleted) == 1 and not failed:
        flash(_("Deleted %(name)s", name=deleted[0]), "success")
    elif deleted:
        flash(_("Files deleted: %(count)d", count=len(deleted)), "success")
    if failed:
        flash(_("Could not delete: %(names)s", names=", ".join(failed)), "error")
    return redirect(url_for("files.index"))


# -- uploads ---------------------------------------------------------------


def _receive_files(csrf_required: bool):
    """Parses a multipart upload, streaming file contents straight into the upload folder."""
    store = storage()

    def stream_factory(total_content_length, content_type, filename, content_length=None):
        return store.new_temp_file()

    try:
        _stream, form, files = parse_form_data(
            request.environ,
            stream_factory=stream_factory,
            max_form_memory_size=1024 * 1024,
            max_content_length=current_app.config["MAX_CONTENT_LENGTH"],
            max_form_parts=1000,
            silent=False,
        )
    except RequestEntityTooLarge:
        raise
    except ValueError:
        abort(400)

    try:
        if csrf_required:
            sent = request.headers.get(CSRF_HEADER) or form.get(CSRF_FIELD, "")
            expected = session.get("csrf", "")
            if not expected or not hmac.compare_digest(sent.encode(), expected.encode()):
                abort(400, description="csrf")
        saved = []
        for item in files.getlist("file"):
            if item.filename:
                saved.append(store.save(item.stream, item.filename))
        return saved
    finally:
        for items in files.listvalues():
            for item in items:
                item.close()


def _upload_result(saved: list[str]):
    if not saved:
        message = _("No files selected")
        return {"ok": False, "error": message}, 400
    logger.info("Uploaded %d file(s)", len(saved))
    return {"ok": True, "saved": saved}, 200


@bp.get("/upload")
@login_required
def upload_page():
    s = settings()
    upload_url = url_for("files.upload")
    if s.cloudflare_bypass:
        token = sign("upload", epoch().current())
        upload_url = f"https://{s.upload_domain}{url_for('files.upload_bypass', token=token)}"
    max_bytes = current_app.config["MAX_CONTENT_LENGTH"] or 0
    return render_template("upload.html", upload_url=upload_url, max_bytes=max_bytes)


@bp.post("/upload")
@login_required
@csrf_exempt  # checked in _receive_files, after the body has been streamed to disk
def upload():
    saved = _receive_files(csrf_required=True)
    if _wants_json():
        return _upload_result(saved)
    if saved:
        flash(_("Files uploaded: %(count)d", count=len(saved)), "success")
    else:
        flash(_("No files selected"), "warning")
    return redirect(url_for("files.index") if saved else url_for("files.upload_page"))


@bp.after_app_request
def _bypass_cors(response):
    # Errors raised while receiving the upload need CORS headers too, or the browser hides them
    if request.endpoint == "files.upload_bypass" and settings().cloudflare_bypass:
        response.headers.update(_cors_headers())
    return response


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": f"https://{settings().domain}",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "X-Requested-With",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
    }


@bp.route("/upload-bypass", methods=["POST", "OPTIONS"])
@csrf_exempt  # authenticated by the signed token instead of the session
def upload_bypass():
    s = settings()
    if not s.cloudflare_bypass:
        abort(404)
    if request.method == "OPTIONS":
        return "", 204, _cors_headers()
    if unsign("upload", request.args.get("token", ""), max_age=s.session_lifetime_hours * 3600) != epoch().current():
        return {"ok": False, "error": "unauthorized"}, 401, _cors_headers()
    body, status = _upload_result(_receive_files(csrf_required=False))
    return body, status, _cors_headers()
