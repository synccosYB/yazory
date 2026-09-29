"""Shared server settings for Replit Run and published deployments."""

# Provider requests can block for seconds. Keep other pages and health checks
# responsive while they wait, without creating a large database connection pool.
workers = 2
worker_class = 'gthread'
threads = 4
timeout = 60
graceful_timeout = 30
keepalive = 5

# Recycle workers periodically to bound memory growth; stagger their restarts.
max_requests = 1000
max_requests_jitter = 100
