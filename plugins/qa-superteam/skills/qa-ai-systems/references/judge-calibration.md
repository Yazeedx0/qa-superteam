# Judge calibration protocol

An LLM judge is a measuring instrument. An instrument nobody has checked against a
reference is not evidence, so qast applies this policy (`qa_superteam/aieval.py`):

| Judge state | Effect on the case |
|---|---|
| No `--judge-model`, or no SDK/credentials | judge check NOT_RUN; deterministic checks decide |
| Judge answers `uncertain`, refuses, or returns malformed output | INCONCLUSIVE |
| No `--calibration` file, or its kappa < 0.6 | any verdict ⇒ INCONCLUSIVE ("not trusted as a verdict") |
| Calibrated, kappa ≥ 0.6 | verdict counts, reported with kappa and n |
| Any deterministic check failed | FAILED regardless of the judge |

A judge never overrides a deterministic failure, and it is never ground truth: even a
calibrated judge is an estimate of human judgment with a known error rate.

## 1. Decide whether a judge is needed

Use one only for properties no deterministic check can express: tone, empathy,
completeness of an explanation, whether a paraphrase preserves meaning, adherence to a
style guide. Do not use one for facts (use `contains`/`regex`), citations, tool calls,
refusals of known secret requests, or injection canaries.

What the qast judge sees: the rubric, the user input, the **ids** of retrieved documents,
and the answer. It does not see document text, so it cannot check faithfulness to a
source. Groundedness stays with deterministic proxies and human review.

## 2. Write the rubric

- Binary and observable: "PASS only if the reply (a) acknowledges the damage, (b) states the
  remedy the policy offers, (c) offers no compensation beyond it. FAIL otherwise."
- One property per rubric; split compound qualities into separate cases.
- Say when to answer `uncertain` ("if the rubric cannot be applied from the text shown").
- Freeze it. Calibration is valid only for this exact text.

## 3. Build the calibration set

- **At least 30 cases** (qast computes kappa for any n; the minimum is this protocol's
  rule). More when classes are imbalanced: aim for at least 10 human-PASS and 10 human-FAIL.
- Drawn from the same distribution as the eval cases, including borderline answers. Real
  failing answers are the most valuable; collect them from earlier runs.
- Preferably disjoint from the cases you will evaluate; if they overlap, say so in the summary.

## 4. Get judge verdicts

Run the calibration set with the judge and without a calibration file. Every judged case
becomes INCONCLUSIVE, which is expected; the verdicts are stored in the results artifact.
The gate counts every ai-eval execution in a run, so do this in its own run
(`qast run start --mode eval-ai --scope "judge calibration <model>"` ... `qast run finish`),
as for a baseline (metrics.md).

```
qast exec ai-eval --group ai-eval --label judge-calibration --dataset tests/qa/ai/calibration_cases.jsonl \
  --entry <module:function> --judge-model <model id>
```

Extract `{id, label}` lines from that execution's `ai-eval-results.jsonl` evidence
(`.qa-superteam/runs/<run>/artifacts/<evidence id>-ai-eval-results.jsonl`):

```bash
python3 - <path to ai-eval-results.jsonl> > tests/qa/ai/judge_labels.jsonl <<'EOF'
import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    rec = json.loads(line)
    verdict = (rec.get("judge") or {}).get("verdict")
    if verdict:
        print(json.dumps({"id": rec["id"], "label": verdict}))
EOF
```

Keep `uncertain` verdicts in the file: they count as disagreement, which is the conservative choice.

## 5. Human labels (from humans only)

The labels file is `{"id": "...", "label": "pass"|"fail"}` per line, written by people
applying the same rubric **without seeing the judge's verdicts**. You may prepare a
labelling sheet; you must never fill in labels yourself, infer them from the judge, or
"approximate" them. Without human labels the judge stays uncalibrated, and that is the
correct, reportable outcome.

```bash
python3 - tests/qa/ai/calibration_cases.jsonl <path to ai-eval-results.jsonl> > labelling-sheet.md <<'EOF'
import json, sys
cases = {}
for line in open(sys.argv[1], encoding="utf-8"):
    if line.strip() and not line.lstrip().startswith("//"):
        case = json.loads(line)
        cases[case["id"]] = case
cell = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
print("| id | input | answer | rubric | label (pass/fail) |\n|---|---|---|---|---|")
for line in open(sys.argv[2], encoding="utf-8"):
    rec = json.loads(line)
    case = cases.get(rec["id"])
    if case and case.get("judge"):
        print(f"| {rec['id']} | {cell(case['input'])} | {cell(rec['answer_preview'])} | {cell(case['judge']['rubric'])} | |")
EOF
```

`answer_preview` holds the first 600 characters; give labellers the full answer (call the
entry function) when answers are longer. Two independent labellers with disagreements
resolved by discussion produce better labels than one.

## 6. Compute agreement

```
qast ai-eval calibrate --judgments tests/qa/ai/judge_labels.jsonl --labels tests/qa/ai/human_labels.jsonl \
  --judge-model <model id> --rubric-id <rubric short hash> \
  --out tests/qa/ai/calibration-<model id>-<rubric short hash>.json
```

Read the output, not only kappa:

- `n`: below 30 ⇒ do not use the judge, whatever kappa says (qast enforces this: such a judge never produces PASSED/FAILED).
- `kappa` (Cohen's κ = (pₒ − pₑ) / (1 − pₑ), agreement corrected for chance): below 0.6 ⇒
  untrusted (qast enforces this). 0.6-0.8 is substantial, above 0.8 strong. High raw
  agreement with low kappa means the classes are imbalanced and the judge may simply say
  "pass" to everything.
- `confusion_human_by_judge` (rows = human, columns = judge): the **human fail / judge pass**
  cell is the dangerous one, because a lenient judge hides defects. Report it explicitly.
- `disagreements`: read them; a pattern (always wrong on one kind of answer) means the
  rubric needs work, and a changed rubric means starting again at step 3.

## 7. Use the calibrated judge

```
qast exec ai-eval --group ai-eval --dataset tests/qa/ai/support_cases.jsonl --entry <module:function> \
  --judge-model <same model id> --calibration tests/qa/ai/calibration-<model id>-<hash>.json
```

Report every judge-based outcome with the model id, kappa, n and the lenient-cell count.

## 8. Re-calibrate when

- the judge model id or version changes, or the provider's fallback serves a different model;
- the rubric text changes;
- the judge prompt template changes (a plugin upgrade can change it);
- the system under test or its data distribution changes enough that answers look different;
- an INCONCLUSIVE review shows the judge disagreeing with humans more than the calibration predicted.

qast does not bind a calibration file to a model or rubric. The file name and a
`qast run note --kind assumption "calibration <file> was produced for <model> / rubric <hash>"`
carry that binding. A mismatch means the judge is uncalibrated.

## 9. INCONCLUSIVE ⇒ human review

List INCONCLUSIVE cases (judge uncertain, uncalibrated, or samples disagreeing) with input,
answer and reason for a person to decide. Record what the person decided with
`qast run note --kind decision "<case id>: <reviewer>: <pass|fail> because ..."`. Until then
the case is unresolved, and the gate's `R-AI-EVAL-INCONCLUSIVE` rule requires review.

## Known judge biases

- **Self-preference**: a judge from the same model family as the system under test rates it
  higher. Prefer a different family, or disclose it.
- **Verbosity**: longer answers get higher scores. Include short correct and long wrong
  answers in the calibration set.
- **Injection**: answers can contain text addressed to the judge. The judge prompt treats the
  response as data, but injection and secret cases must be decided by deterministic checks.
- **Drift**: the same model id can behave differently over time; dated calibrations age.
