from functools import wraps
from flask import session, redirect, url_for, request
import logging
from utils.logging_config import configure_logging
import pyotp
import re
import ipaddress

# Limiter initialization
from utils.rate_limiter import RateLimiter
totp_limiter = RateLimiter(max_attempts=5, window_seconds=300)  # 5 attempts in 5 minutes

# Logging setting
logger = logging.getLogger(__name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session or not session['authenticated']:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def validate_totp_secret(totp_secret, app_name="SecureFileHub"):
    # Checks the validity of the TOTP Secret
    if not totp_secret:
        logger.error("TOTP_SECRET is not configured in environment variables!")
        # Temporary secretion generation for development
        totp_secret = pyotp.random_base32()
        logger.warning(f"Temporary TOTP_SECRET generated: {totp_secret}")
        
        # Generate QR code for the TOTP secret
        generate_totp_qrcode(totp_secret, app_name)
    
    # Validity checks TOTP_SECRET
    try:
        totp = pyotp.TOTP(totp_secret)
        # We check that you can really generate the code
        test_code = totp.now()
        return totp_secret, totp
    except Exception as e:
        logger.error(f"Invalid TOTP_SECRET: {e}")
        # We generate a new secret instead of a challenge
        logger.warning("Generating a new valid TOTP_SECRET")
        new_secret = pyotp.random_base32()
        totp = pyotp.TOTP(new_secret)
        logger.warning(f"Temporary TOTP_SECRET generated: {new_secret}")
        
        # Generate QR code for the new TOTP secret
        generate_totp_qrcode(new_secret, app_name)
        
        return new_secret, totp

def generate_totp_qrcode(totp_secret, issuer_name="SecureFileHub"):
    # Generate and display an ASCII QR code in the logs for the TOTP secret
    import qrcode
    from io import StringIO

    # Create the URI for the TOTP (used by authenticator apps)
    totp_uri = pyotp.TOTP(totp_secret).provisioning_uri(name="totp", issuer_name=issuer_name)
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    # Create ASCII QR code
    f = StringIO()
    qr.print_ascii(out=f)
    f.seek(0)
    
    # Log the QR code
    logger.warning(f"TOTP QR Code:")
    for line in f.getvalue().split('\n'):
        if line.strip():
            logger.warning(line)
    
    logger.warning(f"TOTP URI: {totp_uri}")
    logger.warning(f"Scan this QR code with your authenticator app or enter the secret manually")

def validate_backup_codes(backup_codes_str):
    # Checks the validity of backup codes
    backup_codes = [code.strip() for code in backup_codes_str.split(',') if code.strip()]
    
    if not backup_codes:
        logger.warning("BACKUP_CODES not configured in environment variables")
        return []
    
    backup_code_pattern = re.compile(r'^[=0-9]{6}$')
    valid_backup_codes = []
    
    for code in backup_codes:
        if backup_code_pattern.match(code):
            valid_backup_codes.append(code)
        else:
            logger.error(f"Invalid backup code: {code}")
    
    if len(valid_backup_codes) != len(backup_codes):
        raise ValueError("Non-valid backup codes have been detected. Make sure the codes are 8 digits long.")
    
    return valid_backup_codes

def verify_totp(token, totp):
    # Checks the validity of TOTP token
    return totp.verify(token)

def verify_backup_code(token, backup_codes):
    # Checks the validity of the backup code
    return token in backup_codes

# Get Cloudflare IP List
def get_cloudflare_ips():
    import urllib.request
    import urllib.error
    logger.info("Getting Started with Getting a List of Cloudflare IP Addresses")

    # Create a custom Opener with user-agent
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36')]
    urllib.request.install_opener(opener)

    try:
        # We get the current IPV4 list of Cloudflare addresses
        logger.debug("Requesting IPv4 addresses")
        with urllib.request.urlopen("https://www.cloudflare.com/ips-v4", timeout=5) as response:
            cf_ipv4 = response.read().decode('utf-8').strip().split("\n")
        logger.debug(f"Received {len(cf_ipv4)} IPv4 addresses")
        
        # We get the current IPV6 list of Cloudflare addresses
        logger.debug("Requesting IPv6 addresses")
        with urllib.request.urlopen("https://www.cloudflare.com/ips-v6", timeout=5) as response:
            cf_ipv6 = response.read().decode('utf-8').strip().split("\n")
        logger.debug(f"Received {len(cf_ipv6)} IPv6 addresses")
        
        return cf_ipv4 + cf_ipv6
    except Exception as e:
        # Extended exclusion processing
        logger.error(f"Error getting Cloudflare IP addresses: {e}, type: {type(e)}")
        # In case of error, return built-in list (may be outdated)
        return [
            "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22",
            "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
            "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22",
            "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
            "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22"
        ]

def get_cloudflare_ips_with_caching():
    import json
    import os
    import time
    from datetime import datetime

    cache_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "cloudflare_ips_cache.json")
    cache_dir = os.path.dirname(cache_file)

    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create cache directory: {e}")
            # Use an alternative path, such as a temporary directory
            import tempfile
            cache_file = os.path.join(tempfile.gettempdir(), "cloudflare_ips_cache.json")
    cache_ttl = 7 * 86400  # 7 days in seconds
    
    # Checking the existence and age of the cache file
    if os.path.exists(cache_file):
        file_age = time.time() - os.path.getmtime(cache_file)
        if file_age < cache_ttl:
            # The cache is up to date, let's use it
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    return cache_data.get('ips', [])
            except (json.JSONDecodeError, IOError):
                pass  # In case of cache reading error, we continue and get fresh data
    else:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    
    # We receive fresh data
    ips = get_cloudflare_ips()
    
    # Save to cache
    try:
        with open(cache_file, 'w') as f:
            json.dump({'ips': ips, 'timestamp': datetime.now().isoformat()}, f)
        logger.info(f"Cloudflare IP address cache successfully saved to {cache_file}")
    except Exception as e:
        logger.error(f"Failed to save Cloudflare IP address cache: {e}")
        # Trying to save to another location on error
        fallback_file = os.path.join(tempfile.gettempdir(), "cf_ips_fallback.json")
        try:
            with open(fallback_file, 'w') as f:
                json.dump({'ips': ips, 'timestamp': datetime.now().isoformat()}, f)
            logger.info(f"Cache saved to backup location: {fallback_file}")
            cache_file = fallback_file
        except Exception as e2:
            logger.error(f"Failed to save cache even to backup location: {e2}")
    
    return ips

# Initialize Cloudflare IP list on startup
CF_IPS = get_cloudflare_ips_with_caching()

def is_cloudflare_ip(ip):
    # Check if an IP address belongs to Cloudflare
    for network in CF_IPS:
        try:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(network):
                return True
        except ValueError:
            continue
    return False

def get_client_ip():
    # Then we check the X-Forwarded-For (from Nginx)
    if request.headers.get('X-Forwarded-For'):
        # X-Forwarded-FOR may contain a list of IP addresses
        connecting_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        if is_cloudflare_ip(connecting_ip) and request.headers.get('CF-Connecting-IP'):
            return request.headers.get('CF-Connecting-IP')
        else:
            return connecting_ip
    # In extreme cases, we use direct IP
    else:
        return request.remote_addr