"""Per-replica sidecar: reads llama-server /metrics locally and streams LoadStats over gRPC."""
from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator

import grpc
import httpx

from control import load_pb2, load_pb2_grpc

_METRIC = re.compile(r"^llamacpp:(\w+)\s+([-0-9.eE+]+)$", re.M)


def parse_metrics(text: str) -> dict[str, float]:
    return {k: float(v) for k, v in _METRIC.findall(text)}


class Sidecar(load_pb2_grpc.LoadStreamServicer):
    def __init__(self, name: str, llama_url: str) -> None:
        self.name = name
        self.http = httpx.AsyncClient(base_url=llama_url, timeout=2.0)

    async def read(self) -> load_pb2.LoadStats:
        t = time.time()
        m = parse_metrics((await self.http.get("/metrics")).text)
        return load_pb2.LoadStats(
            replica=self.name, t_src=t,
            slots_busy=int(m.get("requests_processing", 0)),
            queue_depth=int(m.get("requests_deferred", 0)),
            tokens_per_s=m.get("predicted_tokens_seconds", 0.0))

    async def Stream(self, request_iterator, context) -> AsyncIterator[load_pb2.LoadStats]:  # noqa: N802
        hello = await anext(request_iterator)
        interval = max(hello.interval_ms, 10) / 1000
        while True:
            yield await self.read()
            await asyncio.sleep(interval)


async def serve(name: str, llama_url: str, port: int) -> None:
    server = grpc.aio.server()
    load_pb2_grpc.add_LoadStreamServicer_to_server(Sidecar(name, llama_url), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    import sys
    asyncio.run(serve(sys.argv[1], sys.argv[2], int(sys.argv[3])))
