"""Poisson session-arrival load generator (per-request TTFT/ITL/e2e/tokens/status/replica)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import time
from dataclasses import asdict, dataclass

import httpx
import numpy as np

from workloads.trace import load


@dataclass
class Rec:
    session: int
    turn: int
    t_start: float
    ttft: float
    itl_mean: float
    e2e: float
    prompt_tokens: int
    completion_tokens: int
    status: str
    replica: str
    prefill_tokens: int = 0   # prompt tokens actually recomputed (timings.prompt_n)
    cached_tokens: int = 0


async def one_request(client: httpx.AsyncClient, url: str, turn: dict, sid: int, t_zero: float,
                      timeout: float, model: str) -> Rec:
    body = {"model": model, "messages": turn["messages"], "max_tokens": turn["max_tokens"],
            "temperature": 0.0, "stream": True, "stream_options": {"include_usage": True}}
    t0 = time.perf_counter()
    ttft, last, gaps, pt, ct, status, rep = -1.0, None, [], 0, 0, "ok", ""
    pn = cn = 0
    try:
        async with client.stream("POST", f"{url}/v1/chat/completions", json=body,
                                 timeout=timeout) as r:
            rep = r.headers.get("x-replica", "")
            if r.status_code != 200:
                status = f"http_{r.status_code}"
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data:") or "[DONE]" in line:
                        continue
                    obj = json.loads(line[5:])
                    if obj.get("usage"):
                        pt = obj["usage"].get("prompt_tokens", 0)
                        ct = obj["usage"].get("completion_tokens", 0)
                    if obj.get("timings"):
                        pn = obj["timings"].get("prompt_n", 0)
                        cn = obj["timings"].get("cache_n", 0)
                    ch = obj.get("choices") or []
                    if ch and (ch[0].get("delta") or {}).get("content"):
                        now = time.perf_counter()
                        if ttft < 0:
                            ttft = now - t0
                        else:
                            gaps.append(now - last)
                        last = now
    except httpx.TimeoutException:
        status = "timeout"
    except httpx.HTTPError:
        status = "error"
    return Rec(sid, turn["turn"], t0 - t_zero, ttft, float(np.mean(gaps)) if gaps else 0.0,
               time.perf_counter() - t0, pt, ct, status, rep, pn, cn)


async def run(url: str, sessions: list[dict], rate_rps: float, duration_s: float,
              think_s: float, timeout: float, seed: int, model: str = "qwen") -> list[Rec]:
    """rate_rps is the *request* rate; session arrival rate = rate / mean turns per session."""
    rng = random.Random(seed)
    mean_turns = float(np.mean([len(s["turns"]) for s in sessions]))
    sess_rate = rate_rps / mean_turns
    recs: list[Rec] = []
    t_zero = time.perf_counter()

    async def session(s: dict, client: httpx.AsyncClient) -> None:
        for turn in s["turns"]:
            recs.append(await one_request(client, url, turn, s["session_id"], t_zero, timeout,
                                          model))
            if recs[-1].status != "ok":
                return
            await asyncio.sleep(rng.expovariate(1 / think_s) if think_s > 0 else 0)

    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=1024)) as client:
        tasks, t, i = [], 0.0, 0
        while t < duration_s:
            t += rng.expovariate(sess_rate)
            delay = t - (time.perf_counter() - t_zero)
            if delay > 0:
                await asyncio.sleep(delay)
            tasks.append(asyncio.create_task(session(sessions[i % len(sessions)], client)))
            i += 1
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout + 30)
            for t in pending:  # unfinished sessions at drain deadline: drop, keep recorded reqs
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    return recs


def pct(xs: list[float], p: float) -> float:
    return float(np.percentile(xs, p)) if xs else float("nan")


def summarize(recs: list[Rec], duration_s: float, slo_ttft_s: float) -> dict:
    ok = [r for r in recs if r.status == "ok" and r.ttft >= 0]
    # actual span (arrivals continue past duration_s as sessions finish their turns)
    span = (max(r.t_start + r.e2e for r in recs) - min(r.t_start for r in recs)) if recs else 1.0
    duration_s = max(span, 1e-9)
    tt = [r.ttft for r in ok]
    good = [r for r in ok if r.ttft <= slo_ttft_s]
    return {
        "span_s": span, "arrival_rps": len(recs) / duration_s,
        "n": len(recs), "ok": len(ok), "errors": len(recs) - len(ok),
        "throughput_rps": len(ok) / duration_s, "goodput_rps": len(good) / duration_s,
        "ttft_p50": pct(tt, 50), "ttft_p95": pct(tt, 95), "ttft_p99": pct(tt, 99),
        "e2e_p50": pct([r.e2e for r in ok], 50), "e2e_p95": pct([r.e2e for r in ok], 95),
        "itl_mean_p50": pct([r.itl_mean for r in ok if r.itl_mean], 50),
        "cache_hits": sum(1 for r in ok if r.replica == "cache"),
        "prefill_tokens": sum(r.prefill_tokens for r in ok),
        "cached_tokens": sum(r.cached_tokens for r in ok),
        "prompt_tokens": sum(r.prompt_tokens for r in ok),
        "completion_tokens": sum(r.completion_tokens for r in ok),
    }


def write_csv(recs: list[Rec], path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(recs[0])) if recs else ["empty"])
        w.writeheader()
        for r in recs:
            w.writerow(asdict(r))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--trace", default="data/trace.jsonl")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--duration", type=float, default=60)
    ap.add_argument("--think", type=float, default=2.0)
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--slo", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="logs/run.csv")
    a = ap.parse_args()
    rs = asyncio.run(run(a.url, load(a.trace), a.rate, a.duration, a.think, a.timeout, a.seed))
    write_csv(rs, a.out)
    print(json.dumps(summarize(rs, a.duration, a.slo), indent=1))
