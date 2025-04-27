import time
import threading

class RateLimiter:
    def __init__(self, max_attempts=5, window_seconds=300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts = {}
        self.lock = threading.Lock()
    
    def _cleanup(self, ip):
        current_time = time.time()
        if ip in self.attempts:
            self.attempts[ip] = [(t, s) for t, s in self.attempts[ip] if current_time - t < self.window_seconds]
            if not self.attempts[ip]:
                del self.attempts[ip]

    def add_attempt(self, ip, success=False):
        current_time = time.time()
        with self.lock:  # We use the context manager
            if ip not in self.attempts:
                self.attempts[ip] = []
            self.attempts[ip].append((current_time, success))
            self._cleanup(ip)

    def is_rate_limited(self, ip):
        current_time = time.time()
        with self.lock:  # We use the context manager
            self._cleanup(ip)
            if ip not in self.attempts:
                return False
            failed_attempts = [t for t, s in self.attempts[ip] if not s]
            return len(failed_attempts) >= self.max_attempts

    def get_remaining_time(self, ip):
        with self.lock:
            if ip not in self.attempts:
                return 0
                
            # Check the limit right here without causing is_rate_limited ()
            failed_attempts = [t for t, s in self.attempts[ip] if not s]
            if len(failed_attempts) < self.max_attempts:
                return 0
                
            current_time = time.time()
            oldest_attempt = min([t for t, s in self.attempts[ip] if not s])
            return int(self.window_seconds - (current_time - oldest_attempt))