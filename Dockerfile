# V7.28 — Cloud Run container for Taki backend.
# Serves /api/* (live cascade trigger + status + cached brief) and the static
# frontend. The Vercel deployment is the public-facing dashboard; this image
# is self-contained so `docker run -p 8080:8080 taki` is also a one-line
# local preview path.
FROM python:3.14-slim

# Container-friendly Python defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first so layer cache survives code-only changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# App code (everything else is excluded via .dockerignore)
COPY agents/ ./agents/
COPY guardrails/ ./guardrails/
COPY services/ ./services/
COPY fixtures/ ./fixtures/
COPY frontend/ ./frontend/
COPY server.py run.py ./

# Cloud Run injects PORT=8080. server.py picks it up + binds 0.0.0.0.
ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
