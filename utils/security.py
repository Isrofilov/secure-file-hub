import re

def secure_filename_with_cyrillic(filename):
    # Provides a safe file name, while maintaining Cyrillic
    filename = re.sub(r'[^\w\s\u0400-\u04FF.-]', '_', filename)  # The range of the Cyrillic alphabet has been added
    filename = re.sub(r'\s+', '_', filename)
    if len(filename) > 255:  # Limiting the file name length
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext
    return filename.strip('._')

def add_security_headers(response):
    # Adds security headers to HTTP answer
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response