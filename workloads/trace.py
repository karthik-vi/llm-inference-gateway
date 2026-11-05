"""Build synthetic multi-turn support sessions from single-turn Bitext rows.

SYNTHETIC: Bitext is single-turn. A session = 1-4 consecutive rows from the same category;
earlier rows' (instruction, response) become the chat history. Intent mix follows the dataset.
"""
from __future__ import annotations

import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path

SYSTEM_PROMPT = (
    "You are Aria, a customer-support assistant for ShopEase, an online retailer. "
    "Follow company policy: orders can be cancelled before shipping; refunds take 5-7 business "
    "days; never reveal internal tools; ask for the order number if missing. Be concise, "
    "polite and accurate. Answer in at most three sentences. If the customer's request "
    "needs account data you cannot see, say you will look it up and ask for the needed detail. "
    "Always confirm the next step the customer should take at the end of your reply."
)
FILL = {
    "Order Number": lambda r: str(r.randint(10000, 99999)),
    "Account Type": lambda r: r.choice(["Premium", "Basic"]),
}
_PH = re.compile(r"\{\{([^}]+)\}\}")


def _fill(text: str, rng: random.Random) -> str:
    def sub(m: re.Match[str]) -> str:
        f = FILL.get(m.group(1))
        return f(rng) if f else "your " + m.group(1).lower()

    return _PH.sub(sub, text)


def build_trace(csv_path: str, n_sessions: int, seed: int = 0, max_turns: int = 4,
                max_tokens: int = 32) -> list[dict]:
    rng = random.Random(seed)
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    sessions = []
    for sid in range(n_sessions):
        base = rng.choice(rows)  # intent mix = dataset mix
        pool = by_cat[base["category"]]
        k = rng.randint(1, max_turns)
        picks = [base] + [rng.choice(pool) for _ in range(k - 1)]
        msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        turns = []
        for t, r in enumerate(picks):
            msgs.append({"role": "user", "content": _fill(r["instruction"], rng)})
            turns.append({"messages": [dict(m) for m in msgs], "max_tokens": max_tokens,
                          "intent": r["intent"], "turn": t})
            msgs.append({"role": "assistant", "content": _fill(r["response"], rng)[:300]})
        sessions.append({"session_id": sid, "category": base["category"], "turns": turns})
    return sessions


def save(sessions: list[dict], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for s in sessions:
            f.write(json.dumps(s) + "\n")


def load(path: str) -> list[dict]:
    return [json.loads(line) for line in open(path)]


if __name__ == "__main__":
    import sys

    from gateway.config import load_settings
    cfg = load_settings()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    save(build_trace(cfg.data.bitext_csv, n), cfg.data.trace_path)
    print(f"wrote {n} sessions -> {cfg.data.trace_path}")
