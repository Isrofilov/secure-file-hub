import re
from utils.logging_config import configure_logging
import logging

logger = logging.getLogger(__name__)

def validate_domains(main_domain, upload_domain):
    # Checks the validity of domain names and their mismatch.
    # If the domains are not indicated (empty lines), considers them valid.
    #
    # Args:
    #     main_domain: the main domain of the application
    #     upload_domain: Domain for uploading files
    #   
    # Returns:
    #     tuple: (main_domain, upload_domain) after validation,
    #            Empty lines if the values ​​are unequal

    # Regular expression to verify domain validity
    domain_pattern = re.compile(r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$')
    
    # If the main domain is indicated, check its validity
    if main_domain and not domain_pattern.match(main_domain):
        logger.warning(f"Main domain '{main_domain}' is not a valid domain name")
        main_domain = ''
    
    # If the upload domain is indicated, check its validity
    if upload_domain and not domain_pattern.match(upload_domain):
        logger.warning(f"Upload domain '{upload_domain}' is not a valid domain name")
        upload_domain = ''
    
    # Check for domains, if both are indicated
    if main_domain and upload_domain and main_domain == upload_domain:
        logger.warning("Main domain and upload domain are the same, domains are reset")
        main_domain = ''
        upload_domain = ''
    
    return main_domain, upload_domain
