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

CMD ["python", "run.py"]
