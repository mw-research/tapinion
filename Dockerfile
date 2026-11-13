# Tapinion server image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DB_PATH=/data/tapinion.sqlite3

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY tapinion ./tapinion
RUN pip install --no-cache-dir . && \
    useradd --uid 1000 --create-home tapinion && mkdir -p /data && chown tapinion /data

USER tapinion
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
# Behind a reverse proxy, trust its X-Forwarded-* headers (adjust if the proxy is elsewhere).
CMD ["tapinion", "serve", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
