#!/bin/sh
# BatchZero container entrypoint: FalkorDB -> seed -> API + UI.
set -eu

echo "[batchzero] starting FalkorDB..."
/var/lib/falkordb/bin/run.sh &

echo "[batchzero] waiting for FalkorDB..."
i=0
until redis-cli -h 127.0.0.1 -p "${FALKORDB_PORT:-6379}" ping 2>/dev/null | grep -q PONG; do
    i=$((i + 1))
    if [ "$i" -gt 60 ]; then
        echo "[batchzero] FalkorDB did not become ready" >&2
        exit 1
    fi
    sleep 1
done
echo "[batchzero] FalkorDB is up"

echo "[batchzero] seeding tenants (idempotent)..."
python -m batchzero.seed || echo "[batchzero] seed failed — serving anyway"

export API_PORT="${PORT:-8000}"
export API_HOST="${API_HOST:-0.0.0.0}"
echo "[batchzero] serving API + UI on ${API_HOST}:${API_PORT}"
exec python -m batchzero.api.app
