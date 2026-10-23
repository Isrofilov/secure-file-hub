"""Minimal gettext-style translations loaded straight from .po files."""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from flask import g, request, session

logger = logging.getLogger(__name__)

TRANSLATIONS_DIR = Path(__file__).parent / "translations"
LANGUAGE_NAMES = {"en": "English", "ru": "Русский"}
DEFAULT_LANGUAGE = "en"

_catalogs: dict[str, dict[str, str]] = {}


def parse_po(text: str) -> dict[str, str]:
    """Parses msgid/msgstr pairs; fuzzy, untranslated and context entries are skipped."""
    catalog: dict[str, str] = {}
    for block in re.split(r"\n[ \t]*\n", text):
        fields: dict[str, str] = {}
        key = None
        fuzzy = False
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            elif not line or line.startswith("#"):
                continue
            elif line.startswith('"'):
                if key:
                    fields[key] += ast.literal_eval(line)
            else:
                key, _, value = line.partition(" ")
                fields[key] = ast.literal_eval(value)
        msgid, msgstr = fields.get("msgid"), fields.get("msgstr")
        if msgid and msgstr and not fuzzy and "msgctxt" not in fields:
            catalog[msgid] = msgstr
    return catalog


def load_catalogs() -> None:
    for po in TRANSLATIONS_DIR.glob("*/LC_MESSAGES/messages.po"):
        lang = po.parent.parent.name
        _catalogs[lang] = parse_po(po.read_text(encoding="utf-8"))
        logger.debug("Loaded %d %s translations", len(_catalogs[lang]), lang)


def get_locale() -> str:
    if "lang" not in g:
        lang = session.get("lang")
        if lang not in LANGUAGE_NAMES:
            accepted = request.accept_languages
            lang = (accepted and accepted.best_match(LANGUAGE_NAMES)) or DEFAULT_LANGUAGE
        g.lang = lang
    return g.lang


def gettext(message: str, **params) -> str:
    text = _catalogs.get(get_locale(), {}).get(message, message)
    return text % params if params else text


_ = gettext
