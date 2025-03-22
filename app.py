import os
from flask import Flask, request, session, redirect, url_for
from flask_minify import Minify
from flask_babel import Babel
import time
from datetime import datetime
from config import SECRET_KEY, BABEL_SUPPORTED_LOCALES
from utils.security import add_security_headers

# Импорт blueprints
from routes.auth_routes import auth_bp
from routes.file_routes import files_bp
from routes.error_routes import errors_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Babel initialization
babel = Babel(app)

# Localization settings
def get_locale():
    # Priority: 1) the selected language in the session 2) the language of the browser 3) the default language
    if 'language' in session:
        return session['language']
    return request.accept_languages.best_match(BABEL_SUPPORTED_LOCALES)

# Set the language selection function
babel.init_app(app, locale_selector=get_locale)

# Registration Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(files_bp)
app.register_blueprint(errors_bp)

@app.route('/change_language/<lang>')
def change_language(lang):
    if lang in BABEL_SUPPORTED_LOCALES:
        session['language'] = lang
    return redirect(request.referrer or url_for('files.files'))

@app.before_request
def before_request():
    # Store the start time of the request processing
    request.start_time = time.time()

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.context_processor
def inject_page_generation_time():
    def get_generation_time():
        # Calculate time taken in milliseconds
        if hasattr(request, 'start_time'):
            generation_time = (time.time() - request.start_time) * 1000
            return f"{generation_time:.2f} ms"
        return None
    
    # Make function available in all templates
    return {'get_generation_time': get_generation_time}

@app.after_request
def add_security_headers_wrapper(response):
    return add_security_headers(response)

Minify(app=app)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)