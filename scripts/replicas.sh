#!/usr/bin/env bash
# Usage: scripts/replicas.sh start|stop   (reads config.yaml via python)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
if [ "${1:-}" = stop ]; then pkill -f "llama-server" || true; exit 0; fi
eval "$($PY - <<'PYEOF'
from gateway.config import load_settings
s = load_settings(); l = s.llama
m = l.model_small if l.model == "small" else l.model_large
print(f'BIN={l.server_bin} MODEL={m} T={l.threads_per_replica} P={l.parallel_slots} C={l.ctx_per_slot}')
print('PORTS="' + " ".join(r.url.rsplit(":",1)[1] for r in s.replicas) + '"')
PYEOF
)"
mkdir -p logs; i=0
for port in $PORTS; do
  nohup $BIN -m $MODEL --host 127.0.0.1 --port $port -t $T -np $P -c $((C*P)) \
    --cont-batching --cache-prompt > logs/replica$i.log 2>&1 &
  i=$((i+1))
done
for port in $PORTS; do
  for _ in $(seq 60); do curl -sf http://127.0.0.1:$port/health >/dev/null && break; sleep 1; done
done
echo "replicas up: $PORTS"
