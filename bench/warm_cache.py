"""Pre-warm the semantic cache with cacheable first-turn queries from sessions NOT used by the
benchmark (sessions 200..399; the load generator consumes sessions 0..~190 in order)."""
from __future__ import annotations

import asyncio

import httpx

from gateway.semcache import cacheable
from workloads.trace import load


async def main(url: str = "http://127.0.0.1:8080", conc: int = 4) -> None:
    turns = [s["turns"][0] for s in load("data/trace.jsonl")[200:]]
    turns = [t for t in turns if cacheable(t["messages"])]
    sem = asyncio.Semaphore(conc)
    async with httpx.AsyncClient(timeout=60) as c:
        async def go(t: dict) -> None:
            async with sem:
                body = {"messages": t["messages"], "max_tokens": t["max_tokens"], "stream": True,
                        "temperature": 0.0}
                async with c.stream("POST", f"{url}/v1/chat/completions", json=body) as r:
                    async for _ in r.aiter_lines():
                        pass
        await asyncio.gather(*[go(t) for t in turns])
    print(f"warmed with {len(turns)} queries")


if __name__ == "__main__":
    asyncio.run(main())
