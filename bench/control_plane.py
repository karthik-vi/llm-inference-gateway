"""ADR-007: gRPC push stream vs HTTP polling of llama-server /metrics.
Both clients keep `latest` (value + source timestamp). A sampler reads the age of `latest` at
random instants (= staleness a router would see). Overhead = client-process CPU seconds/updates
and bytes per update. Load: a few concurrent chat requests keep the replica busy meanwhile."""
from __future__ import annotations

import asyncio
import random
import resource
import statistics
import sys
import time

import grpc
import httpx
import numpy as np

from control import load_pb2, load_pb2_grpc
from control.sidecar import parse_metrics, serve

LLAMA = "http://127.0.0.1:9001"


async def background_load(stop: asyncio.Event) -> None:
    async with httpx.AsyncClient(timeout=60) as c:
        async def worker() -> None:
            while not stop.is_set():
                await c.post(f"{LLAMA}/v1/chat/completions", json={
                    "messages": [{"role": "user", "content": "Explain how to return an item."}],
                    "max_tokens": 24, "temperature": 0.0})
        await asyncio.gather(*[worker() for _ in range(3)])


async def run_http(period: float, dur: float, ages: list[float], stats: dict) -> None:
    latest = {"t": time.time()}
    end = time.time() + dur

    async def poll() -> None:
        async with httpx.AsyncClient(timeout=2) as c:
            while time.time() < end:
                t0 = time.time()
                r = await c.get(f"{LLAMA}/metrics")
                t1 = time.time()
                parse_metrics(r.text)
                latest["t"] = (t0 + t1) / 2        # server read ~ midway through the round trip
                stats["updates"] += 1
                stats["bytes"] += len(r.content)
                await asyncio.sleep(max(0, period - (time.time() - t0)))
    await asyncio.gather(poll(), sample(latest, end, ages))


async def run_grpc(period: float, dur: float, ages: list[float], stats: dict) -> None:
    latest = {"t": time.time()}
    end = time.time() + dur
    async with grpc.aio.insecure_channel("127.0.0.1:9101") as ch:
        stub = load_pb2_grpc.LoadStreamStub(ch)

        async def hello():
            yield load_pb2.Hello(interval_ms=int(period * 1000))
            await asyncio.sleep(dur + 1)

        async def consume() -> None:
            async for s in stub.Stream(hello()):
                latest["t"] = s.t_src
                stats["updates"] += 1
                stats["bytes"] += s.ByteSize()
                if time.time() >= end:
                    return
        await asyncio.gather(consume(), sample(latest, end, ages))


async def sample(latest: dict, end: float, ages: list[float]) -> None:
    await asyncio.sleep(1.0)
    while time.time() < end:
        await asyncio.sleep(random.uniform(0.005, 0.05))
        ages.append(time.time() - latest["t"])


def cpu() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


async def main(dur: float = 15.0) -> None:
    srv = asyncio.create_task(serve("r0", LLAMA, 9101))
    await asyncio.sleep(1)
    stop = asyncio.Event()
    load = asyncio.create_task(background_load(stop))
    print("mode,period_ms,updates_per_s,age_p50_ms,age_p95_ms,age_p99_ms,client_cpu_ms_per_update,bytes_per_update")
    for period in (0.05, 0.1, 0.25):
        for mode, fn in (("http_poll", run_http), ("grpc_push", run_grpc)):
            ages: list[float] = []
            stats = {"updates": 0, "bytes": 0}
            c0 = cpu()
            await fn(period, dur, ages, stats)
            cpu_ms = (cpu() - c0) * 1000 / max(stats["updates"], 1)
            a = np.array(ages) * 1000
            print(f"{mode},{int(period*1000)},{stats['updates']/dur:.1f},{np.percentile(a,50):.1f},"
                  f"{np.percentile(a,95):.1f},{np.percentile(a,99):.1f},{cpu_ms:.2f},"
                  f"{stats['bytes']/max(stats['updates'],1):.0f}", flush=True)
    stop.set(); load.cancel(); srv.cancel()


if __name__ == "__main__":
    asyncio.run(main())
