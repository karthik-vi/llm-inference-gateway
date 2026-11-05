# Environment (recorded 2026-11-05)

| Item | Value |
|---|---|
| CPU | Intel Xeon @ 2.80GHz, 4 vCPUs (AVX2, AVX-512F, FMA) |
| RAM | 15 GiB |
| Free disk | ~30 GB (fixed per-session allowance) |
| Python | 3.13.18 system; project targets >=3.11 (uv available) |
| Toolchain | gcc/g++, cmake, make present |
| Docker | CLI present, daemon **not usable** -> Docker/compose/k8s are "not verified in this environment" |
| github.com download | works (raw.githubusercontent.com HTTP 200) |
| huggingface.co download | works (model repo and dataset repo HTTP 200) |
| GPU | none |
