# Gunicorn settings; any of them can be overridden with GUNICORN_CMD_ARGS.
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
# One process keeps the login rate limiter consistent; threads handle concurrent transfers
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
worker_class = "gthread"
threads = int(os.environ.get("THREADS", "16"))
timeout = 120
graceful_timeout = 30
keepalive = 5
accesslog = "-"
access_log_format = '%(h)s "%(r)s" %(s)s %(B)s %(M)sms'
