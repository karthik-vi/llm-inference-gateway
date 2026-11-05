#!/usr/bin/env bash
# Usage: scripts/replicas.sh start|stop   (reads config.yaml via python)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
if [ "${1:-}" = stop ]; then pkill -f "llama-server" || true; exit 0; fi
eval "$($PY - <<'PYEOF'
from gateway.config import load_settings
s = load_settings(); l = s.llama
print(f'BIN={l.server_bin} T={l.threads_per_replica} P={l.parallel_slots} C={l.ctx_per_slot}')
spec = []
for r in s.replicas:
    m = l.model_small if r.tier == "small" else l.model_large
    spec.append(r.url.rsplit(":", 1)[1] + ":" + m)
print('SPEC="' + " ".join(spec) + '"')
print('PORTS="' + " ".join(r.url.rsplit(":", 1)[1] for r in s.replicas) + '"')
PYEOF
)"
mkdir -p logs; i=0
for sp in $SPEC; do
  port=${sp%%:*}; MODEL=${sp#*:}
  nohup $BIN -m $MODEL --host 127.0.0.1 --port $port -t $T -np $P -c $((C*P)) \
    --cont-batching --cache-prompt --metrics > logs/replica$i.log 2>&1 &
  i=$((i+1))
done
for port in $PORTS; do
  for _ in $(seq 60); do curl -sf http://127.0.0.1:$port/health >/dev/null && break; sleep 1; done
done
echo "replicas up: $PORTS"
