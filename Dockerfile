FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UPLOAD_FOLDER=/app/uploads \
    PUID=1000 \
    PGID=1000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py gunicorn.conf.py docker-entrypoint.sh ./
COPY securefilehub ./securefilehub
RUN chmod +x docker-entrypoint.sh && python -m compileall -q securefilehub

EXPOSE 8000
VOLUME ["/app/uploads"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=4)"

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "app:app"]
