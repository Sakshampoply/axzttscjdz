FROM node:22-bookworm-slim AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.0 AS uv

FROM python:3.12-slim-bookworm AS backend
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8080
RUN useradd --create-home --uid 10001 appuser
USER appuser

FROM backend AS worker
CMD ["python", "-m", "app.cli", "worker"]

FROM backend AS web
COPY --from=ui /src/frontend/dist/ ./frontend/dist/
EXPOSE 8080
CMD ["python", "-m", "app.serve"]
