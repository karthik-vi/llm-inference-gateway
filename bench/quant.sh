#!/usr/bin/env bash
# Phase 2e: prompt-processing (pp256) and token-generation (tg32) tokens/s per model x quant, 2 threads.
set -euo pipefail
cd "$(dirname "$0")/.."
out=results/quant_bench.csv; rm -f $out
for m in models/*.gguf; do
  vendor/llama.cpp/build/bin/llama-bench -m $m -t 2 -p 256 -n 32 -r 3 -o csv 2>/dev/null | { read -r h; [ -f $out ] || echo "$h" > $out; cat >> $out; }
done
