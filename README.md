# 🔐 SecureFileHub

SecureFileHub is a lightweight, self-hosted file manager built with Python/Flask. It is protected by two-factor (TOTP) login and has a fast, dependency-free web interface.

![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg) ![Python](https://img.shields.io/badge/python-3.14-green.svg) ![Flask](https://img.shields.io/badge/flask-3-green.svg)

*[Русская версия](README.ru.md)*

## 🔑 Features

- **TOTP login**: sign in with a code from any authenticator app; a code that has already been used is rejected (replay protection)
- **Backup codes**: optional emergency codes, 6–64 characters (letters, digits, dashes), single-use by default (can be made reusable)
- **Brute-force protection**: failed logins are limited per client (IPv6 addresses are grouped by /64) and by a global cap across all clients
- **Hardened web app**: CSRF protection on every state-changing request, a strict Content Security Policy without inline scripts, sandboxed file responses, secure session cookies
- **File browser**: list and grid views, image thumbnails (cached WebP), multi-select
- **Previews**: images, PDF, video, audio and text files open right in the browser
- **Share links**: a link to a single file that works without logging in, expires after `SHARE_LINK_TTL_HOURS` and stops working as soon as the file is replaced or deleted
- **Bulk download**: several files are downloaded as one ZIP archive that is streamed on the fly, without temporary files
- **Upload queue**: drag & drop, paste from the clipboard or pick files, with per-file progress
- **Dark mode** and **English/Russian** interface
- **Cloudflare 100 MB bypass**: upload large files through a separate, non-proxied domain
- **Docker image** that runs as an unprivileged user

## 📋 Requirements

- Python 3.12 or newer, 3.14 recommended (for running without Docker; the Docker image uses 3.14)
- Docker (optional)

## 🚀 Installation and Setup

### Using Docker

#### Option 1: Prebuilt image from Docker Hub

Create a `docker-compose.yml`:

```yaml
services:
  securefilehub:
    image: isrofilov/secure-file-hub:latest
    ports:
      - "8000:8000"
    volumes:
      - ./uploads:/app/uploads
    environment:
      - TIMEZONE=Europe/London
      - BACKUP_CODES=7fk2-9qpm-x3va,c8d1-mm4z-2k7w   # optional, each works once by default
      # - SECURE_COOKIES=true                        # when served over HTTPS
      # - TRUSTED_PROXIES=1                          # when behind a reverse proxy
    restart: unless-stopped
```

Start it and look at the logs for the TOTP QR code (see [First start](#-first-start)):

```bash
docker compose up -d
docker compose logs securefilehub
```

The app is available at http://localhost:8000.

#### Option 2: Building from source

```bash
git clone https://github.com/Isrofilov/secure-file-hub.git
cd secure-file-hub
docker compose up -d --build
```

The bundled `docker-compose.yml` builds the image locally and lists the most common settings.

#### Container user

The image runs the app as an unprivileged user with UID/GID `PUID`/`PGID` (both `1000` by default). On start, the entrypoint fixes the ownership of the upload folder, so files in the mounted volume belong to that user. Set `PUID`/`PGID` to match your host user if needed.

### Local Installation

```bash
git clone https://github.com/Isrofilov/secure-file-hub.git
cd secure-file-hub
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # optional, all settings have defaults
```

Run the development server:

```bash
python app.py
```

For production use Gunicorn. `gunicorn.conf.py` is picked up automatically (bind address, workers, threads, timeouts):

```bash
gunicorn app:app
```

A `.env` file in the working directory is loaded automatically.

## 🔐 First start

You don't have to configure any secrets. If `TOTP_SECRET` and `SECRET_KEY` are not set, they are generated once and saved in `UPLOAD_FOLDER/.securefilehub` (the secret files have mode `600`). Restarts and container re-creation keep using the same values, so sessions and your authenticator keep working.

When the TOTP secret is generated for the first time, the secret and a QR code are printed to the logs — only on that first start:

```
A new TOTP secret was generated and saved: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
Scan this QR code with your authenticator app:
[QR code]
```

1. Install an authenticator app (Google Authenticator, Aegis, 2FAS, Authy or similar)
2. Scan the QR code or enter the secret manually
3. Log in with a 6-digit code from the app

**Important**: the `.securefilehub` directory contains your secrets. Keep it private and include it in backups. To reset the TOTP secret, delete `UPLOAD_FOLDER/.securefilehub/totp_secret` and restart — a new secret and QR code will be printed. You can also set `TOTP_SECRET` explicitly (a base32 string); then the saved file is not used.

The same directory also holds the thumbnail cache, unfinished uploads and the list of used backup codes. Hidden files (names starting with a dot) are never shown in the file list.

### Backup codes

Backup codes are for emergencies when your phone is not at hand. Set them as a comma-separated list in `BACKUP_CODES`, for example `7fk2-9qpm-x3va,c8d1-mm4z-2k7w`. Each code is 6–64 characters long and may contain letters, digits and dashes.

By default each backup code works **only once**: used codes are recorded (as hashes) in the state directory, and the log shows how many unused codes are left. Store them separately from your authenticator device and add new codes when you run low.

If you prefer permanent codes, as in 1.x, set `BACKUP_CODES_REUSABLE=true`. Keep in mind that such a code is effectively a password that never changes: anyone who sees or intercepts it once can sign in for as long as it is configured, and an automated attacker's chance of guessing it does not reset every 30 seconds like a TOTP code. If you enable it, use long random codes (12+ characters, e.g. `7fk2-9qpm-x3va`) rather than 6 digits, and replace a code as soon as you suspect it was seen.

## ⚙️ Configuration

All settings are optional and are read from environment variables (or a `.env` file). See also [`.env.example`](.env.example).

| Variable | Default | Description |
|---|---|---|
| `UPLOAD_FOLDER` | `uploads` (`/app/uploads` in Docker) | Where files are stored |
| `SECRET_KEY` | generated and saved | Key for signing sessions and links; use at least 32 random characters |
| `TOTP_SECRET` | generated and saved | Base32 TOTP secret for your authenticator app |
| `BACKUP_CODES` | — | Comma-separated backup codes (6–64 letters, digits, dashes) |
| `BACKUP_CODES_REUSABLE` | `false` | `true` keeps backup codes valid after use (as in 1.x), see [Backup codes](#backup-codes) |
| `TIMEZONE` | `Europe/Moscow` | Time zone for displayed dates and ZIP names, e.g. `Europe/London`; unknown values fall back to UTC |
| `IMAGE_PREVIEW_ENABLED` | `true` | Show image thumbnails |
| `MAX_UPLOAD_SIZE_MB` | `0` | Maximum request size for uploads in MB, `0` means no limit |
| `SESSION_LIFETIME_HOURS` | `12` | How long a login stays valid (counted from sign-in, not from the last request) |
| `SHARE_LINK_TTL_HOURS` | `24` | How long share links stay valid |
| `SECURE_COOKIES` | `false` | Send the session cookie only over HTTPS; set to `true` behind HTTPS |
| `TRUSTED_PROXIES` | `0` | Number of reverse proxies in front of the app; `X-Forwarded-*` headers are ignored when `0` |
| `REAL_IP_HEADER` | — | Header with the real client IP, e.g. `CF-Connecting-IP` (see below) |
| `LOGIN_MAX_ATTEMPTS` | `5` | Failed logins allowed per client within the window |
| `LOGIN_WINDOW_SECONDS` | `300` | Length of the rate-limiting window in seconds |
| `LOGIN_GLOBAL_MAX_ATTEMPTS` | `30` | Failed logins allowed from all clients together within the window, `0` disables the global cap |
| `DOMAIN` | — | Main domain, for the Cloudflare bypass |
| `UPLOAD_DOMAIN` | — | Non-proxied upload domain, for the Cloudflare bypass |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, …) |
| `PORT` | `8000` | Port to listen on |
| `WEB_CONCURRENCY` | `1` | Number of Gunicorn worker processes (keep at 1, see below) |
| `THREADS` | `16` | Threads per Gunicorn worker |
| `PUID` / `PGID` | `1000` / `1000` | User and group the Docker container runs as |

Any other Gunicorn option can be passed with `GUNICORN_CMD_ARGS`.

### Scaling

The login rate limiter lives in memory of a single process. Keep `WEB_CONCURRENCY=1` (the default) so every login attempt is counted in one place, and scale with `THREADS` instead — uploads and downloads are served by threads.

## 🛡️ Brute-force protection

- At most `LOGIN_MAX_ATTEMPTS` failed logins per client within `LOGIN_WINDOW_SECONDS` (by default 5 per 5 minutes)
- IPv6 clients are grouped by their /64 prefix, since one host usually owns the whole prefix
- A global cap (`LOGIN_GLOBAL_MAX_ATTEMPTS`) slows down attacks spread across many addresses. Browsers that have signed in successfully before are exempt from it, so an attacker cannot lock the owner out
- A successful login resets the counter for that client
- The client is identified by its real IP address, so it is important to configure the reverse proxy settings correctly (see below)

## 🌍 Reverse proxy

When the app runs behind nginx, Caddy, Traefik, Cloudflare etc.:

- **`TRUSTED_PROXIES`** — set it to the number of proxies in front of the app (usually `1`). By default `X-Forwarded-For` is **ignored**: anyone can send that header, and trusting it would let an attacker pick a new fake IP for every attempt and bypass the rate limiter. With `TRUSTED_PROXIES=N`, only the address added by the last N proxies is used, as well as `X-Forwarded-Proto` and `X-Forwarded-Host`.
- **`REAL_IP_HEADER`** — take the client IP from a header such as `CF-Connecting-IP`. It is used only together with `TRUSTED_PROXIES`, and only when the app is reachable **exclusively** through that proxy; otherwise clients could set the header themselves.
- **`SECURE_COOKIES=true`** — set it when the site is served over HTTPS.

Minimal nginx example:

```nginx
server {
    listen 443 ssl;
    server_name files.example.com;

    client_max_body_size 0;          # size limits are handled by MAX_UPLOAD_SIZE_MB
    proxy_request_buffering off;     # stream uploads instead of buffering them
    proxy_buffering off;             # stream large downloads
    proxy_read_timeout 1h;
    proxy_send_timeout 1h;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

With this setup use `TRUSTED_PROXIES=1` and `SECURE_COOKIES=true`.

## ☁️ Cloudflare upload limit bypass

Cloudflare's free plan rejects request bodies larger than 100 MB. To upload bigger files:

1. Create a subdomain for uploads, e.g. `upload.yourdomain.com`
2. Add a DNS record for it with proxying **disabled** (grey cloud, "DNS only") and serve it over HTTPS
3. Set both domains:

```
DOMAIN=yourdomain.com
UPLOAD_DOMAIN=upload.yourdomain.com
```

The site keeps working through `DOMAIN`, while the upload page sends files directly to `UPLOAD_DOMAIN`. Those uploads are authorized by a signed token that is valid for `SESSION_LIFETIME_HOURS`; CORS only allows requests from `https://DOMAIN`. If the two domains are the same, the bypass is disabled.

## ✨ Usage

1. Open http://localhost:8000 (or your domain) and log in with a TOTP code or a backup code
2. Switch between the list and grid views; your choice is remembered in the browser
3. Use the preview button to open a file in the browser, or select several files to download them as a ZIP or delete them
4. Use the share button to get a temporary link to a file
5. Upload files from the upload page: drag & drop, paste or pick them
6. Switch the language and the light/dark theme in the header; log out with the logout button

## ⬆️ Upgrading from 1.x

- `TIMEZONE` still defaults to `Europe/Moscow`
- `X-Forwarded-For` is no longer trusted by default — if you run behind a reverse proxy, set `TRUSTED_PROXIES` (otherwise every client looks like the proxy and shares one rate limit)
- Backup codes are now single-use (set `BACKUP_CODES_REUSABLE=true` to keep the old behaviour) and must be 6–64 characters of letters, digits and dashes
- Logout is now a POST request (the logout button in the interface) and signs out **all** sessions, on every device
- Old download links (`/download/...`) no longer work; use share links instead
- Bootstrap, Flask-Babel, Flask-Minify and pytz have been removed — reinstall dependencies from `requirements.txt`
- Translations are plain `.po` files loaded at startup from `securefilehub/translations/<lang>/LC_MESSAGES/messages.po`; there is no compile step
- If `TOTP_SECRET` was not set before, a new one is generated on the first start — scan the new QR code from the logs

## 🧪 Development

Run the tests:

```bash
python -m unittest discover -s tests
```

To add or change translations, edit the `.po` file and restart the app.

## 🧩 Architecture

- `app.py` — WSGI entry point (`gunicorn app:app` or `python app.py`)
- `securefilehub/__init__.py` — app factory, logging, security headers, template helpers
- `securefilehub/config.py` — settings from the environment, generation of persisted secrets
- `securefilehub/auth.py` — TOTP and backup code verification, rate limiter, login checks
- `securefilehub/security.py` — CSRF, signed tokens (share links, upload bypass), CSP and headers
- `securefilehub/storage.py` — everything that touches the upload folder: listing, saving, ZIP streaming, thumbnails
- `securefilehub/i18n.py` — minimal gettext reading `.po` files
- `securefilehub/routes/` — blueprints: `auth.py` (login, logout, language), `files.py` (files, uploads, sharing), `errors.py`
- `securefilehub/templates/`, `securefilehub/static/` — Jinja templates, CSS, JavaScript and icons
- `tests/` — test suite
- `Dockerfile`, `docker-entrypoint.sh`, `gunicorn.conf.py`, `docker-compose.yml` — deployment

## 📜 License

This project is licensed under the [GNU AFFERO GENERAL PUBLIC LICENSE](https://github.com/Isrofilov/secure-file-hub/blob/main/LICENSE).

---

_Thank you for your interest in SecureFileHub!_
