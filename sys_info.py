import datetime
import time

# Application start time
app_start_time = time.time()

def get_datetime():
    """Return current date and time combined as 'YYYY-MM-DD HH:MM:SS'"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_app_uptime():
    """Return the application uptime as a human-readable string"""
    elapsed = time.time() - app_start_time
    hours, rem = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}h {minutes}m {seconds}s"


