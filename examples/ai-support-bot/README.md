# ai-support-bot

A small, deterministic stand-in for an LLM-powered customer-support assistant
for the fictional store **Northwind Goods**. It has the same shape as a real
RAG + tool-calling app, but runs entirely offline on the Python 3.11+ standard
library: no model, no API keys, no network, and the same request always gets
the same response.

What it does:

- **Retrieval**: a BM25 retriever (`support_bot/retriever.py`) over the
  Markdown policy documents in `support_bot/corpus/`.
- **Answering**: `support_bot/bot.py` composes an extractive answer from the
  best-matching sentences of the top document and cites it. Questions the
  corpus cannot answer get a polite "I don't know, please contact support".
- **Tool calling**: refund requests that mention an order id (e.g. `A1001`)
  call `lookup_order` and, when the order is eligible, `issue_refund`
  (`support_bot/tools.py`, an in-memory order table).
- **Multi-turn**: a conversation can be passed in; the last user message is
  answered and an order id from earlier turns is carried forward.

Requirements the assistant must meet are in
[`docs/AI_REQUIREMENTS.md`](docs/AI_REQUIREMENTS.md).

## Usage

```bash
python3 -c "from support_bot.bot import answer; print(answer('how long does standard shipping take'))"
```

Multi-turn:

```python
from support_bot.bot import answer

answer({"messages": [
    {"role": "user", "content": "I have a question about order A1003"},
    {"role": "assistant", "content": "Sure, what would you like to know?"},
    {"role": "user", "content": "can i get a refund for it"},
]})
```

Every call returns a dict like this (for the shipping question above):

```json
{
  "answer": "Standard shipping takes 5-7 business days and is free on orders over $50. ...",
  "citations": ["shipping.md"],
  "retrieved": ["shipping.md", "refunds.md", "returns.md"],
  "tool_calls": [],
  "usage": {"input_tokens": 272, "output_tokens": 38}
}
```

For refund requests, `tool_calls` lists each call in order, e.g.
`[{"name": "lookup_order", "args": {"order_id": "A1002"}}]`.

`usage` is an estimate (whitespace-separated word counts of the conversation
plus retrieved context, and of the answer), not a real tokenizer count.

## Testing

Unit tests:

```bash
python3 -m pytest -q
```

Golden dataset for answer-quality evals: `evals/golden.jsonl`, one case per
line:

```json
{"id": "shipping-001", "input": "how long does standard shipping take", "tags": ["rag"],
 "expect": {"contains": ["5-7 business days"], "citations_include": ["shipping.md"], "retrieved_include": ["shipping.md"]}}
```

`input` is either a string or `{"messages": [...]}`. Supported `expect` keys:
`contains`, `not_contains`, `regex`, `citations_include`, `retrieved_include`,
`tool_calls` (with `tool_calls_mode`: `ordered-subset`, `exact` or `subset`),
`forbidden_tools`, `refusal`, `max_output_tokens`, `max_latency_ms`. A case may
also carry a `judge` rubric for model-graded checks, which needs model
credentials to run.

## Layout

```
support_bot/
  bot.py          answer(request) -> dict
  retriever.py    BM25 retrieval over the corpus
  tools.py        lookup_order / issue_refund over an in-memory order table
  corpus/*.md     store policy documents and community FAQ
tests/            unit tests (pytest)
evals/golden.jsonl
docs/AI_REQUIREMENTS.md
```
