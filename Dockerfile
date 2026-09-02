# Sentinel Autonomous Software Testing Agent Harness
# Production Container Image

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for ultra-fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy project definition
COPY pyproject.toml .
COPY README.md* .

# Install dependencies into system environment
RUN uv pip install --system -e .

# Copy application source code
COPY sentinel/ sentinel/
COPY examples/ examples/

# Create directories for persistent data
RUN mkdir -p /app/data /app/reports /app/artifacts

# Expose default dashboard port
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    SENTINEL_DB_PATH=/app/data/sentinel_memory.sqlite

# Default entrypoint starts the Web Dashboard
CMD ["python", "-m", "sentinel.cli", "dashboard", "--port", "8080", "--db", "/app/data/sentinel_memory.sqlite"]
