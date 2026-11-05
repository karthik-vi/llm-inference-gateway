# Data and models

| Asset | Source | License | Use |
|---|---|---|---|
| Qwen2.5-0.5B-Instruct Q4_K_M GGUF | huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF | Apache-2.0 | serving |
| Qwen2.5-1.5B-Instruct Q4_K_M GGUF | huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF | Apache-2.0 | downloaded; unused so far |
| Bitext customer-support dataset (26,872 rows, 27 intents) | huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset | CDLA-Sharing-1.0 (per dataset card; verify before redistribution) | workload |
| llama.cpp | github.com/ggml-org/llama.cpp (built from source, vendor/) | MIT | replicas |

**Synthetic sessions:** Bitext is single-turn. `workloads/trace.py` builds multi-turn sessions (1-4 turns, same category) by chaining rows; earlier rows' responses are used as assistant history. Placeholders like `{{Order Number}}` are filled with random values. Seeded (seed 0).
