"""Simulated retail backend over the tau-bench retail DB (in memory) + policy retrieval."""
from __future__ import annotations

import copy
import json
import re

TOOLS_DOC = """Tools (call at most one per reply, never together with a user-facing answer):
- find_user_id_by_email(email)
- get_user_details(user_id)
- get_order_details(order_id)
- cancel_pending_order(order_id, reason)   # reason: "no longer needed" or "ordered by mistake"
To call a tool reply with ONLY a JSON object: {"tool": "<name>", "args": {...}}
Otherwise reply to the user in plain text."""

SCHEMA = {
    "find_user_id_by_email": {"email"},
    "get_user_details": {"user_id"},
    "get_order_details": {"order_id"},
    "cancel_pending_order": {"order_id", "reason"},
}
REASONS = {"no longer needed", "ordered by mistake"}


class Backend:
    def __init__(self, users: dict, orders: dict) -> None:
        self.users, self.orders = copy.deepcopy(users), copy.deepcopy(orders)
        self.authenticated: str | None = None

    @classmethod
    def load(cls, root: str = "data/tau") -> Backend:
        return cls(json.load(open(f"{root}/users.json")), json.load(open(f"{root}/orders.json")))

    def call(self, name: str, args: dict) -> str:
        if name == "find_user_id_by_email":
            for uid, u in self.users.items():
                if u["email"].lower() == str(args["email"]).lower():
                    self.authenticated = uid
                    return uid
            return "Error: user not found"
        if name == "get_user_details":
            u = self.users.get(args["user_id"])
            if not u or self.authenticated != args["user_id"]:
                return "Error: authenticate with find_user_id_by_email first"
            return json.dumps({"name": u["name"], "email": u["email"], "orders": u["orders"]})
        o = self.orders.get(str(args.get("order_id")))
        if o is None:
            return "Error: order not found"
        if self.authenticated is None or o["user_id"] != self.authenticated:
            return "Error: authenticate first; orders of other users cannot be accessed"
        if name == "get_order_details":
            return json.dumps({"order_id": o["order_id"], "status": o["status"],
                               "items": [i["name"] for i in o["items"]]})
        if name == "cancel_pending_order":
            if o["status"] != "pending":
                return f"Error: order status is {o['status']}, only pending orders can be cancelled"
            if args.get("reason") not in REASONS:
                return "Error: invalid reason"
            o["status"] = "cancelled"
            return "Order cancelled"
        return "Error: unknown tool"

    def state(self) -> dict[str, str]:
        return {k: v["status"] for k, v in self.orders.items()}


_TOK = re.compile(r"[a-z0-9']+")


def tokens(text: str) -> list[str]:
    return _TOK.findall(text.lower())


def passages(policy_md: str) -> list[str]:
    parts, cur = [], ""
    for line in policy_md.splitlines():
        if line.startswith("#"):
            if cur.strip():
                parts.append(cur.strip())
            cur = line + "\n"
        elif line.startswith("- ") and len(cur) > 600:
            parts.append(cur.strip())
            cur = line + "\n"
        else:
            cur += line + "\n"
    if cur.strip():
        parts.append(cur.strip())
    return parts


def retrieve(query: str, pas: list[str], k: int = 2) -> list[str]:
    q = {t for t in tokens(query) if len(t) > 3}
    scored = sorted(pas, key=lambda p: -len(q & set(tokens(p))) / (1 + len(tokens(p)) ** 0.5))
    return scored[:k]
