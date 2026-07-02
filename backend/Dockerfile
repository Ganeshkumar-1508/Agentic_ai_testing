# TestAI Harness - Python Backend
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libpq-dev \
    docker.io \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/* \
    && docker pull alpine:3.19 2>/dev/null || true \
    && (curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh) || true

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 -r requirements.txt \
    && playwright install chromium

COPY . .

# Docker socket on Windows mounts as root:root — run as root for sandbox access.
# RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
# USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# workers=1: FastAPI is async — concurrency is handled via the event loop,
# not process count. Multi-worker (--workers N) only helps for CPU-bound
# work. Our bottleneck is I/O (LLM calls, Docker, DB), which async handles
# perfectly. Additionally, asyncpg connection pools are not fork-safe —
# pooled connections share TCP file descriptors across processes, causing
# concurrent access corruption (ConnectionDoesNotExistError).
# Use workers>1 only with gunicorn + UvicornWorker which handles pre-fork properly.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
