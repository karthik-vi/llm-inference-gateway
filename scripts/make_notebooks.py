"""Generates notebooks/*.ipynb (kept as a script so the notebooks stay diff-able)."""
import json


def nb(cells):
    out = []
    for kind, src in cells:
        c = {"cell_type": kind, "metadata": {}, "source": src.strip("\n").splitlines(True)}
        if kind == "code":
            c.update(outputs=[], execution_count=None)
        out.append(c)
    return {"cells": out, "metadata": {"accelerator": "GPU", "colab": {"provenance": []},
            "kernelspec": {"name": "python3", "display_name": "Python 3"}},
            "nbformat": 4, "nbformat_minor": 5}


GPU = [
("markdown", """
# GPU serving benchmark (vLLM on a free Colab T4)
**NOT RUN IN THIS ENVIRONMENT** (the repo's container has no GPU). Written to be run by you.

- Runtime: ~25-35 min on a free T4. **Runtime > Change runtime type > T4 GPU**, then **Runtime > Run all**.
- What it does: replays the same Bitext-derived trace as the CPU baseline against vLLM (Qwen2.5-0.5B/1.5B-Instruct, fp16),
  profiles a short generation with `torch.profiler`, measures T4 bandwidth/GEMM as a second hardware profile for the perf model,
  and computes cost per 1k requests (CPU vs GPU).
- Output: `results/gpu_benchmark.json` and `results/hw_profile_t4.json` are downloaded at the end. Commit them into `results/`.
- Edit `REPO` below to your fork/clone URL if needed.
"""),
("code", """
REPO = "https://github.com/karthik-vi/llm-inference-gateway"
BRANCH = "claude/stoic-goldberg-2u4dpb"
!nvidia-smi
!pip -q install vllm httpx datasets pandas matplotlib
!git clone -q -b $BRANCH $REPO repo && cd repo && pip -q install -e . 
"""),
("code", """
import os, subprocess, time, json, urllib.request
os.chdir("/content/repo"); os.makedirs("data", exist_ok=True); os.makedirs("results", exist_ok=True)
# Bitext CSV (same file as scripts/download.sh) and the same trace builder (seed 0)
urllib.request.urlretrieve("https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset/resolve/main/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv", "data/bitext.csv")
from workloads.trace import build_trace, save
save(build_trace("data/bitext.csv", 400), "data/trace.jsonl")
"""),
("code", """
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"   # change to Qwen/Qwen2.5-1.5B-Instruct for the second run
srv = subprocess.Popen(["python", "-m", "vllm.entrypoints.openai.api_server", "--model", MODEL, "--dtype", "float16",
    "--max-model-len", "2048", "--enable-prefix-caching", "--port", "8000"], stdout=open("vllm.log", "w"), stderr=subprocess.STDOUT)
import httpx
for _ in range(180):
    try:
        if httpx.get("http://127.0.0.1:8000/health").status_code == 200: break
    except Exception: pass
    time.sleep(2)
print("vLLM up")
"""),
("code", """
# Replay: same Poisson load generator as the CPU baseline, same SLO (p95 TTFT <= 2.0 s), higher rates (a T4 is faster).
import asyncio
from workloads.loadgen import run, summarize
from workloads.trace import load
sessions = load("data/trace.jsonl")
results = {}
for rate in [1, 2, 4, 8, 16, 32]:
    recs = asyncio.run(run("http://127.0.0.1:8000", sessions, rate, 60, 2.0, 30, seed=1, model=MODEL))
    results[rate] = summarize(recs, 60, 2.0); print(rate, {k: round(v, 3) for k, v in results[rate].items() if "ttft" in k or "goodput" in k})
"""),
("code", """
# torch.profiler on a short generation (HF transformers, separate from the server; free GPU memory first)
srv.terminate(); time.sleep(5)
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
tok = AutoTokenizer.from_pretrained(MODEL); m = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float16).cuda()
x = tok("How do I cancel my order?", return_tensors="pt").to("cuda")
from torch.profiler import profile, ProfilerActivity
with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
    m.generate(**x, max_new_tokens=32)
top = prof.key_averages().table(sort_by="cuda_time_total", row_limit=10); print(top)
prof_text = top
"""),
("code", """
# Second hardware profile for perfmodel (same keys as results/hw_profile_cpu.json; cores=1 => per-device)
import torch, time
n = 256 * 1024 * 1024 // 4
a = torch.randn(n, device="cuda"); b = torch.randn(n, device="cuda"); c = torch.empty_like(a)
torch.cuda.synchronize(); t = time.perf_counter()
for _ in range(20): torch.add(a, b, out=c)
torch.cuda.synchronize(); bw = 20 * 3 * n * 4 / (time.perf_counter() - t) / 1e9
x = torch.randn(4096, 4096, device="cuda", dtype=torch.float16); torch.cuda.synchronize(); t = time.perf_counter()
for _ in range(20): x @ x
torch.cuda.synchronize(); gf = 20 * 2 * 4096**3 / (time.perf_counter() - t) / 1e9
hw = {"cpu": "NVIDIA T4 (Colab)", "cores": 1, "triad_GBps_numpy_1thread": round(bw, 1), "gemm_fp32_GFLOPs_blas_all_threads": round(gf, 1)}
json.dump(hw, open("results/hw_profile_t4.json", "w"), indent=1); print(hw)
"""),
("code", """
# Cost per 1k requests. ASSUMPTIONS (edit!): T4 on-demand price and the CPU instance price you compare against.
GPU_USD_PER_HR, CPU_USD_PER_HR = 0.35, 0.17   # ASSUMED list prices, not measured here
best = max((r for r, s in results.items() if s["ttft_p95"] <= 2.0), default=None)
gpu_goodput = results[best]["goodput_rps"] if best else 0.0
out = {"model": MODEL, "gpu": "T4", "slo_ttft_p95_s": 2.0, "sweep": results, "max_rate_meeting_slo": best,
       "gpu_usd_per_1k_requests": (GPU_USD_PER_HR / 3600) / gpu_goodput * 1000 if gpu_goodput else None,
       "assumed_prices_usd_per_hr": {"gpu": GPU_USD_PER_HR, "cpu": CPU_USD_PER_HR},
       "cpu_reference": "see results/RESUME_METRICS.md (4 vCPU baseline goodput 0.93 req/s at SLO)",
       "profiler_top_ops": prof_text}
json.dump(out, open("results/gpu_benchmark.json", "w"), indent=1, default=str)
from google.colab import files; files.download("results/gpu_benchmark.json"); files.download("results/hw_profile_t4.json")
"""),
]

LORA = [
("markdown", """
# LoRA fine-tune of Qwen2.5-0.5B as the cascade router / intent classifier
**NOT RUN IN THIS ENVIRONMENT** (needs a GPU). Written to be run by you on a free Colab T4.

- Runtime: ~20-30 min (train ~12 min on 4k examples, 1 epoch, plus eval and GGUF export).
- Steps: LoRA SFT on the Bitext **train split** (labels = 27 intents; 80/10/10 split, seed 0) -> evaluate on the **held-out split**
  vs the prompt-only (zero-shot) 0.5B router -> merge + export to GGUF so the gateway can load it.
- Output: `results/router_lora.json` (accuracy numbers) is downloaded at the end; commit it into `results/`.
- Optional stretch: a short GRPO run (TRL) rewarding valid tool-call JSON and the correct tool (cell guarded by `RUN_GRPO`).
"""),
("code", """
!pip -q install transformers datasets peft trl accelerate bitsandbytes pandas
import os, json, random, urllib.request
os.makedirs("results", exist_ok=True)
urllib.request.urlretrieve("https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset/resolve/main/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv", "bitext.csv")
import pandas as pd
df = pd.read_csv("bitext.csv").sample(frac=1, random_state=0).reset_index(drop=True)
n = len(df); train, val, test = df[: int(.8 * n)], df[int(.8 * n): int(.9 * n)], df[int(.9 * n):]
INTENTS = sorted(df.intent.unique()); print(len(INTENTS), "intents;", len(train), len(val), len(test))
"""),
("code", """
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
tok = AutoTokenizer.from_pretrained(MODEL); tok.padding_side = "left"
base = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float16).cuda()
PROMPT = "Classify the customer message into one intent.\\nIntents: " + ", ".join(INTENTS) + "\\nMessage: {m}\\nIntent:"

def predict(model, msgs, bs=32):
    out = []
    for i in range(0, len(msgs), bs):
        enc = tok([PROMPT.format(m=m) for m in msgs[i:i+bs]], return_tensors="pt", padding=True).to("cuda")
        g = model.generate(**enc, max_new_tokens=8, do_sample=False)
        out += [tok.decode(x[enc.input_ids.shape[1]:], skip_special_tokens=True).strip().split("\\n")[0] for x in g]
    return out

sample = test.sample(500, random_state=0)
zs = predict(base, sample.instruction.tolist())
zs_acc = sum(p == t for p, t in zip(zs, sample.intent)) / len(sample); print("prompt-only router accuracy:", zs_acc)
"""),
("code", """
from peft import LoraConfig, get_peft_model
from datasets import Dataset
from trl import SFTTrainer, SFTConfig
tr = train.sample(4000, random_state=0)
ds = Dataset.from_dict({"text": [PROMPT.format(m=m) + " " + i + tok.eos_token for m, i in zip(tr.instruction, tr.intent)]})
model = get_peft_model(base, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type="CAUSAL_LM"))
SFTTrainer(model=model, train_dataset=ds, processing_class=tok,
           args=SFTConfig(output_dir="lora_out", num_train_epochs=1, per_device_train_batch_size=16, learning_rate=2e-4,
                          logging_steps=20, fp16=True, report_to=[], dataset_text_field="text", max_length=256)).train()
"""),
("code", """
model.eval(); ft = predict(model, sample.instruction.tolist())
ft_acc = sum(p == t for p, t in zip(ft, sample.intent)) / len(sample); print("LoRA router accuracy:", ft_acc)
json.dump({"model": MODEL, "n_eval": len(sample), "split": "held-out 10% (seed 0)", "prompt_only_accuracy": zs_acc,
           "lora_accuracy": ft_acc, "train_examples": 4000, "epochs": 1}, open("results/router_lora.json", "w"), indent=1)
"""),
("code", """
# Merge + export to GGUF (llama.cpp converter), then quantize to Q4_K_M like the gateway's replicas
merged = model.merge_and_unload(); merged.save_pretrained("merged"); tok.save_pretrained("merged")
!git clone -q --depth 1 https://github.com/ggml-org/llama.cpp && pip -q install -r llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
!python llama.cpp/convert_hf_to_gguf.py merged --outfile router-f16.gguf --outtype f16
!cd llama.cpp && cmake -B build -DLLAMA_CURL=OFF -DGGML_CUDA=OFF >/dev/null && cmake --build build -j --target llama-quantize >/dev/null
!llama.cpp/build/bin/llama-quantize router-f16.gguf router-q4_k_m.gguf Q4_K_M
from google.colab import files; files.download("router-q4_k_m.gguf"); files.download("results/router_lora.json")
"""),
("code", """
RUN_GRPO = False   # stretch goal: set True to run a short GRPO job (~10 min). Reward: valid tool-call JSON + correct tool.
if RUN_GRPO:
    import re
    from trl import GRPOTrainer, GRPOConfig
    TOOLS = {"get_order_details", "cancel_pending_order", "find_user_id_by_email"}
    def reward(completions, gold_tool, **kw):
        r = []
        for c, g in zip(completions, gold_tool):
            try: o = json.loads(re.search(r"\\{.*\\}", c, re.S).group(0)); ok = o["tool"] in TOOLS and isinstance(o["args"], dict)
            except Exception: ok = False
            r.append(0.5 * ok + 0.5 * (ok and o["tool"] == g))
        return r
    prompts = [{"prompt": f"Customer: cancel my order #W{1000+i}. Reply with JSON {{\\"tool\\": ..., \\"args\\": {{...}}}}.", "gold_tool": "cancel_pending_order"} for i in range(64)]
    GRPOTrainer(model=MODEL, reward_funcs=reward, train_dataset=Dataset.from_list(prompts),
                args=GRPOConfig(output_dir="grpo_out", max_steps=30, per_device_train_batch_size=8, num_generations=4, report_to=[])).train()
"""),
]

json.dump(nb(GPU), open("notebooks/gpu_serving_benchmark.ipynb", "w"), indent=1)
json.dump(nb(LORA), open("notebooks/router_lora_finetune.ipynb", "w"), indent=1)
