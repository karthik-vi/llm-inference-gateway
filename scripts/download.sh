#!/usr/bin/env bash
# Downloads models + data into gitignored dirs. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models data vendor
HF=https://huggingface.co
fetch() { [ -s "$2" ] || curl -sSL --fail -o "$2" "$1"; }
fetch $HF/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf models/qwen2.5-0.5b-instruct-q4_k_m.gguf
fetch $HF/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf models/qwen2.5-1.5b-instruct-q4_k_m.gguf
fetch $HF/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset/resolve/main/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv data/bitext.csv
[ -d vendor/llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp vendor/llama.cpp
[ -x vendor/llama.cpp/build/bin/llama-server ] || (cd vendor/llama.cpp && cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=OFF >/dev/null && cmake --build build -j4 --target llama-server)
# Phase 2e quantization variants (F16 of the 1.5B model is ~3 GB, over the 2 GB rule: skipped)
fetch $HF/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q8_0.gguf models/qwen2.5-0.5b-instruct-q8_0.gguf
fetch $HF/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-fp16.gguf models/qwen2.5-0.5b-instruct-fp16.gguf
fetch $HF/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q8_0.gguf models/qwen2.5-1.5b-instruct-q8_0.gguf
