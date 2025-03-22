import os
import time
from utils.logging_config import configure_logging
import logging

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
