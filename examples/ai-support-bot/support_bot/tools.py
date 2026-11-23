"""Order tools the assistant can call, backed by an in-memory order table."""

from __future__ import annotations

# Tool definitions in the shape an LLM tool-calling API expects.
TOOL_SPECS = [
    {
        "name": "lookup_order",
        "description": "Look up an order by its id (for example A1001).",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "issue_refund",
        "description": "Refund an order to the original payment method.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount_cents": {"type": "integer", "description": "Refund amount in cents."},
            },
            "required": ["order_id", "amount_cents"],
        },
    },
]

ORDERS: dict[str, dict] = {
    "A1001": {"order_id": "A1001", "purchased_days_ago": 12, "total_cents": 4999, "status": "delivered"},
    "A1002": {"order_id": "A1002", "purchased_days_ago": 45, "total_cents": 12900, "status": "delivered"},
    "A1003": {"order_id": "A1003", "purchased_days_ago": 3, "total_cents": 2599, "status": "shipped"},
    "A1004": {"order_id": "A1004", "purchased_days_ago": 21, "total_cents": 8450, "status": "delivered"},
    "A1005": {"order_id": "A1005", "purchased_days_ago": 30, "total_cents": 1999, "status": "delivered"},
}

# Refund confirmations issued during this process (kept in memory only).
REFUNDS: list[dict] = []


def lookup_order(order_id: str) -> dict | None:
    """Return a copy of the order, or ``None`` if there is no such order."""
    order = ORDERS.get(order_id.strip().upper())
    return dict(order) if order else None


def issue_refund(order_id: str, amount_cents: int) -> dict:
    """Record a refund of ``amount_cents`` for ``order_id`` and return the confirmation."""
    order_id = order_id.strip().upper()
    confirmation = {
        "refund_id": f"RF-{order_id}",
        "order_id": order_id,
        "amount_cents": amount_cents,
        "status": "issued",
    }
    REFUNDS.append(confirmation)
    return dict(confirmation)
