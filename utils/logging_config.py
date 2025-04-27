import os
import logging

def configure_logging():
    # We get the level of logistics from the environment variable or use INFO by default
    log_level_name = os.environ.get('LOG_LEVEL', 'INFO')
    
    # We convert a string representation of logging levels in the Loging Constant
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)
    
    # We adjust the logistics once
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Return the configured level of logistics for information
    return log_level

# Initialize logging when imported module
log_level = configure_logging()