FROM node:24-alpine AS web
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_API_BASE_URL=""
ENV VITE_RENDER_DEMO=true
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production COOKIE_SECURE=1 UPLOAD_DIR=/tmp/demo-uploads
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ ./
COPY hosting/ ./hosting/
COPY --from=web /build/dist/ ./demo-static/
RUN useradd --system --no-create-home --shell /usr/sbin/nologin demo
USER demo
EXPOSE 10000
CMD ["python", "-m", "hosting.start"]
