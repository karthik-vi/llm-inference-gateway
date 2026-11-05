"""Support agent: tool calls against the simulated backend + policy retrieval.
`llm(messages) -> (text, prompt_tokens, completion_tokens)` is injectable so CI can mock it."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from eval.backend import TOOLS_DOC, Backend, passages, retrieve
from eval.scorers import (
    grounding,
    parse_tool_call,
    success_cancel,
    success_lookup,
    success_policy,
    tool_call_valid,
    tool_validity,
)

LLM = Callable[[list[dict]], tuple[str, int, int]]
SYSTEM = ("You are a retail customer-support agent. Authenticate the user by email "
          "(find_user_id_by_email) before any account action. Before cancelling an order, "
          "check its status, state the action and ask the user for explicit confirmation (yes). "
          "Do not invent information. Policy excerpts:\n{policy}\n\n" + TOOLS_DOC)
CONFIRM_WORDS = ("confirm", "proceed", "yes", "go ahead")
MAX_CALLS = 8


@dataclass
class Result:
    task: str
    type: str
    success: bool = False
    grounded: float | None = None
    calls: int = 0
    tool_valid: int = 0
    tool_attempted: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    final: str = ""
    called_ids: list[str] = field(default_factory=list)


def run_task(task: dict, llm: LLM, backend: Backend, policy_md: str) -> Result:
    res = Result(task["id"], task["type"])
    before = backend.state()
    pas = passages(policy_md)
    retrieved = retrieve(task["opening"], pas)
    msgs = [{"role": "system", "content": SYSTEM.replace("{policy}", "\n---\n".join(retrieved))},
            {"role": "user", "content": task["opening"]}]
    attempts: list[tuple[dict | None, bool]] = []
    confirmed = False
    t0 = time.perf_counter()
    for _ in range(MAX_CALLS):
        text, pt, ct = llm(msgs)
        res.calls += 1
        res.prompt_tokens += pt
        res.completion_tokens += ct
        msgs.append({"role": "assistant", "content": text})
        call, tried = parse_tool_call(text)
        if tried:
            attempts.append((call, tried))
            if tool_call_valid(call):
                if "order_id" in call["args"]:
                    res.called_ids.append(str(call["args"]["order_id"]))
                out = backend.call(call["tool"], call["args"])
            else:
                out = "Error: invalid tool call (need JSON {\"tool\": name, \"args\": {...}})"
            msgs.append({"role": "user", "content": f"TOOL RESULT: {out}"})
            continue
        res.final = text
        if (task["type"] == "cancel" and not confirmed
                and any(w in text.lower() for w in CONFIRM_WORDS)):
            confirmed = True  # scripted user: confirms once
            msgs.append({"role": "user", "content": "Yes, please go ahead."})
            continue
        break
    res.latency_s = time.perf_counter() - t0
    res.tool_valid, res.tool_attempted = tool_validity(attempts)
    after = backend.state()
    if task["type"] == "lookup":
        res.success = success_lookup(res.final, task["true_status"], res.called_ids, task["order_id"])
    elif task["type"] == "cancel":
        res.success = success_cancel(before, after, task["order_id"])
    else:
        res.success = success_policy(res.final, task["gold"])
        res.grounded = grounding(res.final, retrieved, task["opening"])
    return res
