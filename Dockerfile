FROM python:3.12-slim

WORKDIR /app

# Install only the runtime dependencies needed by the API
COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi==0.129.0 \
    uvicorn==0.41.0 \
    "psycopg[binary]==3.2.9" \
    psycopg-pool==3.3.0 \
    httpx==0.28.1 \
    atproto \
    tweepy

# Copy application code
COPY api/ api/
COPY frontend/ frontend/
COPY scripts/ scripts/

EXPOSE 8000

CMD uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}
