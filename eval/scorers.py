"""Pure scoring functions (unit-tested; no LLM)."""
from __future__ import annotations

import json
import re

from eval.backend import REASONS, SCHEMA, tokens

_JSON = re.compile(r"\{.*\}", re.S)


def parse_tool_call(text: str) -> tuple[dict | None, bool]:
    """-> (call or None, looked_like_tool_call). A reply that contains a JSON object with a
    'tool' key is an attempted tool call; it is valid only if it parses to {tool, args}."""
    if '"tool"' not in text:
        return None, False
    m = _JSON.search(text)
    if not m:
        return None, True  # truncated / unbalanced JSON: an attempted but invalid call
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None, True
    if isinstance(obj, dict) and isinstance(obj.get("tool"), str) and isinstance(obj.get("args"), dict):
        return obj, True
    return None, True


def tool_call_valid(call: dict | None) -> bool:
    if call is None:
        return False
    need = SCHEMA.get(call["tool"])
    if need is None or set(call["args"]) != need:
        return False
    if call["tool"] == "cancel_pending_order" and call["args"].get("reason") not in REASONS:
        return False
    return True


def tool_validity(calls: list[tuple[dict | None, bool]]) -> tuple[int, int]:
    """-> (valid, attempted)."""
    att = [c for c, tried in calls if tried]
    return sum(tool_call_valid(c) for c, tried in calls if tried), len(att)


def grounding(answer: str, retrieved: list[str], question: str) -> float:
    """Share of the answer's content words (len>3) that appear in the retrieved policy text or
    the question. A crude, reproducible proxy for 'stays within the retrieved text'."""
    src = set(tokens(" ".join(retrieved) + " " + question))
    words = [w for w in tokens(answer) if len(w) > 3]
    return sum(w in src for w in words) / len(words) if words else 0.0


def success_lookup(answer: str, true_status: str, called_ids: list[str], order_id: str) -> bool:
    return true_status in answer.lower() and order_id in called_ids


def success_cancel(before: dict[str, str], after: dict[str, str], target: str) -> bool:
    changed = {k for k in after if after[k] != before.get(k)}
    return changed == {target} and after[target] == "cancelled"


def success_policy(answer: str, gold: list[str]) -> bool:
    a = answer.lower()
    return all(any(alt in a for alt in g.lower().split("|")) for g in gold)
