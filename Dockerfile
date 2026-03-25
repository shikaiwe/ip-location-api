FROM python:3.11-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --user -e .

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY --from=builder /root/.local /root/.local
COPY data/ ./data/
COPY --from=builder /app/src ./src/

EXPOSE 8000

ENV WORKERS=1
ENV WORKER_CLASS=uvicorn.workers.UvicornWorker

CMD ["sh", "-c", "if [ \"$WORKERS\" -gt 1 ]; then pip install gunicorn && exec gunicorn ip_location_api.main:app --bind 0.0.0.0:8000 --workers $WORKERS --worker-class $WORKER_CLASS; else exec python -m uvicorn ip_location_api.main:app --host 0.0.0.0 --port 8000; fi"]
