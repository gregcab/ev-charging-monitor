FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DASHBOARD_HOST=0.0.0.0
ENV DASHBOARD_PORT=5000
ENV MONITOR_INTERVAL_MINUTES=5
ENV DB_PATH=/app/data/ev_monitoring.db
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/')" || exit 1

CMD ["python", "run.py"]
