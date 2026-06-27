# Stage 1: Build the Next.js frontend (static export -> frontend/out)
FROM node:20-slim AS frontend-builder
# Build-stage only: tolerate TLS-intercepting proxy/AV on the build host.
# Not carried into the runtime image (stage 2).
ENV NODE_TLS_REJECT_UNAUTHORIZED=0
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend (serves API + static frontend)
FROM python:3.12-slim AS app

# uv binary for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app/backend

# Install dependencies only (project code runs from source, not installed)
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --no-dev --no-install-project

# Backend source
COPY backend/ ./

# Frontend static export -> resolves to main.py's ../frontend/out (/app/frontend/out)
COPY --from=frontend-builder /app/frontend/out /app/frontend/out

# SQLite lives on the mounted volume, separate from the backend/db package
ENV DB_PATH=/app/db/finally.db
RUN mkdir -p /app/db

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
