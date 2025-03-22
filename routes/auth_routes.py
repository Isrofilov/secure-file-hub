from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from flask_babel import gettext as _
from datetime import datetime
from utils.auth import get_client_ip, verify_totp, verify_backup_code, totp_limiter
from config import DEFAULT_TIMEZONE, BACKUP_CODES, totp
from utils.logging_config import configure_logging
import logging

# Create Blueprint for authentication routes
auth_bp = Blueprint('auth', __name__)

logger = logging.getLogger(__name__)

@auth_bp.route('/')
def index():
    if 'authenticated' in session and session['authenticated']:
        return redirect(url_for('files.files'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        token = request.form.get('token')
        client_ip = get_client_ip()
        
        # Check the speed 
        rate_limited = False
        try:
            rate_limited = totp_limiter.is_rate_limited(client_ip)
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")

        if rate_limited:
            try:
                remaining_time = totp_limiter.get_remaining_time(client_ip)
                minutes = remaining_time // 60
                seconds = remaining_time % 60
                flash(_('Too many failed attempts. Please try again in %(minutes)d min. %(seconds)d sec.', 
                  minutes=minutes, seconds=seconds), 'danger')
            except Exception as e:
                logger.error(f"Error getting remaining time: {e}")
                flash(_("Too many attempts. Please try again later."), 'danger')
            
            return render_template('login.html')

        # Checking backup codes and TOTP
        if (token and verify_backup_code(token, BACKUP_CODES)) or (token and verify_totp(token, totp)):
            session['authenticated'] = True
            session['login_time'] = datetime.now(DEFAULT_TIMEZONE).strftime('%H:%M:%S %d.%m.%Y')
            flash(_('You have successfully logged in'), 'success')
            totp_limiter.add_attempt(client_ip, success=True)
            return redirect(url_for('files.files'))
        else:
            totp_limiter.add_attempt(client_ip, success=False)
            flash(_('Invalid authentication code'), 'danger')
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session['authenticated'] = False
    flash(_('You have logged out'), 'info')
    return redirect(url_for('auth.login'))