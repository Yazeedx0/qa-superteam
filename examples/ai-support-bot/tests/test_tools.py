from support_bot.tools import issue_refund, lookup_order


def test_lookup_known_order():
    order = lookup_order("A1001")
    assert order == {"order_id": "A1001", "purchased_days_ago": 12, "total_cents": 4999, "status": "delivered"}


def test_lookup_is_case_insensitive():
    assert lookup_order(" a1002 ")["order_id"] == "A1002"


def test_lookup_unknown_order_returns_none():
    assert lookup_order("Z9999") is None


def test_lookup_returns_a_copy():
    lookup_order("A1004")["status"] = "refunded"
    assert lookup_order("A1004")["status"] == "delivered"


def test_issue_refund_returns_confirmation():
    confirmation = issue_refund("A1004", 8450)
    assert confirmation == {"refund_id": "RF-A1004", "order_id": "A1004", "amount_cents": 8450, "status": "issued"}
