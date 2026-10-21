FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN useradd --create-home --uid 1000 cleaner \
    && mkdir -p /config /data /logs /reports \
    && chown -R cleaner:cleaner /app /config /data /logs /reports

USER cleaner

EXPOSE 8080

CMD ["python", "-m", "app.main"]
