import multiprocessing
import os

# Bind to 0.0.0.0 to make the server available externally
bind = "0.0.0.0:" + os.getenv("PORT", "8000")

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