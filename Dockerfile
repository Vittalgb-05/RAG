# Multi-stage / clean Dockerfile for Local-First Multimodal PDF Intelligence System
# Standardized on Python 3.11 Debian Bookworm for 100% reproducible environments
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
COPY requirements.txt requirements-lock.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy source code and documentation
COPY . .

# Register application package in editable/local mode
RUN pip install -e .

# Create persistence and cache directories
RUN mkdir -p data models .cache

# Expose Streamlit frontend port
EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Launch Streamlit
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
