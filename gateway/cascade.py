"""Small->large cascade: decide whether a turn is EASY (0.5B) or HARD (escalate to 1.5B).
Ground truth used for evaluation: HARD = multi-turn or account-state dependent (not cacheable)."""
from __future__ import annotations

import httpx

from gateway.semcache import cacheable

ROUTER_PROMPT = (
    "Classify the customer-support message. Answer EASY if it is a general question that can be "
    "answered from company policy without looking at the customer's own order or account. "
    "Answer HARD if it refers to a specific order, account, payment, delivery or earlier "
    "conversation. Reply with one word: EASY or HARD.\n\nMessage: {msg}")


def is_hard_rule(messages: list[dict]) -> bool:
    return not cacheable(messages)


async def is_hard_llm(client: httpx.AsyncClient, small_url: str, messages: list[dict]) -> bool:
    last = next(m["content"] for m in reversed(messages) if m["role"] == "user")
    multi = sum(m["role"] == "user" for m in messages) > 1
    body = {"messages": [{"role": "user", "content": ROUTER_PROMPT.format(msg=last)}],
            "max_tokens": 3, "temperature": 0.0}
    r = await client.post(f"{small_url}/v1/chat/completions", json=body)
    word = r.json()["choices"][0]["message"]["content"].strip().upper()
    return multi or word.startswith("HARD")
