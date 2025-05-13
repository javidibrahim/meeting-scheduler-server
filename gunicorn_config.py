import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker processes
# For Fly.io free tier (1GB RAM), we'll use a more conservative worker count
workers = min(multiprocessing.cpu_count() + 1, 2)  # Max 2 workers for free tier
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# Timeouts
timeout = 120  # Increased for long-running async operations
keepalive = 5
graceful_timeout = 30  # Time to wait for workers to finish on shutdown

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'

# Process naming
proc_name = "meeting-scheduler-api"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None

# Worker lifecycle
max_requests = 1000  # Restart workers after this many requests
max_requests_jitter = 50  # Add randomness to max_requests
worker_tmp_dir = "/dev/shm"  # Use RAM for temporary files

# Async settings
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
keepalive = 5

# Preload app
preload_app = True

# Server hooks
def on_starting(server):
    """Log when the server is starting"""
    server.log.info("Starting meeting-scheduler-api server")

def on_exit(server):
    """Log when the server is exiting"""
    server.log.info("Stopping meeting-scheduler-api server") 