import base64
import hmac
import hashlib
import time
from config import SECRET_KEY

# Function for creating a temporary access token
def generate_access_token(expiry_seconds=3600):
    # Currently in seconds
    timestamp = int(time.time())
    # Token expiration time
    expiry = timestamp + expiry_seconds
    
    # Data for the signature
    data = f"{timestamp}:{expiry}"
    
    # Create HMAC using SHA-256
    signature = hmac.new(
        key=SECRET_KEY.encode('utf-8'),
        msg=data.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    
    # We encode in Base64 and combine with data
    signature_b64 = base64.urlsafe_b64encode(signature).decode('utf-8')
    token = f"{data}:{signature_b64}"
    
    # Coding the entire token in Base64 for the convenience of transfer
    return base64.urlsafe_b64encode(token.encode('utf-8')).decode('utf-8')

# Function to check token
def verify_access_token(token):
    try:
        # We decode token from Base64
        decoded = base64.urlsafe_b64decode(token.encode('utf-8')).decode('utf-8')
        
        # We divide into parts
        parts = decoded.split(':')
        if len(parts) != 3:
            return False
            
        timestamp, expiry, signature = parts
        
        # We check the validity period
        current_time = int(time.time())
        if current_time > int(expiry):
            return False
            
        # We will recreate the signature for verification
        data = f"{timestamp}:{expiry}"
        expected_signature = hmac.new(
            key=SECRET_KEY.encode('utf-8'),
            msg=data.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        
        expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).decode('utf-8')
        
        # Compare the signatures
        return signature == expected_signature_b64
    except Exception:
        return False