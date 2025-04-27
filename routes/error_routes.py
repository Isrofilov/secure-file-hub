from flask import Blueprint, render_template
from flask_babel import gettext as _

errors_bp = Blueprint('errors', __name__)

@errors_bp.app_errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error_code=404, error_message=_("Page not found")), 404

@errors_bp.app_errorhandler(500)
def internal_error(error):
    return render_template('error.html', error_code=500, error_message=_("Internal server error")), 500

@errors_bp.app_errorhandler(403)
def forbidden_error(error):
    return render_template('error.html', error_code=403, error_message=_("Access forbidden")), 403

@errors_bp.app_errorhandler(405)
def method_not_allowed_error(error):
    return render_template('error.html', error_code=405, error_message=_("Method not allowed")), 405

@errors_bp.app_errorhandler(401)
def unauthorized_error(error):
    return render_template('error.html', error_code=401, error_message=_("Unauthorized access")), 401

@errors_bp.app_errorhandler(410)
def gone_error(error):
    return render_template('error.html', error_code=410, error_message=_("The link is out of date")), 410