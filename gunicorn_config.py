import multiprocessing
import os

# Use PORT environment variable for Render compatibility
port = os.getenv("PORT", "8000")

# Bind to 0.0.0.0 to make the server available externally
bind = f"0.0.0.0:{port}"

# Use the recommended number of workers based on CPU cores
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"

# Increase timeout for long-running processes
timeout = 120

# Configure logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"

# Disable daemon mode (required for containerized apps)
daemon = False

# Recommended settings for containerized apps
forwarded_allow_ips = "*"
proxy_allow_ips = "*" 