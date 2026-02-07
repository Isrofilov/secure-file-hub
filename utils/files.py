import os
import time
import logging

from utils.security import secure_filename_with_cyrillic

logger = logging.getLogger(__name__)

def cleanup_temp_files(temp_dir, zip_path):
    try:
        # A small delay before deleting to make sure that the file is no longer used
        time.sleep(0.5)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
    except Exception as e:
        logger.error(f"Error when deleting temporary files: {str(e)}")

def save_uploaded_files(files, upload_folder):
    """Save uploaded files to the upload folder, handling duplicates.

    Returns the number of successfully saved files.
    """
    success_count = 0
    for file in files:
        original_filename = secure_filename_with_cyrillic(file.filename)

        base, ext = os.path.splitext(original_filename)
        filename = original_filename

        # If the file exists, add the suffix _2, _3, etc.
        if os.path.exists(os.path.join(upload_folder, filename)):
            counter = 2
            while True:
                new_filename = f"{base}_{counter}{ext}"
                if not os.path.exists(os.path.join(upload_folder, new_filename)):
                    filename = new_filename
                    break
                counter += 1

        file.save(os.path.join(upload_folder, filename))
        success_count += 1
    return success_count
