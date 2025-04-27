import hmac
import time

def generate_download_hash(filename, secret_key, expires_at=None):
    """Generates a hash to protect the download link
    
    Args:
        filename: file name to download
        secret_key: application secret key
        expires_at: link expiration time in seconds (optional)
    """
    # Add salt that will change over time
    current_time = int(time.time())
    expiration = expires_at or (current_time + 3600)  # Default 1 hour
    
    # Create a line with data, including the expiration time
    data_to_hash = f"{filename}|{expiration}"
    
    # We use HMAC for safer hash
    signature = hmac.new(
        secret_key.encode(),
        data_to_hash.encode(),
        digestmod='sha256'
    ).hexdigest()
    
    # Return the signature and validity period
    return f"{signature[:16]}-{expiration}"
