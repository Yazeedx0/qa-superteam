# AI eval metrics

Each metric names its oracle and where it is measured: an `expect` key in the dataset
(per case, via `qast exec ai-eval`), a pytest invariant over many cases (via `qast exec
pytest --group ai-eval`), or a calibrated judge. Report counts with the denominators; never a bare percentage.

## Definitions

| Metric | Definition | Measured by | Caveats |
|---|---|---|---|
| Answer correctness | The answer states the required facts and no contradicting ones | `contains`, `regex`, `not_contains` | Anchor on facts (numbers, ids, names), not phrasing |
| Groundedness | Every factual claim is supported by a document the system cites | Deterministic proxy: correct `citations_include` + invariant "citations ⊆ retrieved" + key facts found in the cited text; paraphrase faithfulness only by a calibrated judge | A citation list that is right while the text invents details still fails groundedness |
| Citation accuracy | The cited document is the one that answers; nothing is cited when nothing answers | `citations_include`; invariant "refusal ⇒ no citations" | `citations_include` is a subset check; extra citations need the invariant test |
| Retrieval hit | The relevant document is among the retrieved ones | `retrieved_include` | Binary per case |
| Recall@k | relevant ∩ top-k retrieved / relevant, averaged over cases with labelled relevant sets | pytest invariant | Relevant sets come from a human reading the corpus, not from the system |
| Context utilization | When the relevant document was retrieved, the answer uses it | Cases where `retrieved_include` passed but correctness failed = "retrieved but unused" | Separates retrieval defects from generation defects |
| Tool-call correctness | Right tool, right arguments with exact types and values | `tool_calls` with strict comparison | `4999` (int cents) ≠ `49.99` (float dollars) ≠ `"4999"` |
| Trajectory validity | Allowed sequence of calls: preconditions before actions, nothing forbidden | `tool_calls_mode`, `forbidden_tools` | See trajectory-testing.md |
| Refusal accuracy | Refuses what it must (unanswerable, secrets, out of scope) and answers what it can | `refusal: true` and `refusal: false` cases | The detector is a phrase heuristic; read failing answers |
| Hallucination risk | Rate of confident answers to unanswerable cases, and invented specifics | Unanswerable family with `refusal: true` + `not_contains` of plausible inventions | Measures the cases you wrote, not all hallucination |
| Injection resistance | Share of injection cases where the canary is neither repeated nor acted on | `not_contains` canary + `forbidden_tools` | Release-blocking at any failure for a security finding |
| Secret leakage | Answers containing secrets, system prompt or internal codes | `not_contains`, `refusal` | Zero tolerance |
| Multi-turn consistency | Earlier facts and entities are carried forward; corrections override; no stale entity leaks into a new topic | Multi-turn cases with `tool_calls` / `contains` | Write the assistant turns yourself for reproducibility |
| Instruction adherence | Format, language, length and persona rules from the requirements | `regex`, `max_output_tokens`, judge for tone | |
| Nondeterminism | Share of cases whose samples disagree | `--samples N` ⇒ INCONCLUSIVE cases / cases | Temperature, retrieval ties, tool timing |
| Latency | p50/p95/max of the in-process entry call | `ai-eval-summary.json` → `latency_ms`; `max_latency_ms` per case | This machine, this provider, this moment: not an SLO measurement |
| Tokens and cost | Output tokens per case; cost = tokens × documented price | `usage` from the system; otherwise qast's word-count estimate | Label every figure **measured** (provider-reported usage) or **estimated** (word counts, or a system that itself estimates); `usage_estimated: false` only means the system reported a number |
| Pass rate | PASSED / (PASSED + FAILED) | `ai-eval-summary.json`, gate rule `R-AI-EVAL-PASS-RATE` | INCONCLUSIVE and ERROR are excluded from the rate and go to review |

## Cross-case invariants (pytest)

Properties that hold for every case belong in a parametrized test that loads the dataset
and calls the entry function directly. The import must be the same function passed to
`--entry`. These tests were executed against an example RAG bot.

```python
import json
from pathlib import Path

import pytest

from assistant.entry import answer          # the module:function used as --entry

DATASET = Path(__file__).parent / "ai" / "support_cases.jsonl"
CASES = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()
         if line.strip() and not line.lstrip().startswith("//")]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_citations_are_subset_of_retrieved(case):
    out = answer(case["input"])
    assert set(out["citations"]) <= set(out["retrieved"]), (out["citations"], out["retrieved"])


@pytest.mark.parametrize("case", [c for c in CASES if "unanswerable" in c.get("tags", [])],
                         ids=lambda c: c["id"])
def test_unanswerable_cases_cite_nothing(case):
    assert answer(case["input"])["citations"] == []


# relevant documents per question, labelled by a person reading the corpus
RELEVANT = {
    "how long do I have to return a jacket": {"returns.md"},
    "what does the warranty cover": {"warranty.md"},
}


def test_mean_recall_at_3():
    recalls = [len(rel & set(answer(q)["retrieved"][:3])) / len(rel) for q, rel in RELEVANT.items()]
    assert sum(recalls) / len(recalls) >= 0.9, recalls
```

For a deterministic system add `assert answer(x) == answer(x)` over the dataset; for a
model-backed one use `--samples` instead. Streaming: assert that the concatenated chunks
equal the non-streamed answer for the same input (see trajectory-testing.md).

## Baseline comparison

For a prompt, model, retriever or chunking change, the question is "what changed", not
"what is the pass rate". Run the **same dataset file** on both versions and compare per case.

1. Freeze the dataset first; both runs must use the identical file (its stem is part of
   every result id).
2. The gate counts every ai-eval execution in a run, so record the baseline in its own run:
   `qast run start --mode eval-ai --scope "baseline <ref>"`, then
   `git worktree add <tmpdir>/base <base-ref>` and
   `qast exec ai-eval --group ai-eval --label baseline:<base-ref> --cwd <tmpdir>/base --dataset <absolute path to the dataset> --entry <fn> --samples 3`,
   then `qast run finish`. Start (or resume, passing `--run <id>` to every command) the run
   for the candidate and execute it with `--label candidate`. Remove the worktree afterwards
   (`git worktree remove <tmpdir>/base`).
3. Compare per case from the two execution records
   (`.qa-superteam/runs/<run>/executions/<execution id>.json`):

```bash
python3 - <baseline execution json> <candidate execution json> <<'EOF'
import json, sys
before, after = ({r["identifier"]: r["status"] for r in json.load(open(p))["results"]} for p in sys.argv[1:3])
for case in sorted(before.keys() | after.keys()):
    b, a = before.get(case, "ABSENT"), after.get(case, "ABSENT")
    if b != a:
        kind = {("PASSED", "FAILED"): "REGRESSION", ("FAILED", "PASSED"): "FIXED"}.get((b, a), "CHANGED")
        print(f"{kind:<10} {case}: {b} -> {a}")
EOF
```

4. Report regressions (each one is a finding candidate: triage like any FAILED case),
   fixes, and cases that became INCONCLUSIVE. Equal pass rates can hide offsetting
   regressions and fixes; the per-case diff cannot.
5. If the baseline cannot be run (no ref, no environment), say so; do not compare against
   numbers from another machine, provider or day.
