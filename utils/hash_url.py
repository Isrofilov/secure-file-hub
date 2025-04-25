import hashlib
from flask import current_app
import logging

logger = logging.getLogger(__name__)

def generate_download_hash(filename, secret_key):
    """Генерирует хеш для защиты ссылки на скачивание"""
    to_hash = f"{filename}{secret_key}"
    return hashlib.sha256(to_hash.encode()).hexdigest()[:16]