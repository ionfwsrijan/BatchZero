# BatchZero — single-container deployment image (API + built UI + FalkorDB).
#
#   docker build -f deploy/Dockerfile -t batchzero .
#   docker run --rm -p 8000:8000 batchzero
#
# The runtime stage is the official FalkorDB image (Debian 13), so the graph
# engine ships inside the same container: one service to deploy, no external
# database to wire up. The FastAPI app serves the compiled React UI, and spawns
# its MCP servers as stdio subprocesses from the same venv.

FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM falkordb/falkordb:latest

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    BROWSER=0 \
    LLM_PROVIDER=mock \
    TENANT_GRAPH=pmph_ops \
    TRAINING_TENANT_GRAPH=training_academy

# The base image also carries the bundled Browser UI (node); this deployment
# serves the BatchZero UI instead, so drop it to keep the image small.
RUN rm -rf /var/lib/falkordb/browser /usr/local/bin/node

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip

WORKDIR /app
COPY README.md ./README.md
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/batchzero ./backend/batchzero
RUN /opt/venv/bin/pip install -e ./backend

COPY --from=ui /ui/dist ./frontend/dist
COPY deploy/start.sh /usr/local/bin/batchzero-start
RUN sed -i 's/\r$//' /usr/local/bin/batchzero-start \
    && chmod +x /usr/local/bin/batchzero-start

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/batchzero-start"]
