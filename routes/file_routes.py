from flask import Blueprint, request, render_template, redirect, send_file, url_for, flash, send_from_directory, abort, current_app
from flask_babel import gettext as _, gettext
from datetime import datetime, timezone
from config import DEFAULT_TIMEZONE, DOMAIN, UPLOAD_DOMAIN, USE_CLOUDFLARE_BYPASS, IMAGE_PREVIEW_ENABLED
from utils.auth import login_required
from utils.hash_url import generate_download_hash
from utils.logging_config import configure_logging
import logging
import os
import time
import urllib.parse
import tempfile
import zipfile

logger = logging.getLogger(__name__)

# Create BluePrint for working with files
files_bp = Blueprint('files', __name__)

@files_bp.route('/files')
@login_required
def files():
    files = []
    for filename in os.listdir('uploads'):
        filepath = os.path.join('uploads', filename)
        if os.path.isfile(filepath):
            file_size = os.path.getsize(filepath)
            file_time = os.path.getmtime(filepath)
            file_datetime = datetime.fromtimestamp(file_time).replace(tzinfo=timezone.utc).astimezone(DEFAULT_TIMEZONE)
            file_date = file_datetime.strftime('%d.%m.%Y %H:%M:%S')
            
            # Converting the size of the file into a readable format
            if file_size < 1024:
                size_str = f"{file_size} {gettext('B')}"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size/1024:.1f} {gettext('KB')}"
            else:
                size_str = f"{file_size/(1024*1024):.1f} {gettext('MB')}"
            
            # Determination of the file type
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            
            # Determine the type of extension file
            is_image = ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.tiff', '.ico']
            is_pdf = ext == '.pdf'
            is_document = ext in ['.doc', '.docx', '.odt', '.rtf', '.txt', '.conf', '.json', '.md']
            is_spreadsheet = ext in ['.xls', '.xlsx', '.ods', '.csv']
            is_archive = ext in ['.zip', '.rar', '.tar', '.gz', '.7z']
            is_video = ext in ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm']
            is_audio = ext in ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.wma']
            
            # Add a file with additional attributes of type
            files.append({
                'name': filename,
                'size': size_str,
                'date': file_date,
                'type': ext[1:] if ext else '',  # File type without point
                'hash': generate_download_hash(filename, current_app.config['SECRET_KEY']),
                'is_image': is_image,
                'is_pdf': is_pdf,
                'is_document': is_document,
                'is_spreadsheet': is_spreadsheet,
                'is_archive': is_archive,
                'is_video': is_video,
                'is_audio': is_audio
            })
    
    # Date file sorting (new on top)
    files.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('files.html', files=files, IMAGE_PREVIEW_ENABLED=IMAGE_PREVIEW_ENABLED)

@files_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        # Check if there is a file in the request
        if 'file' not in request.files:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {'success': False, 'message': '_("No file selected")'}, 400
            flash('_("No file selected")', 'danger')
            return redirect(request.url)
        
        files = request.files.getlist('file')
        
        if not files or files[0].filename == '':
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {'success': False, 'message': '_("No file selected")'}, 400
            flash('_("No file selected")', 'danger')
            return redirect(request.url)
        
        from utils.security import secure_filename_with_cyrillic

        success_count = 0
        for file in files:
            original_filename = secure_filename_with_cyrillic(file.filename)

            base, ext = os.path.splitext(original_filename)
            filename = original_filename

            # If the file exists, add the suffix (2), (3), etc.
            if os.path.exists(os.path.join('uploads', filename)):
                counter = 2
                while True:
                    new_filename = f"{base}_{counter}{ext}"
                    if not os.path.exists(os.path.join('uploads', new_filename)):
                        filename = new_filename
                        break
                    counter += 1

            file.save(os.path.join('uploads', filename))
            success_count += 1
        
        if success_count > 0:
            message = _("File successfully uploaded") if success_count == 1 else f'{success_count} {_("files uploaded")}'
            
            # If this is AJAX request, return json
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {'success': True, 'message': message}
            
            flash(message, 'success')
            return redirect(url_for('files.files'))
    if USE_CLOUDFLARE_BYPASS:
        from utils.auth_bypass import generate_access_token
        return render_template('upload.html', UPLOAD_DOMAIN=UPLOAD_DOMAIN, access_token=generate_access_token(3600))
    else:
        return render_template('upload.html')
    
@files_bp.route('/upload-bypass', methods=['POST', 'OPTIONS'])
def upload_bypass():
    if not USE_CLOUDFLARE_BYPASS:
        abort(404)

    from utils.auth_bypass import verify_access_token

    token = request.args.get('access_token')
    if not token or not verify_access_token(token):
        abort(401)  # Unauthorized access

    CORS_HEADERS = {'Access-Control-Allow-Origin': f"https://{DOMAIN}",
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Max-Age': '86400'}
    
    if request.method == 'OPTIONS':
        return '', 200, CORS_HEADERS
    
    # Check if there is a file in the request
    if 'file' not in request.files:
        return {'success': False, 'message': '_("No file selected")'}, 400, CORS_HEADERS
    
    files = request.files.getlist('file')
    
    if not files or files[0].filename == '':
        return {'success': False, 'message': '_("No file selected")'}, 400, CORS_HEADERS
    
    from utils.security import secure_filename_with_cyrillic
    
    success_count = 0
    for file in files:
        original_filename = secure_filename_with_cyrillic(file.filename)

        base, ext = os.path.splitext(original_filename)
        filename = original_filename

        # If the file exists, add the suffix (2), (3), etc.
        if os.path.exists(os.path.join('uploads', filename)):
            counter = 2
            while True:
                new_filename = f"{base}_{counter}{ext}"
                if not os.path.exists(os.path.join('uploads', new_filename)):
                    filename = new_filename
                    break
                counter += 1

        file.save(os.path.join('uploads', filename))
        success_count += 1
    
    if success_count > 0:
        message = _("File successfully uploaded") if success_count == 1 else f'{success_count} {_("files uploaded")}'
        return {'success': True, 'message': message}, 200, CORS_HEADERS



@files_bp.route('/download/<filename>/<file_hash>')
def download_file(filename, file_hash):
    try:
        # Divide the hash and validity period
        signature, expiration = file_hash.split('-')
        
        # We check the validity period
        current_time = int(time.time())
        if current_time > int(expiration):
            abort(410)
        
        # We generate a hash again for verification
        expected_hash = generate_download_hash(filename, current_app.config['SECRET_KEY'], expires_at=int(expiration))
        expected_signature = expected_hash.split('-')[0]
        
        # Compare hashs
        if signature != expected_signature:
            abort(403)
        
        preview_mode = request.args.get('preview', 'false').lower() == 'true'
        
        # Проверяем существование файла
        file_path = os.path.join(current_app.root_path, 'uploads', filename)
        if not os.path.exists(file_path):
            logger.error(f"File not found: {filename}")
            abort(404)
        
        response = send_from_directory(
            'uploads',
            filename,
            as_attachment=not preview_mode,
            mimetype='application/pdf' if filename.lower().endswith('.pdf') else None
        )
        
        if filename.lower().endswith('.pdf'):
            # Coding the file name in the Content-Disposition title
            encoded_filename = urllib.parse.quote(filename)
            
            if preview_mode:
                response.headers['Content-Disposition'] = f'inline; filename="{encoded_filename}"'
            else:
                response.headers['Content-Disposition'] = f'attachment; filename="{encoded_filename}"'
        
        return response
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        abort(404)

@files_bp.route('/bulk_download', methods=['POST'])
@login_required
def bulk_download():
    from utils.files import cleanup_temp_files
    try:
        # We get a list of files from the form
        files = request.form.getlist('files')
        
        if not files:
            flash(_('No files selected for download'), 'warning')
            return redirect(url_for('files.files'))
        
        # If only one file is selected, we redirect the direct download
        if len(files) == 1:
            return redirect(url_for('files.download_file', filename=files[0]))
        
        # For many files we create a temporary archive
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, 'files.zip')
        
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in files:
                file_path = os.path.join('uploads', file)
                if os.path.exists(file_path):
                    zipf.write(file_path, file)

        # We send the archive to the client
        response = send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name='files.zip'
        )

        # Add a headers for tracking the deletion
        # We do not delete the file immediately, but mark it for subsequent cleaning
        response.headers['X-Temp-Dir'] = temp_dir
        response.headers['X-Zip-Path'] = zip_path

        # We use flask-specific functionality to close the connection
        response.call_on_close(lambda: cleanup_temp_files(temp_dir, zip_path))
        
        return response
    
    except Exception as e:
        logger.error(f"Mass download error: {str(e)}")
        flash(_('An error occurred while preparing files for download'), 'danger')
        return redirect(url_for('files.files'))

@files_bp.route('/delete/<filename>', methods=['POST'])
@login_required
def delete_file(filename):
    try:
        file_path = os.path.join('uploads', filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f"{gettext('File')} {filename} {gettext('deleted')}", 'success')
        else:
            flash(f"{gettext('File')} {filename} {gettext('not found')}", 'danger')
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        flash(_('Error deleting file'), 'danger')
    
    return redirect(url_for('files.files'))

@files_bp.route('/bulk_delete', methods=['POST'])
@login_required
def bulk_delete():
    try:
        # We get a list of files from the form
        files = request.form.getlist('files')
        
        if not files:
            flash(_('No files selected for deletion'), 'warning')
            return redirect(url_for('files.files'))
        
        successful = 0
        failed = 0
        
        # We delete each file
        for filename in files:
            file_path = os.path.join('uploads', filename)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Error deleting file {filename}: {str(e)}")
                failed += 1
        
        # We display a message about the result of the operation
        if successful > 0 and failed == 0:
            flash(f"{gettext('Successfully deleted')} {successful} {gettext('files')}", 'success')
        elif successful > 0 and failed > 0:
            flash(f"{gettext('Deleted')} {successful} {gettext('files, failed to delete')} {failed} {gettext('files')}", 'warning')
        else:
            flash(_('Failed to delete selected files'), 'danger')
            
        return redirect(url_for('files.files'))
        
    except Exception as e:
        logger.error(f"Error during bulk deletion: {str(e)}")
        flash(_('An error occurred while deleting files'), 'danger')
        return redirect(url_for('files.files'))