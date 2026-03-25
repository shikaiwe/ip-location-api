FROM python:3.11-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip && pip install -e .

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY --from=builder /app /app
COPY data/ ./data/

EXPOSE 8000

ENV WORKERS=1

CMD ["sh", "-c", "if [ \"$WORKERS\" -gt 1 ]; then pip install --no-cache-dir gunicorn && exec gunicorn ip_location_api.main:app --bind 0.0.0.0:8000 --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker; else exec python -m uvicorn ip_location_api.main:app --host 0.0.0.0 --port 8000; fi"]
