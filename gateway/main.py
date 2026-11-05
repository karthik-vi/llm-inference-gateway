"""OpenAI-compatible streaming gateway (v0: round-robin, timeouts, metrics, OTel spans)."""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

import anyio
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from opentelemetry import trace
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from gateway import metrics
from gateway.admission import AdmissionController
from gateway.config import Replica, Settings, load_settings
from gateway.router import make_router, prefix_key
from gateway.semcache import SemanticCache, cacheable, fastembed_fn

tracer = trace.get_tracer("gateway")


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    app = FastAPI(title="llm-inference-gateway")
    router = make_router(cfg.gateway.routing, cfg.replicas, cfg.gateway.max_inflight_per_replica)
    inflight: dict[str, int] = {r.name: 0 for r in cfg.replicas}
    gw = cfg.gateway
    adm = (AdmissionController(gw.slo_ttft_s, gw.slots_per_replica, gw.admission_margin)
           if gw.admission else None)
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(cfg.gateway.upstream_timeout_s, connect=5.0),
        limits=httpx.Limits(max_connections=512, max_keepalive_connections=64),
    )

    sem = (SemanticCache(fastembed_fn(), gw.semcache_threshold) if gw.semcache else None)

    async def cached_stream(answer: str) -> AsyncIterator[bytes]:
        def chunk(d: dict) -> bytes:
            return ("data: " + json.dumps(d) + "\n\n").encode()
        yield chunk({"choices": [{"index": 0, "delta": {"content": answer}}]})
        yield chunk({"choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                     "timings": {"prompt_n": 0, "cache_n": 0}})
        yield b"data: [DONE]\n\n"

    @app.get("/metrics")
    async def prom() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def stream_upstream(rep: Replica, body: dict,
                              cache_text: str | None = None) -> AsyncIterator[bytes]:
        """Proxy SSE. Leaving the `async with` (incl. on client disconnect, which cancels
        this generator) closes the upstream connection, which makes llama-server abort."""
        t0 = time.perf_counter()
        last: float | None = None
        first_ttft: float | None = None
        parts: list[str] = []
        status = "ok"
        n_at_start = inflight[rep.name] - 1
        try:
            with tracer.start_as_current_span("upstream", attributes={"replica": rep.name}):
                async with client.stream(
                    "POST", f"{rep.url}/v1/chat/completions", json=body
                ) as resp:
                    if resp.status_code != 200:
                        status = f"http_{resp.status_code}"
                        yield await resp.aread()
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        now = time.perf_counter()
                        if line.startswith("data:") and "[DONE]" not in line:
                            delta = _has_content(line)
                            if delta and cache_text is not None:
                                parts.append(delta)
                            if delta and last is None:
                                first_ttft = now - t0
                                metrics.TTFT.labels(rep.name).observe(now - t0)
                            elif delta and last is not None:
                                metrics.ITL.labels(rep.name).observe(now - last)
                            if delta:
                                last = now
                        yield (line + "\n\n").encode()
                if sem is not None and cache_text is not None and parts:
                    await anyio.to_thread.run_sync(sem.add, cache_text, "".join(parts))
        except httpx.TimeoutException:
            status = "timeout"
            metrics.ERRORS.labels(rep.name, "timeout").inc()
            raise
        except httpx.HTTPError:
            status = "upstream_error"
            metrics.ERRORS.labels(rep.name, "upstream").inc()
            raise
        except BaseException:
            status = "cancelled"
            raise
        finally:
            inflight[rep.name] -= 1
            if adm is not None and status == "ok":
                adm.observe(first_ttft, time.perf_counter() - t0, n_at_start)
            metrics.REQS.labels(rep.name, status).inc()

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Response:
        body = await request.json()
        ctext = None
        if sem is not None and body.get("stream") and cacheable(body.get("messages", [])):
            ctext = next(m["content"] for m in body["messages"] if m["role"] == "user")
            with tracer.start_as_current_span("cache_lookup"):
                ans, _sim = await anyio.to_thread.run_sync(sem.lookup, ctext)
            if ans is not None:
                metrics.CACHE.labels("hit").inc()
                metrics.REQS.labels("cache", "ok").inc()
                return StreamingResponse(cached_stream(ans), media_type="text/event-stream",
                                         headers={"X-Replica": "cache"})
            metrics.CACHE.labels("miss").inc()
        if adm is not None:
            with tracer.start_as_current_span("admission"):
                d = adm.decide(inflight)
            if not d.admit:
                metrics.REJECTED.inc()
                return JSONResponse({"error": "SLO cannot be met", "est_ttft_s": d.est_ttft_s},
                                    status_code=429, headers={"Retry-After": str(d.retry_after_s)})
        with tracer.start_as_current_span("route"):
            rep = router.pick(prefix_key(body.get("messages", [])), inflight)
        inflight[rep.name] += 1
        if body.get("stream"):
            body.setdefault("stream_options", {"include_usage": True})
            return StreamingResponse(
                stream_upstream(rep, body, ctext),
                media_type="text/event-stream",
                headers={"X-Replica": rep.name},
            )
        try:
            with tracer.start_as_current_span("upstream", attributes={"replica": rep.name}):
                r = await client.post(f"{rep.url}/v1/chat/completions", json=body)
        except httpx.HTTPError:
            metrics.ERRORS.labels(rep.name, "upstream").inc()
            metrics.REQS.labels(rep.name, "upstream_error").inc()
            return JSONResponse({"error": "upstream failure"}, status_code=502)
        finally:
            inflight[rep.name] -= 1
        st = "ok" if r.status_code == 200 else f"http_{r.status_code}"
        metrics.REQS.labels(rep.name, st).inc()
        return JSONResponse(r.json(), status_code=r.status_code,
                            headers={"X-Replica": rep.name})

    return app


def _has_content(line: str) -> str:
    try:
        obj = json.loads(line[5:])
        ch = obj.get("choices") or []
        return (ch[0].get("delta") or {}).get("content") or "" if ch else ""
    except (ValueError, AttributeError):
        return ""


if __name__ == "__main__":
    s = load_settings()
    uvicorn.run(create_app(s), host=s.gateway.host, port=s.gateway.port, log_level="warning")
