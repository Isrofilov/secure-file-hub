import os
import secrets
import pytz
import logging
from dotenv import load_dotenv
from utils.auth import validate_totp_secret, validate_backup_codes
from utils.domains import validate_domains

logger = logging.getLogger(__name__)

# Loading variables of the environment from the .env file if it exists
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    logger.info(f"Loaded environment variables from the file {env_path}")
else:
    logger.info(f"No .env file found, system environment variables are used")

# Setting up timezone by default
DEFAULT_TIMEZONE = pytz.timezone(os.environ.get('TIMEZONE', 'Europe/Moscow'))

# Turning on/off the pre -examination of the images
IMAGE_PREVIEW_ENABLED = os.environ.get('IMAGE_PREVIEW_ENABLED', 'true').lower() == 'true'
logger.info("Image preview: " + ("enabled" if IMAGE_PREVIEW_ENABLED else "disabled"))

# Settings for bypassing restrictions of Cloudflare (if necessary)
# If it is necessary to use a bypass of Cloudflare restrictions, you need to specify the domains
# UPLOAD_DOMAIN to download files (including more than 100 MB) and DOMAIN for access to the site
DOMAIN, UPLOAD_DOMAIN = validate_domains(
    os.environ.get('DOMAIN', ''),
    os.environ.get('UPLOAD_DOMAIN', '')
)

# Cloudflare bypass flag
USE_CLOUDFLARE_BYPASS = bool(DOMAIN and UPLOAD_DOMAIN)
if USE_CLOUDFLARE_BYPASS:
    logger.info(f"Cloudflare restriction bypass activated. Main domain: {DOMAIN}, upload domain: {UPLOAD_DOMAIN}")

# Localization settings
BABEL_DEFAULT_LOCALE = 'en'
BABEL_SUPPORTED_LOCALES = ['en', 'ru']

# Configuration Applications
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(16)
    logger.warning("SECRET_KEY not set in environment variables. Using a randomly generated key — sessions will not persist across restarts.")

# Validation and initialization TOTP
TOTP_SECRET, totp = validate_totp_secret(os.environ.get('TOTP_SECRET'))

# Validation and initialization of backup codes
BACKUP_CODES = validate_backup_codes(os.environ.get('BACKUP_CODES', ''))

# Upload folder configuration
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')

# Checking and creating upload folder
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except Exception as e:
    logger.error(f"Error when creating a folder {UPLOAD_FOLDER}: {e}")
    raise

if not os.path.isdir(UPLOAD_FOLDER):
    logger.error(f"{UPLOAD_FOLDER} is not a folder")
    raise NotADirectoryError(UPLOAD_FOLDER)

if not os.access(UPLOAD_FOLDER, os.W_OK):
    logger.error(f"No write permission to the folder {UPLOAD_FOLDER}")
    raise PermissionError(f"No write permission to the folder {UPLOAD_FOLDER}")