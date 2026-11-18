# Stage 1: Build Next.js static frontend
FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /app/frontend
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@latest --activate
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install || pnpm install --no-frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# Stage 2: Python runtime
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    USE_TF=0 \
    USE_TORCH=1 \
    TF_ENABLE_ONEDNN_OPTS=0

# Install required system libraries for OpenCV, RapidOCR, PyMuPDF, and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for Docker layer caching
COPY requirements-lock.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements-lock.txt

# Copy backend source code
COPY . .

# Copy static frontend export from build stage
COPY --from=frontend-builder /app/frontend/out ./frontend/out

# Register application package in editable/local mode
RUN pip install -e . --no-deps

# Create persistence and cache directories
RUN mkdir -p data models .cache tools

# Expose API and web application port
EXPOSE 8000

# Healthcheck targeting RFC 9457 compliant system health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Launch FastAPI with Uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
