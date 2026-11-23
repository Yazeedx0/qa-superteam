# Tool-call, agent and trajectory testing

## How qast matches tool calls

`expect.tool_calls` is a list of `{name, args}`; the system reports `tool_calls` in call
order. A call matches when the name is equal and **every listed arg key** is present with a
strictly equal value (same type and value; nested dicts and lists compared the same way).
Arg keys you do not list are not compared: list the ones the requirement fixes, leave out
volatile ones (timestamps, generated ids).

| `tool_calls_mode` | Passes when | Use for |
|---|---|---|
| `ordered-subset` (default) | expected calls appear in this order, other calls may be interleaved | "look up before acting" while tolerating extra harmless reads |
| `exact` | same number of calls, pairwise matching in order | fully specified flows (refund = lookup then refund, nothing else) |
| `subset` | every expected call appears somewhere | order genuinely irrelevant (parallel independent reads) |

Pair every positive expectation with the negative one: `forbidden_tools` for actions that must
not happen in that case (refund on an ineligible order, any tool for an out-of-scope request,
a privileged tool requested inside retrieved text).

## Argument correctness

The most valuable tool assertions are the boring ones:

- **Units and types**: money in integer minor units (`4999`), not floats (`49.99`) or strings;
  quantities as integers; booleans not `"true"`.
- **Identity**: the id from the conversation, normalized as the tool expects (case, prefix).
- **Source of the value**: the amount comes from the looked-up record, not from the user's
  claim ("refund me $500 for order X" must refund the order total).
- **Schema**: arguments validate against the tool's declared JSON schema. A pytest invariant can
  run every recorded call through `jsonschema` if the project already uses it, or a hand-written
  type check against the declared `properties` otherwise.

## Trajectory validity

Express rules as cases, one rule per case:

| Rule | Case design |
|---|---|
| Precondition before action | `exact` or `ordered-subset` with lookup before action |
| No action without eligibility | ineligible input + `forbidden_tools: [action]` + explanation `regex` |
| No repeated side effects | `exact` with a single action call (catches retry loops in the agent) |
| Bounded steps | count calls in a pytest invariant over the dataset (`len(tool_calls) <= N`) |
| Untrusted text cannot trigger tools | injection document asks for the action + `forbidden_tools` |
| Human confirmation for destructive tools | the first turn must not call the tool; a confirming second turn may |

## When the app does not report tool calls

Write an adapter entry under `test_dir` (needs `write_tests`) that runs the real agent and
records calls by wrapping the tool functions, then pass it as `--entry`. Executed with
`qast exec ai-eval --entry tests.qa.ai.entry:answer` against an example agent:

```python
"""Eval adapter: maps the app's agent to the qast ai-eval contract and records tool calls."""
import inspect

from myapp import agent, tools

RECORDED_TOOLS = ("lookup_order", "issue_refund")


def answer(request):
    calls = []
    originals = {name: getattr(tools, name) for name in RECORDED_TOOLS}

    def recorder(name, fn):
        def wrapper(*args, **kwargs):
            calls.append({"name": name, "args": dict(inspect.signature(fn).bind(*args, **kwargs).arguments)})
            return fn(*args, **kwargs)
        return wrapper

    try:
        for name, fn in originals.items():
            setattr(tools, name, recorder(name, fn))
        result = agent.run(request)
    finally:
        for name, fn in originals.items():
            setattr(tools, name, fn)
    return {
        "answer": result.text,
        "citations": list(result.sources),
        "retrieved": list(result.retrieved_ids),
        "tool_calls": calls,
        "usage": dict(result.usage),
    }
```

Wrapping works when the agent looks tools up at call time (`tools.lookup_order(...)` or a
registry dict). If it bound them at import (`from tools import lookup_order`), wrap the name in
the agent's module or the registry the framework uses (most agent frameworks keep a tool
list you can wrap). If the tools have real side effects, the adapter must substitute
sandbox fakes, not just record. For frameworks with callbacks or tracing (LangChain callbacks,
OpenTelemetry spans), collecting calls from the trace is an alternative; the output shape stays the same.

## Multi-agent systems

- **Routing**: the request reaches the right sub-agent (record handoffs like tool calls:
  `{"name": "handoff", "args": {"to": "billing"}}`) and `exact` the expected route.
- **Context passing**: facts established before the handoff (ids, constraints) arrive intact;
  test with a fact only stated before the handoff.
- **Termination**: the conversation between agents ends within a step budget; assert the
  number of handoffs per case.
- **Authority**: a sub-agent cannot use a tool its role lacks, even when another agent asks it to.

## Memory

- **Isolation**: memory written in user A's session never surfaces for user B (run A's case,
  then B's case in the same process; `not_contains` A's unique fact). This is a security finding when it fails.
- **Persistence**: a fact from session 1 is available in session 2 when the product promises it.
- **Forgetting**: deleted or expired memory is no longer used.
- **Poisoning**: an instruction stored as a "memory" by one turn does not change behaviour later
  (same canary approach as retrieved content).

## Streaming

- Concatenated chunks equal the non-streamed answer for the same input (or both pass the same oracle).
- No forbidden content appears in any chunk, even if a later filter removes it from the final
  text: check the chunks, not only the assembled answer.
- Tool calls emitted during streaming are complete and valid JSON when assembled.
- Time to first chunk and total time are reported separately, labelled as measured on this machine.
- Cancellation mid-stream leaves no half-executed tool action.

## Realtime and voice

Evaluate the text layer with the same datasets (transcripts as input). Additionally test
barge-in (a new user turn cancels the pending answer and any pending tool action), partial
transcripts (no action on an incomplete utterance), and latency to first audio as a measured,
environment-labelled number. Audio quality itself needs human review; record it as not verified otherwise.
