"""Incident drill: load run with injected faults on replica r1. Usage: python -m bench.drill --tag NAME
Timeline (s): 0-40 healthy | 40 kill r1 | 80 restart r1 | 120 throttle r1 (SIGSTOP duty cycle, 30% CPU)
| 170 unthrottle | 200 end. Records load.csv, metrics.jsonl (scraped /metrics every 2 s), events.json,
spans.jsonl (gateway OTel spans) into results/drill_<tag>/."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from gateway.config import load_settings
from workloads.loadgen import run, write_csv
from workloads.trace import load

TIMELINE = {"kill": 40, "restart": 80, "throttle": 120, "unthrottle": 170, "end": 200}


def start_replica(cfg, idx: int, out: Path) -> subprocess.Popen:
    r, lc = cfg.replicas[idx], cfg.llama
    port = r.url.rsplit(":", 1)[1]
    model = lc.model_small if r.tier == "small" else lc.model_large
    return subprocess.Popen(
        [lc.server_bin, "-m", model, "--host", "127.0.0.1", "--port", port, "-t",
         str(lc.threads_per_replica), "-np", str(lc.parallel_slots), "-c",
         str(lc.ctx_per_slot * lc.parallel_slots), "--cont-batching", "--cache-prompt", "--metrics"],
        stdout=open(out / f"replica{idx}.log", "w"), stderr=subprocess.STDOUT)


async def wait_health(url: str, timeout: float = 60) -> None:
    async with httpx.AsyncClient() as c:
        for _ in range(int(timeout * 4)):
            try:
                if (await c.get(f"{url}/health")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise RuntimeError(f"{url} not healthy")


async def inject(cfg, procs: list, out: Path, t0: float, events: list) -> None:
    async def at(t: float) -> None:
        await asyncio.sleep(max(0, t0 + t - time.time()))

    def log(ev: str) -> None:
        events.append({"t": round(time.time() - t0, 2), "event": ev})

    await at(TIMELINE["kill"]); procs[1].kill(); log("kill r1")
    await at(TIMELINE["restart"])
    procs[1] = start_replica(cfg, 1, out); log("restart r1 (process start)")
    await wait_health(cfg.replicas[1].url); log("r1 healthy again")
    await at(TIMELINE["throttle"]); log("throttle r1 (30% duty)")
    stop = asyncio.Event()

    async def duty() -> None:
        while not stop.is_set():
            os.kill(procs[1].pid, signal.SIGCONT); await asyncio.sleep(0.03)
            os.kill(procs[1].pid, signal.SIGSTOP); await asyncio.sleep(0.07)
    task = asyncio.create_task(duty())
    await at(TIMELINE["unthrottle"]); stop.set(); await task
    os.kill(procs[1].pid, signal.SIGCONT); log("unthrottle r1")


KEEP = ("gw_requests_total", "gw_errors_total", "gw_inflight", "gw_replica_down", "gw_goodput_total",
        "gw_ttft_seconds_bucket", "gw_ttft_seconds_count", "gw_rejected_total")


async def scrape(gw: str, t0: float, out: Path) -> None:
    async with httpx.AsyncClient(timeout=2) as c:
        with open(out / "metrics.jsonl", "w") as f:
            while True:
                try:
                    txt = (await c.get(f"{gw}/metrics")).text
                    rows = {ln.rsplit(" ", 1)[0]: float(ln.rsplit(" ", 1)[1]) for ln in txt.splitlines()
                            if ln.startswith(KEEP)}
                    f.write(json.dumps({"t": round(time.time() - t0, 2), "m": rows}) + "\n")
                    f.flush()
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(2)


async def main(tag: str, rate: float, breaker: bool) -> None:
    out = Path(f"results/drill_{tag}")
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*"):
        f.unlink()
    cfg = load_settings()
    procs = [start_replica(cfg, i, out) for i in range(len(cfg.replicas))]
    for r in cfg.replicas:
        await wait_health(r.url)
    env = {**os.environ, "GATEWAY_BREAKER": "1" if breaker else "0",
           "GATEWAY_TRACE_FILE": str(out / "spans.jsonl")}
    gw = subprocess.Popen([sys.executable, "-m", "gateway.main"], env=env,
                          stdout=open(out / "gateway.log", "w"), stderr=subprocess.STDOUT)
    await asyncio.sleep(3)
    url = f"http://{cfg.gateway.host}:{cfg.gateway.port}"
    events: list = []
    t0 = time.time()
    sc = asyncio.create_task(scrape(url, t0, out))
    fi = asyncio.create_task(inject(cfg, procs, out, t0, events))
    recs = await run(url, load("data/trace.jsonl"), rate, TIMELINE["end"], 2.0, 30, seed=1)
    await fi
    sc.cancel()
    write_csv(recs, str(out / "load.csv"))
    json.dump({"events": events, "timeline": TIMELINE, "breaker": breaker, "rate": rate,
               "t0_epoch": t0}, open(out / "events.json", "w"), indent=1)
    gw.terminate()
    for p in procs:
        p.kill()
    print(f"{tag}: {len(recs)} requests, events={events}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--breaker", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.tag, a.rate, a.breaker))
