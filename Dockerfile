# ---- web build -------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- runtime ---------------------------------------------------------------
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src QVERIS_DATA_DIR=/data QVERIS_ENV=production QVERIS_HOST=0.0.0.0 QVERIS_PORT=8000
WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY config/ config/
COPY --from=web /app/web/dist web/dist
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')"
CMD ["python", "-m", "server"]
