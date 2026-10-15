FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# pyproject's readme points at ../README.md relative to the backend package.
COPY README.md ./README.md
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/batchzero ./backend/batchzero

RUN pip install --no-cache-dir -e ./backend

EXPOSE 8000
CMD ["python", "-m", "batchzero.api.app"]
