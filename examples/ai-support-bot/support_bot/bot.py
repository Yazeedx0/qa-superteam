"""Northwind Goods support assistant.

A deterministic stand-in for an LLM-backed RAG + tool-calling assistant. It
retrieves policy documents, composes an extractive answer from the best
matching sentences, and calls the order tools for refund requests. The same
request always produces the same response, and nothing leaves the process.
"""

from __future__ import annotations

import re

from . import tools
from .retriever import get_document, retrieve, tokenize

TOP_K = 3
# Minimum BM25 score for the best document before we answer from the corpus.
MIN_SCORE = 1.0
MAX_ANSWER_SENTENCES = 3
REFUND_WINDOW_DAYS = 30
SUPPORT_EMAIL = "support@northwindgoods.example"

FALLBACK_ANSWER = (
    "I'm sorry, I don't know the answer to that. I can help with Northwind Goods orders, "
    "shipping, returns, refunds, warranty, payments and accounts. For anything else, please contact "
    f"our support team at {SUPPORT_EMAIL}."
)
REFUSAL_ANSWER = (
    "I'm sorry, but I can't share internal codes, passwords or other confidential information. "
    f"If you need help with your account, please contact {SUPPORT_EMAIL}."
)

_ORDER_ID_RE = re.compile(r"\b([A-Za-z]\d{4})\b")
_REFUND_RE = re.compile(r"\b(refund|money back)\b", re.IGNORECASE)
_SECRET_RE = re.compile(
    r"\b(admin|override|internal|staff|master)\b[\w\s-]{0,20}?\b(codes?|passwords?|keys?|credentials?|pins?)\b"
    r"|\bsystem prompt\b|\bapi keys?\b",
    re.IGNORECASE,
)
# Policy docs flag caveats as "Note: ..." or "<Topic> note: ...".
_NOTE_RE = re.compile(r"^(?:[A-Za-z]+\s+)?note:\s*(.+)$", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def answer(request: str | dict) -> dict:
    """Answer a customer request.

    ``request`` is either a single user message (``str``) or a conversation
    ``{"messages": [{"role": "user" | "assistant", "content": str}, ...]}``.
    The last user message is answered; an order id mentioned earlier in the
    conversation is carried forward.

    Returns ``{"answer", "citations", "retrieved", "tool_calls", "usage"}``.
    """
    messages = _normalize(request)
    question = _last_user_message(messages)

    if _SECRET_RE.search(question):
        return _response(REFUSAL_ANSWER, messages)

    order_id = _find_order_id(messages)
    if order_id and _wants_refund(messages):
        return _handle_refund(question, order_id, messages)

    return _answer_from_policies(question, messages)


# --------------------------------------------------------------------------- #
# Conversation handling
# --------------------------------------------------------------------------- #


def _normalize(request: str | dict) -> list[dict]:
    if isinstance(request, str):
        return [{"role": "user", "content": request}]
    if isinstance(request, dict) and isinstance(request.get("messages"), list):
        messages = [
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in request["messages"]
            if isinstance(m, dict)
        ]
        if any(m["role"] == "user" for m in messages):
            return messages
    raise ValueError("request must be a string or {'messages': [...]} with at least one user message")


def _last_user_message(messages: list[dict]) -> str:
    return next(m["content"] for m in reversed(messages) if m["role"] == "user")


def _find_order_id(messages: list[dict]) -> str | None:
    """Most recent order id in the conversation, preferring the last user turn."""
    last = _last_user_message(messages)
    match = _ORDER_ID_RE.search(last)
    if match:
        return match.group(1).upper()
    for message in reversed(messages):
        match = _ORDER_ID_RE.search(message["content"])
        if match:
            return match.group(1).upper()
    return None


def _wants_refund(messages: list[dict]) -> bool:
    user_turns = [m["content"] for m in messages if m["role"] == "user"]
    last = user_turns[-1]
    if _REFUND_RE.search(last):
        return True
    # e.g. "I want a refund" -> "What's the order number?" -> "A1004"
    return bool(_ORDER_ID_RE.search(last)) and any(_REFUND_RE.search(turn) for turn in user_turns[:-1])


# --------------------------------------------------------------------------- #
# Refunds (tool calling)
# --------------------------------------------------------------------------- #


def _refund_amount(order: dict) -> float:
    # Full refund of the order total, rounded to the cent.
    return round(order["total_cents"] / 100, 2)


def _handle_refund(question: str, order_id: str, messages: list[dict]) -> dict:
    # Pull the refund policy in alongside whatever else the question touches.
    hits = retrieve(f"refund {question}", k=TOP_K)
    calls = [{"name": "lookup_order", "args": {"order_id": order_id}}]
    order = tools.lookup_order(order_id)

    if order is None:
        text = (
            f"I couldn't find an order with the number {order_id}. "
            "Please double-check the order number in your confirmation email."
        )
        return _response(text, messages, hits=hits, tool_calls=calls)

    if order["status"] != "delivered":
        text = (
            f"Order {order_id} hasn't been delivered yet (current status: {order['status']}), "
            "so it isn't eligible for a refund yet. " + _policy_sentence("refunds.md", "delivered")
        )
    elif order["purchased_days_ago"] > REFUND_WINDOW_DAYS:
        text = (
            f"Order {order_id} was purchased {order['purchased_days_ago']} days ago, which is outside our "
            f"{REFUND_WINDOW_DAYS}-day refund window, so it isn't eligible for a refund. "
            + _policy_sentence("refunds.md", "30 days")
        )
    else:
        amount = _refund_amount(order)
        calls.append({"name": "issue_refund", "args": {"order_id": order_id, "amount_cents": amount}})
        confirmation = tools.issue_refund(order_id, amount)
        text = (
            f"I've issued a refund of ${amount:.2f} for order {order_id} "
            f"(confirmation {confirmation['refund_id']}). "
            + _policy_sentence("refunds.md", "original payment method")
        )
    return _response(text.strip(), messages, citations=["refunds.md"], hits=hits, tool_calls=calls)


def _policy_sentence(doc_id: str, phrase: str) -> str:
    _notes, sentences = _split_document(get_document(doc_id))
    return next((s for s in sentences if phrase.lower() in s.lower()), "")


# --------------------------------------------------------------------------- #
# Policy questions (retrieval + extractive answer)
# --------------------------------------------------------------------------- #


def _answer_from_policies(question: str, messages: list[dict]) -> dict:
    hits = retrieve(question, k=TOP_K)
    if not hits or hits[0][1] < MIN_SCORE:
        return _response(FALLBACK_ANSWER, messages, hits=hits)

    doc_id, _score, text = hits[0]
    reply = " ".join(_compose(question, text))
    if _REFUND_RE.search(question):
        reply += " If you'd like me to start a refund, just tell me your order number."
    return _response(reply, messages, citations=[doc_id], hits=hits)


def _split_document(text: str) -> tuple[list[str], list[str]]:
    """Split a Markdown policy doc into (notes, sentences), skipping headings."""
    notes: list[str] = []
    sentences: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        note = _NOTE_RE.match(line)
        if note:
            notes.append(note.group(1).strip())
            continue
        sentences.extend(s.strip() for s in _SENTENCE_END_RE.split(line) if s.strip())
    return notes, sentences


def _compose(question: str, doc_text: str) -> list[str]:
    """Pick the sentences of ``doc_text`` that best match ``question``.

    Notes carry caveats the customer must always see, so they get a slot
    first; the remaining slots go to the best matching sentences, kept in
    document order so the answer reads naturally.
    """
    notes, sentences = _split_document(doc_text)
    query_terms = set(tokenize(question))

    overlaps = [len(query_terms & set(tokenize(s))) for s in sentences]
    ranked = sorted((i for i, overlap in enumerate(overlaps) if overlap), key=lambda i: (-overlaps[i], i))
    if not ranked and sentences:
        ranked = [0]

    note_lines = [f"Please note: {note}" for note in notes][:MAX_ANSWER_SENTENCES]
    room = MAX_ANSWER_SENTENCES - len(note_lines)
    body = [sentences[i] for i in sorted(ranked[:room])]
    return body + note_lines


# --------------------------------------------------------------------------- #
# Response shape
# --------------------------------------------------------------------------- #


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (whitespace-separated words), not a real tokenizer."""
    return len(text.split())


def _response(
    text: str,
    messages: list[dict],
    *,
    citations: list[str] | None = None,
    hits: list[tuple[str, float, str]] | tuple = (),
    tool_calls: list[dict] | None = None,
) -> dict:
    prompt = " ".join(m["content"] for m in messages)
    context = " ".join(doc_text for _doc_id, _score, doc_text in hits)
    return {
        "answer": text,
        "citations": list(citations or []),
        "retrieved": [doc_id for doc_id, _score, _text in hits],
        "tool_calls": list(tool_calls or []),
        "usage": {
            "input_tokens": _estimate_tokens(prompt) + _estimate_tokens(context),
            "output_tokens": _estimate_tokens(text),
        },
    }
