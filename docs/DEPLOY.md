# Deploying BatchZero

BatchZero ships as **one container**: FalkorDB, the FastAPI agent, its MCP
subprocesses, and the compiled React UI. There is no external database to
provision and no API key required — the deterministic plan drives every tool
call against the graph.

- Image: [`deploy/Dockerfile`](../deploy/Dockerfile) (runtime base is the official
  `falkordb/falkordb` image, Debian 13)
- Entrypoint: [`deploy/start.sh`](../deploy/start.sh) — starts FalkorDB, waits for
  `PONG`, seeds both tenants (idempotent `MERGE`s), then serves the API + UI
- The API binds `$PORT` when the platform provides one (Render sets `PORT`),
  otherwise `8000`, and serves the UI at `/`
- Health check: `GET /api/health` → `{"ok": true, "falkordb": true, ...}`

## Run the container locally

```bash
docker build -f deploy/Dockerfile -t batchzero .
docker run --rm -p 8000:8000 batchzero
# then open http://localhost:8000
```

Proof it works end to end inside the image:

```bash
docker run --rm batchzero python -m batchzero.demo.replay --benchmark 3
# correct source identification: 3/3
```

## Render (free tier, no credit card)

The repo includes [`render.yaml`](../render.yaml) as a blueprint for a single
free web service in the Singapore region.

**Blueprint route**

1. Sign up at <https://render.com> (no card needed for free instances).
2. **New → Blueprint**, pick this repository, approve.
3. Render builds `deploy/Dockerfile` and starts the service. First build takes a
   few minutes; the container seeds 134 nodes / 197 relationships on boot.

**Manual route** (if the blueprint UI changes)

1. **New → Web Service** → connect this repository.
2. Language: **Docker**. Dockerfile path: `deploy/Dockerfile`. Docker context: `.`
3. Instance type: **Free**. Region: **Singapore**.
4. Health check path: `/api/health`.
5. Optional environment variables:

   | Key | Value | Why |
   | --- | --- | --- |
   | `LLM_PROVIDER` | `mock` | Default: deterministic replay, no key, never fails |
   | `GROQ_API_KEY` | `gsk_…` | Switches the same loop to the live LLM |
   | `TENANT_GRAPH` | `pmph_ops` | FalkorDB graph for the Port Meridian district |

## What to expect on the free tier

- **Cold start.** Free instances spin down after ~15 minutes without traffic and
  take roughly a minute to wake on the next request. The container reseeds itself
  on every boot, so the demo is always in a known state.
- **No persistent disk.** State does not survive a restart — which is fine here:
  the fixture is deterministic and rebuilt on boot.
- **750 instance hours/month.** One service that sleeps while idle stays well
  inside the allowance.
- **Graph engine is in-process.** `LLM_PROVIDER=mock` still executes 50 real MCP
  tool calls against the embedded FalkorDB, so the graph work in the demo is the
  same code path as production.

## Live LLM mode

Set `GROQ_API_KEY` and the orchestrator drives the same four roles through the
same MCP tool-sets using a model instead of the scripted plan; if the provider
errors or rate-limits, the loop falls back to the deterministic plan mid-session
(`backend/batchzero/agent/llm.py`).

## Other hosts

Anything that runs a container works — the entrypoint only needs a writable
filesystem and one open port:

- **Docker Compose** (dev/prod, separate services + a volume): `docker compose up --build -d`
- **Fly.io**: one app with two machines (this image + `falkordb/falkordb` with a
  volume), or the same single-container image pinned to a volume-backed machine.
- **Railway / Koyeb / Cloud Run**: deploy the image and set `PORT` per the
  platform's convention; `deploy/start.sh` reads it.
