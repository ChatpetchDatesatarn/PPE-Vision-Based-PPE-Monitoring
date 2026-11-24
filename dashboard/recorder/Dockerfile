# Recorder v3: MQTT -> SQLite (/data/safety.db) + snapshots (/data/snapshots) + HTTP API on :8000
# Build on the target machine (Jetson = arm64, PC = amd64). Base image is already on the Jetson.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY store.py app.py ./
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('API_PORT','8000'), timeout=3)" || exit 1
CMD ["python3", "app.py"]
