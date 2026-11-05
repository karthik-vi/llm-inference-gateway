# Data and models

| Asset | Source | License | Use |
|---|---|---|---|
| Qwen2.5-0.5B-Instruct Q4_K_M GGUF | huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF | Apache-2.0 | serving |
| Qwen2.5-1.5B-Instruct Q4_K_M GGUF | huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF | Apache-2.0 | downloaded; unused so far |
| Bitext customer-support dataset (26,872 rows, 27 intents) | huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset | CDLA-Sharing-1.0 (confirmed from the dataset card, 2026-11-05) | workload |
| BAAI/bge-small-en-v1.5 (via fastembed, ONNX) | huggingface.co/BAAI/bge-small-en-v1.5 | MIT | semantic cache embeddings |
| tau-bench retail DB, policy (users/orders/products.json, wiki.md) | github.com/sierra-research/tau-bench | MIT | agent backend + policy retrieval (tasks are generated here, not the official tau-bench tasks) |
| faiss-cpu, fastembed | PyPI | MIT / Apache-2.0 | cache index / embedding runtime |
| Qwen2.5 0.5B/1.5B Q8_0 and F16 GGUF | same Qwen repos | Apache-2.0 | quantization comparison |
| llama.cpp | github.com/ggml-org/llama.cpp (built from source, vendor/) | MIT | replicas |

**Synthetic sessions:** Bitext is single-turn. `workloads/trace.py` builds multi-turn sessions (1-4 turns, same category) by chaining rows; earlier rows' responses are used as assistant history. Placeholders like `{{Order Number}}` are filled with random values. Seeded (seed 0).
