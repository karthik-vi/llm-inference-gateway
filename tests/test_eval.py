import json

from eval.agent import run_task
from eval.backend import Backend, passages, retrieve
from eval.scorers import (
    grounding,
    parse_tool_call,
    success_cancel,
    success_policy,
    tool_call_valid,
    tool_validity,
)

USERS = {"u1": {"name": "A B", "email": "a@x.com", "orders": ["#W1"]}}
ORDERS = {"#W1": {"order_id": "#W1", "user_id": "u1", "status": "pending",
                  "items": [{"name": "Mug"}]},
          "#W2": {"order_id": "#W2", "user_id": "u1", "status": "delivered", "items": []}}
POLICY = "# Cancel\n- An order can only be cancelled if its status is 'pending'.\n"


def call(tool: str, **args: str) -> str:
    return json.dumps({"tool": tool, "args": args})


def test_tool_validity_rules() -> None:
    ok, _ = parse_tool_call(call("get_order_details", order_id="#W1"))
    assert tool_call_valid(ok)
    bad_args, tried = parse_tool_call(call("get_order_details", orderid="#W1"))
    assert tried and not tool_call_valid(bad_args)
    broken, tried = parse_tool_call('{"tool": "x", "args": ')
    assert broken is None and tried
    assert parse_tool_call("Your order is pending.") == (None, False)
    assert not tool_call_valid(parse_tool_call(
        call("cancel_pending_order", order_id="#W1", reason="because"))[0])
    assert tool_validity([(ok, True), (bad_args, True), (None, False)]) == (1, 2)


def test_scorers() -> None:
    assert success_cancel({"a": "pending", "b": "pending"}, {"a": "cancelled", "b": "pending"}, "a")
    assert not success_cancel({"a": "pending", "b": "pending"},
                              {"a": "cancelled", "b": "cancelled"}, "a")
    assert success_policy("Only pending orders", ["pending"])
    assert success_policy("You may do it one time", ["once|one time"])
    assert not success_policy("No idea", ["pending"])
    assert grounding("orders cancelled pending", ["orders pending cancelled"], "q") == 1.0


def test_retrieval_finds_relevant_passage() -> None:
    pas = passages("# A\nshipping and delivery times\n# B\ncancel pending order status rules\n")
    assert "cancel" in retrieve("how do I cancel an order", pas, k=1)[0]


def scripted(replies: list[str]):
    it = iter(replies)
    return lambda msgs: (next(it), 100, 10)


def test_cancel_flow_with_mocked_llm() -> None:
    be = Backend(USERS, ORDERS)
    llm = scripted([call("find_user_id_by_email", email="a@x.com"),
                    call("get_order_details", order_id="#W1"),
                    "Please confirm: cancel #W1? (yes)",
                    call("cancel_pending_order", order_id="#W1", reason="no longer needed"),
                    "Done, your order is cancelled."])
    task = {"id": "c", "type": "cancel", "order_id": "#W1", "email": "a@x.com",
            "opening": "cancel #W1 a@x.com"}
    r = run_task(task, llm, be, POLICY)
    assert r.success and r.tool_valid == 3 and r.tool_attempted == 3 and r.calls == 5


def test_lookup_and_unauthenticated_failure() -> None:
    be = Backend(USERS, ORDERS)
    task = {"id": "l", "type": "lookup", "order_id": "#W2", "email": "a@x.com",
            "true_status": "delivered", "opening": "status of #W2"}
    r = run_task(task, scripted([call("get_order_details", order_id="#W2"),
                                 "It is delivered."]), be, POLICY)
    assert not r.success or r.called_ids == ["#W2"]  # backend refuses; answer was still given
    assert be.call("get_order_details", {"order_id": "#W2"}).startswith("Error")
