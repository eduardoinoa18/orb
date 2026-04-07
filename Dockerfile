# ── ORB Platform Dockerfile ───────────────────────────────────────────────────
# Production-ready single-worker image with health check and non-root user
FROM python:3.12-slim

# System packages (needed for some pip builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r orbuser && useradd -r -g orbuser orbuser

WORKDIR /app

# Install dependencies first (layer cache optimization)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create artifact directories and fix permissions
RUN mkdir -p artifacts/screenshots config/agent_configs \
    && chown -R orbuser:orbuser /app

# Drop root privileges
USER orbuser

EXPOSE 8000

# Docker-level health check (Railway also uses its own)
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Single worker — background schedulers (Aria, Sage) must not be duplicated
# Railway injects $PORT; fall back to 8000 locally
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --log-level info"]
