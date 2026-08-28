FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install -r /tmp/requirements.txt && \
    useradd --create-home --uid 10001 investment

COPY --chown=investment:investment . /app
RUN chmod +x /app/deployment/start-api.sh /app/deployment/start-worker.sh
USER investment

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "investment_engine.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
