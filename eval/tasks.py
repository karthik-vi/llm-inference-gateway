"""Build the eval task set from the tau-bench retail DB. Opening messages are paraphrased ONCE by
the local 0.5B model (the user simulator) with fixed seeds and cached, so all configs see identical
user messages. Task types are tau-bench-STYLE (generated here, not the official tau-bench tasks)."""
from __future__ import annotations

import json
import random
from collections.abc import Callable

POLICY_QS = [
    ("Can I cancel an order that has already been delivered?", ["pending"]),
    ("What reasons can I give when I cancel an order?", ["no longer needed", "ordered by mistake"]),
    ("How long does it take to get my refund after cancelling an order paid by credit card?",
     ["5 to 7"]),
    ("How many times can the items of a pending order be modified?", ["once|one time|single"]),
    ("Which order statuses can you take action on?", ["pending", "delivered"]),
    ("Do you need my confirmation before changing my order?", ["confirm"]),
    ("What kinds of payment methods can a customer profile have?",
     ["gift card", "paypal", "credit card"]),
    ("Can you help me with another person's account too?", ["one user|single user|only one"]),
]


def base_tasks(users: dict, orders: dict, n_per_type: int = 8, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    by_status: dict[str, list[dict]] = {}
    for o in orders.values():
        by_status.setdefault(o["status"], []).append(o)
    tasks: list[dict] = []

    def pick(status: list[str]) -> dict:
        o = rng.choice([x for s in status for x in by_status[s]])
        return o

    for i in range(n_per_type):
        o = pick(["pending", "processed", "delivered", "cancelled"])
        e = users[o["user_id"]]["email"]
        tasks.append({"id": f"lookup{i}", "type": "lookup", "order_id": o["order_id"], "email": e,
                      "true_status": o["status"],
                      "opening": f"Hi, my email is {e}. What is the current status of my order "
                                 f"{o['order_id']}?"})
    for i in range(n_per_type):
        o = pick(["pending"])
        e = users[o["user_id"]]["email"]
        tasks.append({"id": f"cancel{i}", "type": "cancel", "order_id": o["order_id"], "email": e,
                      "opening": f"Hi, my email is {e}. Please cancel my order {o['order_id']}, "
                                 f"I no longer need it."})
    for i in range(n_per_type):
        q, gold = POLICY_QS[i % len(POLICY_QS)]
        tasks.append({"id": f"policy{i}", "type": "policy", "gold": gold, "opening": q})
    return tasks


def paraphrase_tasks(tasks: list[dict], llm: Callable[[str, int], str]) -> list[dict]:
    """llm(prompt, seed) -> text. Keeps ids/emails; falls back to the template on any drift."""
    out = []
    for i, t in enumerate(tasks):
        p = ("Rewrite this customer message in different words. Keep every order number and "
             "email address exactly as written. Output only the rewritten message.\n\n"
             + t["opening"])
        try:
            new = llm(p, 1000 + i).strip().strip('"')
        except Exception:  # noqa: BLE001
            new = ""
        keep = all(x in new for x in (t.get("order_id"), t.get("email")) if x)
        ok = keep and 10 < len(new) < 400
        out.append({**t, "base_opening": t["opening"], "opening": new if ok else t["opening"],
                    "paraphrased": ok})
    return out


if __name__ == "__main__":
    import httpx

    users = json.load(open("data/tau/users.json"))
    orders = json.load(open("data/tau/orders.json"))
    tasks = base_tasks(users, orders)

    def llm(prompt: str, seed: int) -> str:
        r = httpx.post("http://127.0.0.1:9001/v1/chat/completions", timeout=60, json={
            "messages": [{"role": "user", "content": prompt}], "max_tokens": 80,
            "temperature": 0.7, "seed": seed})
        return r.json()["choices"][0]["message"]["content"]

    res = paraphrase_tasks(tasks, llm)
    with open("data/tau_tasks.jsonl", "w") as f:
        for t in res:
            f.write(json.dumps(t) + "\n")
    print(f"{len(res)} tasks, paraphrased {sum(t['paraphrased'] for t in res)}")
