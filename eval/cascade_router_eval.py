"""Accuracy of the prompt-based 0.5B router vs the rule label (HARD = not cacheable)."""
from __future__ import annotations

import asyncio
import random

import httpx

from gateway.cascade import is_hard_llm, is_hard_rule
from workloads.trace import load


async def main(n: int = 200, url: str = "http://127.0.0.1:9001") -> None:
    turns = [t for s in load("data/trace.jsonl") for t in s["turns"]]
    random.Random(0).shuffle(turns)
    turns = turns[:n]
    tp = fp = tn = fn = 0
    async with httpx.AsyncClient(timeout=60) as c:
        for t in turns:
            truth = is_hard_rule(t["messages"])
            pred = await is_hard_llm(c, url, t["messages"])
            tp += truth and pred; fp += (not truth) and pred
            tn += (not truth) and (not pred); fn += truth and (not pred)
    print(f"n={len(turns)} acc={(tp+tn)/len(turns):.3f} hard_recall={tp/max(tp+fn,1):.3f} "
          f"easy_recall={tn/max(tn+fp,1):.3f} tp={tp} fp={fp} tn={tn} fn={fn}")


if __name__ == "__main__":
    asyncio.run(main())
