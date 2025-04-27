# 🔐 SecureFileHub

SecureFileHub is a lightweight, secure file manager built with Python/Flask, featuring two-factor authentication and a user-friendly interface.

![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg) ![Python](https://img.shields.io/badge/python-3.13-green.svg) ![Flask](https://img.shields.io/badge/flask-3-green.svg) ![Bootstrap](https://img.shields.io/badge/bootstrap-5-green.svg)

*[Русская версия](README.ru.md)*

## 🔑 Features

- **Secure Authentication**: Two-factor authentication with TOTP and backup codes for emergency access
- **Brute Force Protection**: Limited login attempts from a single IP address
- **Multilingual Support**: English and Russian language support
- **Modern Interface**: Responsive design with options to switch between table and tile views
- **Built-in Preview**: View images and PDF files directly in the interface
- **Optimized Performance**: HTML minification and page load optimization
- **Security**: Configured security headers, secure filename handling
- **Docker Support**: Ready to run in a container
- **Cloudflare Upload Limit Bypass**: Solution for uploading files larger than 100MB on Cloudflare's free tier

## 📋 Requirements

- Python 3.11 or higher
- Docker (optional)

## 🚀 Installation and Setup

### Using Docker

#### Option 1: Using pre-built image from DockerHub

1. Pull the latest image:

```bash
docker pull isrofilov/secure-file-hub:latest
```

2. Create a docker-compose.yml file:

```yaml
version: '3'

services:
  file-manager:
    image: isrofilov/secure-file-hub:latest
    ports:
      - "8000:8000"
    volumes:
      - ./uploads:/app/uploads
    environment:
      - TOTP_SECRET=your_secure_totp_secret_here # Optional, will be generated on startup
      - BACKUP_CODES=123456,234567,345678,456789 # Optional
      - LOG_LEVEL=INFO # Optional
      - TIMEZONE=Europe/London # Optional
      - IMAGE_PREVIEW_ENABLED=true # Optional
      - DOMAIN=yourdomain.com # Optional
      - UPLOAD_DOMAIN=upload.yourdomain.com # Optional
    restart: unless-stopped
```

3. Launch with Docker Compose:

```bash
docker-compose up -d
```

#### Option 2: Building from source

1. Clone the repository:

```bash
git clone https://github.com/Isrofilov/secure-file-hub.git
cd secure-file-hub
```

2. Configure environment variables in docker-compose.yml:

```yaml
environment:
  - TOTP_SECRET=your_secure_totp_secret_here # Optional, will be generated on startup
  - BACKUP_CODES=123456,234567,345678,456789 # Optional
  - LOG_LEVEL=INFO # Optional
  - TIMEZONE=Europe/London # Optional
  - IMAGE_PREVIEW_ENABLED=true # Optional
  - DOMAIN=yourdomain.com # Optional
  - UPLOAD_DOMAIN=upload.yourdomain.com # Optional
```

3. Launch with Docker Compose:

```bash
docker-compose up -d
```

4. The application will be available at http://localhost:8000

### Local Installation

1. Clone the repository:

```bash
git clone https://github.com/Isrofilov/secure-file-hub.git
cd secure-file-hub
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create an .env file (all parameters are optional):

```
TOTP_SECRET=your_secure_totp_secret_here
BACKUP_CODES=123456,234567,345678,456789
TIMEZONE=Europe/London
IMAGE_PREVIEW_ENABLED=true
LOG_LEVEL=INFO
```

5. Run the application:

```bash
python app.py
```

6. For running with Gunicorn (recommended for production):

```bash
gunicorn --bind 0.0.0.0:8000 app:app
```

## 🔐 Setting Up Two-Factor Authentication

### Generating TOTP_SECRET

To set up two-factor authentication, you need a TOTP secret key:

1. **Option 1**: Use an online generator:
   - [Base32 Generator](https://www.grc.com/passwords.htm)

2. **Option 2**: Use automatic generation:
   If TOTP_SECRET is not specified in .env or docker-compose.yml, the application will automatically generate a random key at startup. The startup logs will show the generated key as both a text string and a QR code for convenient scanning:
   ```
   Temporary TOTP_SECRET generated: XXXXXXXXXXXXXXXXXXXX
   [QR code for scanning]
   ```
   
   **Important**: An automatically generated key will change with each restart unless you save it in your configuration!

### Setting Up a TOTP App

After obtaining your TOTP_SECRET:

1. Install a TOTP code generation app (Google Authenticator, Authy, or similar)
2. Scan the QR code from the logs or add the key manually
3. Use the temporary codes from the app to log into SecureFileHub

### Backup Codes

Backup codes are designed for emergency access to the system when you don't have access to your primary device with the TOTP app. They provide an alternative authentication method in emergency situations.

**Recommendations for using backup codes**:
- Use backup codes only on trusted devices
- Store backup codes in a secure location separate from your TOTP app device
- For untrusted devices or when providing temporary access to third parties, use only TOTP
- It's strongly recommended to configure backup codes in .env or docker-compose.yml to ensure access to the application if you lose your TOTP device

## 🛡️ Brute Force Protection

The system includes built-in protection against password brute force attempts:
- Limits the number of failed attempts (default 5) from a single IP address
- Temporary login block for 5 minutes after exceeding the limit
- Automatic counter reset after successful login

## 🌐 Multilingual Support

The application supports two languages:
- English (default)
- Russian

Users can switch the language in the interface, and the choice is saved in the session.

## ⚙️ Configuring Cloudflare Limit Bypass

To bypass Cloudflare's limitation on uploading files larger than 100MB on the free tier:

1. Create a subdomain for file uploads (e.g., upload.yourdomain.com)
2. Set up a DNS record for this subdomain but **do not enable** proxying through Cloudflare
3. Specify both domains in the configuration:

```
DOMAIN=yourdomain.com
UPLOAD_DOMAIN=upload.yourdomain.com
```

The system will automatically use different domains for regular operations and for uploading large files.

## ✨ Usage

1. Open the application in your browser: http://localhost:8000 (or your configured domain)
2. Log in using a TOTP code or one of the backup codes (on trusted devices)
3. Manage files through the user-friendly web interface
4. Switch the interface language in the settings menu

## 📊 Screenshots

_[Interface screenshots will be added later]_

## 🧩 Architecture

- **Flask 3**: Web framework
- **Bootstrap 5**: Frontend framework for responsive design
- **Blueprint**: Modular code organization
- **Flask-Babel**: Internationalization and localization
- **Docker**: Containerization for easy deployment

## 📜 License

This project is licensed under the [GNU AFFERO GENERAL PUBLIC LICENSE](https://github.com/Isrofilov/secure-file-hub/blob/main/LICENSE).

---

_Thank you for your interest in SecureFileHub!_
