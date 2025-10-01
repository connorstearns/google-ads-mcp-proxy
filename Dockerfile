# Dockerfile
FROM python:3.11-slim

# Security+speed basics
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps (mostly for faster wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app
COPY . .

# Cloud Run listens on $PORT
ENV PORT=8080
EXPOSE 8080

# Start the FastAPI proxy (module: main.app)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
