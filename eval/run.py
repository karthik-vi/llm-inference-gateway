"""Run the eval suite against a gateway. Usage: python -m eval.run --tag NAME [--url ...]"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np

from eval.agent import Result, run_task
from eval.backend import Backend


def http_llm(url: str):
    client = httpx.Client(timeout=300)

    def llm(msgs: list[dict]) -> tuple[str, int, int]:
        r = client.post(f"{url}/v1/chat/completions", json={
            "messages": msgs, "max_tokens": 160, "temperature": 0.0, "seed": 0}).json()
        u = r.get("usage", {})
        return r["choices"][0]["message"]["content"], u.get("prompt_tokens", 0), \
            u.get("completion_tokens", 0)
    return llm


def summarize(rs: list[Result]) -> dict:
    out: dict = {"n": len(rs), "success": float(np.mean([r.success for r in rs]))}
    for t in ("lookup", "cancel", "policy"):
        x = [r for r in rs if r.type == t]
        out[f"success_{t}"] = float(np.mean([r.success for r in x])) if x else None
    va = sum(r.tool_valid for r in rs)
    at = sum(r.tool_attempted for r in rs)
    out["tool_validity"] = va / at if at else None
    g = [r.grounded for r in rs if r.grounded is not None]
    out["grounding"] = float(np.mean(g)) if g else None
    out["calls_mean"] = float(np.mean([r.calls for r in rs]))
    out["tokens_mean"] = float(np.mean([r.prompt_tokens + r.completion_tokens for r in rs]))
    lat = [r.latency_s for r in rs]
    out["latency_p50_s"], out["latency_p95_s"] = (float(np.percentile(lat, p)) for p in (50, 95))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--tasks", default="data/tau_tasks.jsonl")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    tasks = [json.loads(line) for line in open(a.tasks)]
    tasks = tasks[:a.limit] if a.limit else tasks
    policy = open("data/tau/wiki.md").read()
    llm = http_llm(a.url)
    base = Backend.load()

    def one(t: dict) -> Result:
        return run_task(t, llm, Backend(base.users, base.orders), policy)  # fresh DB per task
    with ThreadPoolExecutor(a.workers) as ex:
        rs = list(ex.map(one, tasks))
    s = summarize(rs)
    json.dump({"tag": a.tag, "summary": s, "results": [r.__dict__ for r in rs]},
              open(f"results/eval_{a.tag}.json", "w"), indent=1)
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()}))
