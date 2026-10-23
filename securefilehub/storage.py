"""Everything that touches the upload folder."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Iterable, Iterator

logger = logging.getLogger(__name__)

MAX_NAME_BYTES = 255
CHUNK_SIZE = 1024 * 1024

KINDS = {
    "image": {"jpg", "jpeg", "png", "gif", "webp", "avif", "svg", "bmp", "tif", "tiff", "ico", "heic"},
    "pdf": {"pdf"},
    "video": {"mp4", "webm", "mov", "mkv", "avi", "wmv", "flv", "m4v", "ogv"},
    "audio": {"mp3", "wav", "ogg", "oga", "flac", "aac", "m4a", "wma", "opus"},
    "archive": {"zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz", "zst"},
    "sheet": {"xls", "xlsx", "ods", "csv", "tsv"},
    "doc": {"doc", "docx", "odt", "rtf", "pages"},
    "slides": {"ppt", "pptx", "odp", "key"},
    "text": {"txt", "md", "log", "json", "yaml", "yml", "toml", "ini", "conf", "cfg", "xml", "env"},
    "code": {"py", "js", "ts", "css", "html", "htm", "sh", "go", "rs", "java", "c", "h", "cpp", "sql", "php", "rb"},
}
_KIND_BY_EXT = {ext: kind for kind, exts in KINDS.items() for ext in exts}

# Formats browsers display natively; everything else is always sent as an attachment
_INLINE_IMAGES = {"jpg", "jpeg", "png", "gif", "webp", "avif", "svg", "bmp", "ico"}
_INLINE_VIDEO = {"mp4", "webm", "ogv", "m4v", "mov"}
_INLINE_AUDIO = {"mp3", "wav", "ogg", "oga", "flac", "aac", "m4a", "opus"}
_THUMBNAIL_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff"}
TEXT_PREVIEW_LIMIT = 512 * 1024

_FORBIDDEN_CHARS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


def extension(name: str) -> str:
    _, dot, ext = name.rpartition(".")
    return ext.lower() if dot and _ else ""


def kind_of(name: str) -> str:
    return _KIND_BY_EXT.get(extension(name), "file")


def preview_kind(name: str) -> str | None:
    """How the browser can preview the file, or None when it cannot."""
    ext = extension(name)
    if ext in _INLINE_IMAGES:
        return "image"
    if ext == "pdf":
        return "pdf"
    if ext in _INLINE_VIDEO:
        return "video"
    if ext in _INLINE_AUDIO:
        return "audio"
    if kind_of(name) in {"text", "code"} or ext in {"csv", "tsv"}:
        return "text"
    return None


def can_thumbnail(name: str) -> bool:
    return extension(name) in _THUMBNAIL_EXTS


def clean_filename(name: str) -> str:
    """Turns a client-supplied name into a safe, non-hidden name of at most 255 bytes."""
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _FORBIDDEN_CHARS.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name.lstrip(".")
    if not name:
        name = "file"
    if len(name.encode()) > MAX_NAME_BYTES:
        stem, dot, ext = name.rpartition(".")
        if not dot or len(ext.encode()) > 32:
            stem, ext = name, ""
        suffix = f".{ext}" if ext else ""
        budget = MAX_NAME_BYTES - len(suffix.encode())
        stem = stem.encode()[:budget].decode(errors="ignore").rstrip(" .")
        name = f"{stem}{suffix}"
    return name


def _numbered(name: str, n: int) -> str:
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    suffix = f" ({n})" + (f".{ext}" if ext else "")
    stem = stem.encode()[: MAX_NAME_BYTES - len(suffix.encode())].decode(errors="ignore")
    return f"{stem}{suffix}"


@dataclass(frozen=True)
class FileEntry:
    name: str
    size: int
    mtime: float
    mtime_ns: int

    @property
    def kind(self) -> str:
        return kind_of(self.name)

    @property
    def ext(self) -> str:
        return extension(self.name)

    @property
    def preview(self) -> str | None:
        return preview_kind(self.name)

    @property
    def has_thumbnail(self) -> bool:
        return can_thumbnail(self.name)

    @property
    def version(self) -> str:
        """Changes whenever the file is replaced; used for cache busting and share links."""
        return format(self.mtime_ns ^ self.size, "x")


class Storage:
    def __init__(self, root: Path, incoming: Path, thumbs: Path):
        self.root = root
        self.incoming = incoming
        self.thumbs = thumbs

    # -- reading -------------------------------------------------------------

    def list(self) -> list[FileEntry]:
        entries = []
        with os.scandir(self.root) as it:
            for item in it:
                if item.name.startswith("."):
                    continue
                try:
                    if not item.is_file(follow_symlinks=False):
                        continue
                    st = item.stat(follow_symlinks=False)
                except OSError:
                    continue
                entries.append(FileEntry(item.name, st.st_size, st.st_mtime, st.st_mtime_ns))
        entries.sort(key=lambda e: e.mtime, reverse=True)
        return entries

    def get(self, name: str) -> FileEntry | None:
        """Looks a file up by its exact name; anything that is not a plain visible file is ignored."""
        if not name or name != os.path.basename(name) or name.startswith(".") or "\x00" in name:
            return None
        path = self.root / name
        try:
            st = path.lstat()
        except (OSError, ValueError):
            return None
        if not stat.S_ISREG(st.st_mode):
            return None
        return FileEntry(name, st.st_size, st.st_mtime, st.st_mtime_ns)

    def path(self, entry: FileEntry) -> Path:
        return self.root / entry.name

    # -- writing -------------------------------------------------------------

    def new_temp_file(self) -> IO[bytes]:
        """A temporary file next to the uploads, so that saving it is a cheap link/rename."""
        return tempfile.NamedTemporaryFile(dir=self.incoming, prefix="upload-", delete=True)

    def save(self, stream: IO[bytes], filename: str) -> str:
        """Stores an uploaded file under a free name derived from ``filename``; returns that name."""
        base = clean_filename(filename)
        tmp_path = getattr(stream, "name", None)
        if isinstance(tmp_path, str) and os.path.dirname(tmp_path) == str(self.incoming):
            stream.flush()
            for n in range(1, 10_000):
                name = base if n == 1 else _numbered(base, n)
                try:
                    os.link(tmp_path, self.root / name)
                    return name
                except FileExistsError:
                    continue
                except OSError:
                    break  # hard links are not supported here, fall back to copying
        stream.seek(0)
        for n in range(1, 10_000):
            name = base if n == 1 else _numbered(base, n)
            try:
                fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            except FileExistsError:
                continue
            try:
                with os.fdopen(fd, "wb") as out:
                    shutil.copyfileobj(stream, out, CHUNK_SIZE)
            except BaseException:
                (self.root / name).unlink(missing_ok=True)
                raise
            return name
        raise FileExistsError(base)

    def delete(self, entry: FileEntry) -> None:
        thumb = self.thumbnail_path(entry)
        thumb.unlink(missing_ok=True)
        thumb.with_suffix(".failed").unlink(missing_ok=True)
        self.path(entry).unlink()

    # -- zip -----------------------------------------------------------------

    def zip_stream(self, entries: Iterable[FileEntry]) -> Iterator[bytes]:
        """Streams a ZIP archive of the files without building it on disk or in memory.

        Files are stored uncompressed: most large files are already compressed and
        this keeps the download as fast as the disk allows.
        """
        sink = _Sink()
        with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for entry in entries:
                path = self.path(entry)
                try:
                    info = zipfile.ZipInfo.from_file(path, arcname=entry.name)
                    src = open(path, "rb")
                except OSError as exc:
                    logger.warning("Skipping %s in archive: %s", entry.name, exc)
                    continue
                info.compress_type = zipfile.ZIP_STORED
                with src, archive.open(info, "w") as dst:
                    while chunk := src.read(CHUNK_SIZE):
                        dst.write(chunk)
                        yield from sink.drain()
                yield from sink.drain()
        yield from sink.drain()

    # -- thumbnails ----------------------------------------------------------

    def thumbnail_path(self, entry: FileEntry) -> Path:
        key = hashlib.sha256(f"{entry.name}\0{entry.version}".encode()).hexdigest()[:32]
        return self.thumbs / f"{key}.webp"

    def thumbnail(self, entry: FileEntry, size: int = 480) -> Path | None:
        """Returns a cached WebP thumbnail of an image, generating it on first use."""
        target = self.thumbnail_path(entry)
        failed = target.with_suffix(".failed")
        if target.exists():
            return target
        if failed.exists():
            return None
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return None
        Image.MAX_IMAGE_PIXELS = 60_000_000  # larger images raise instead of eating memory
        tmp = target.with_name(f".{target.name}.{secrets.token_hex(6)}.tmp")
        try:
            with Image.open(self.path(entry)) as img:
                img.draft("RGB", (size * 2, size * 2))
                img = ImageOps.exif_transpose(img)
                img.thumbnail((size, size))
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() or "transparency" in img.info else "RGB")
                img.save(tmp, "WEBP", quality=80, method=4)
            os.replace(tmp, target)
            return target
        except Exception as exc:  # broken, unsupported or oversized image
            logger.info("No thumbnail for %s: %s", entry.name, exc)
            tmp.unlink(missing_ok=True)
            failed.touch()
            return None


class _Sink:
    """Write-only buffer handed to ZipFile; the generator drains it after every write."""

    def __init__(self):
        self._chunks: list[bytes] = []

    def write(self, data) -> int:
        self._chunks.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass

    def drain(self) -> Iterator[bytes]:
        if self._chunks:
            data = b"".join(self._chunks)
            self._chunks.clear()
            yield data
