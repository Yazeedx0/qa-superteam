"""AI system evaluation: deterministic checks, sampling, judge calibration.

Pure functions only (no I/O, no network) so the logic is unit-testable without any
model.  The runner (:mod:`qa_superteam.runners.ai_eval`) imports the system under
test and feeds its outputs through :func:`evaluate_case`.

Target contract — a callable ``target(request) -> dict`` where ``request`` is the
dataset ``input`` (a string or ``{"messages": [...]}``) and the dict contains::

    answer: str                       (required)
    citations: list[str]              (optional, source ids the answer relies on)
    retrieved: list[str]              (optional, ids returned by retrieval)
    tool_calls: list[{name, args}]    (optional, in call order)
    usage: {input_tokens, output_tokens}  (optional; otherwise estimated)

Judge policy — model-graded verdicts are never treated as ground truth:

* no judge configured            -> judge check NOT_RUN
* judge says "uncertain"/refuses -> INCONCLUSIVE
* judge not calibrated, or Cohen's kappa against human labels below ``min_kappa``
                                  -> any judge verdict yields INCONCLUSIVE
* calibrated judge                -> verdict counts, reported with its kappa
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ALLOWED_EXPECT_KEYS = {
    "contains",
    "not_contains",
    "regex",
    "citations_include",
    "retrieved_include",
    "tool_calls",
    "tool_calls_mode",
    "forbidden_tools",
    "refusal",
    "max_output_tokens",
    "max_latency_ms",
}
ALLOWED_CASE_KEYS = {"id", "input", "expect", "tags", "judge", "notes"}

DEFAULT_REFUSAL_MARKERS = (
    "i can't",
    "i cannot",
    "i can not",
    "i'm unable",
    "i am unable",
    "i'm not able",
    "i am not able",
    "i won't",
    "i will not",
    "i don't know",
    "i do not know",
    "not able to help",
    "can't help with",
    "cannot help with",
    "please contact support",
    "contact our support",
)


class DatasetError(ValueError):
    pass


@dataclass
class CheckResult:
    name: str
    passed: bool | None  # None = not run
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class CaseOutcome:
    case_id: str
    status: str  # PASSED | FAILED | ERROR | INCONCLUSIVE | NOT_RUN
    checks: list[CheckResult] = field(default_factory=list)
    reason: str = ""
    latency_ms: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    usage_estimated: bool = False
    answer_preview: str = ""
    samples: list[str] = field(default_factory=list)
    judge: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "status": self.status,
            "reason": self.reason,
            "checks": [c.as_dict() for c in self.checks],
            "latency_ms": self.latency_ms,
            "usage": self.usage,
            "usage_estimated": self.usage_estimated,
            "answer_preview": self.answer_preview,
            "samples": self.samples,
            "judge": self.judge,
            "tags": self.tags,
        }


def validate_case(case: Any, line_no: int | None = None) -> dict[str, Any]:
    where = f"line {line_no}: " if line_no else ""
    if not isinstance(case, dict):
        raise DatasetError(f"{where}case must be an object")
    unknown = set(case) - ALLOWED_CASE_KEYS
    if unknown:
        raise DatasetError(f"{where}unknown case keys: {sorted(unknown)}")
    if not isinstance(case.get("id"), str) or not case["id"]:
        raise DatasetError(f"{where}case needs a string id")
    if "input" not in case:
        raise DatasetError(f"{where}case {case['id']} needs an input")
    exp = case.get("expect", {})
    if not isinstance(exp, dict):
        raise DatasetError(f"{where}expect must be an object")
    bad = set(exp) - ALLOWED_EXPECT_KEYS
    if bad:
        raise DatasetError(f"{where}case {case['id']}: unsupported expect keys {sorted(bad)}")
    mode = exp.get("tool_calls_mode", "ordered-subset")
    if mode not in ("ordered-subset", "exact", "subset"):
        raise DatasetError(f"{where}case {case['id']}: invalid tool_calls_mode {mode!r}")
    if not exp and "judge" not in case:
        raise DatasetError(f"{where}case {case['id']} has no oracle (empty expect and no judge)")
    return case


def parse_dataset(text: str) -> list[dict[str, Any]]:
    import json

    cases = []
    seen: set[str] = set()
    for i, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise DatasetError(f"line {i}: invalid JSON: {e}") from None
        validate_case(obj, i)
        if obj["id"] in seen:
            raise DatasetError(f"line {i}: duplicate case id {obj['id']}")
        seen.add(obj["id"])
        cases.append(obj)
    if not cases:
        raise DatasetError("dataset is empty")
    return cases


def estimate_tokens(text: str) -> int:
    """Whitespace token estimate. Labelled as an estimate wherever it is reported."""
    return len(text.split())


def strict_equal(a: Any, b: Any) -> bool:
    """Equality that does not conflate 4999 with 49.99, 1 with True, or 5 with 5.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(strict_equal(x, y) for x, y in zip(a, b, strict=False))
    return type(a) is type(b) and a == b


def args_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(k in actual and strict_equal(v, actual[k]) for k, v in expected.items())


def match_tool_calls(expected: list[dict], actual: list[dict], mode: str) -> tuple[bool, str]:
    def fmt(calls):
        return ", ".join(f"{c.get('name')}({c.get('args', {})})" for c in calls) or "none"

    def one(e, a):
        return e.get("name") == a.get("name") and args_match(e.get("args", {}) or {}, a.get("args", {}) or {})

    if mode == "exact":
        ok = len(expected) == len(actual) and all(one(e, a) for e, a in zip(expected, actual, strict=False))
    elif mode == "subset":
        ok = all(any(one(e, a) for a in actual) for e in expected)
    else:  # ordered-subset
        i = 0
        for a in actual:
            if i < len(expected) and one(expected[i], a):
                i += 1
        ok = i == len(expected)
    return ok, f"expected [{fmt(expected)}] ({mode}); actual [{fmt(actual)}]"


def is_refusal(answer: str, markers: tuple[str, ...] = DEFAULT_REFUSAL_MARKERS) -> bool:
    low = answer.lower().replace("’", "'")
    return any(m in low for m in markers)


def deterministic_checks(expect: dict[str, Any], output: dict[str, Any], latency_ms: float | None) -> tuple[list[CheckResult], dict, bool]:
    answer = str(output.get("answer", ""))
    low = answer.lower()
    checks: list[CheckResult] = []
    for s in expect.get("contains", []) or []:
        checks.append(CheckResult(f"contains:{s}", s.lower() in low, "" if s.lower() in low else f"answer lacks {s!r}"))
    for s in expect.get("not_contains", []) or []:
        checks.append(CheckResult(f"not_contains:{s}", s.lower() not in low, "" if s.lower() not in low else f"answer contains forbidden {s!r}"))
    if expect.get("regex"):
        ok = re.search(expect["regex"], answer, re.I | re.S) is not None
        checks.append(CheckResult("regex", ok, "" if ok else f"no match for /{expect['regex']}/"))
    for key, field_name in (("citations_include", "citations"), ("retrieved_include", "retrieved")):
        if key in expect:
            have = list(output.get(field_name) or [])
            missing = [x for x in expect[key] if x not in have]
            checks.append(CheckResult(key, not missing, f"missing {missing}; got {have}" if missing else ""))
    calls = list(output.get("tool_calls") or [])
    if "tool_calls" in expect:
        ok, detail = match_tool_calls(expect["tool_calls"], calls, expect.get("tool_calls_mode", "ordered-subset"))
        checks.append(CheckResult("tool_calls", ok, "" if ok else detail))
    for name in expect.get("forbidden_tools", []) or []:
        used = any(c.get("name") == name for c in calls)
        checks.append(CheckResult(f"forbidden_tool:{name}", not used, f"{name} was called" if used else ""))
    if "refusal" in expect:
        got = is_refusal(answer)
        want = bool(expect["refusal"])
        checks.append(CheckResult("refusal", got == want, "" if got == want else f"refusal expected={want} detected={got} (heuristic markers)"))
    usage = dict(output.get("usage") or {})
    estimated = False
    if "output_tokens" not in usage:
        usage["output_tokens"] = estimate_tokens(answer)
        estimated = True
    if "max_output_tokens" in expect:
        ok = usage["output_tokens"] <= expect["max_output_tokens"]
        label = " (estimated)" if estimated else ""
        checks.append(CheckResult("max_output_tokens", ok, "" if ok else f"{usage['output_tokens']}{label} > {expect['max_output_tokens']}"))
    if "max_latency_ms" in expect and latency_ms is not None:
        ok = latency_ms <= expect["max_latency_ms"]
        checks.append(CheckResult("max_latency_ms", ok, "" if ok else f"{latency_ms:.1f}ms > {expect['max_latency_ms']}ms"))
    return checks, usage, estimated


@dataclass
class JudgeConfig:
    available: bool
    reason: str = ""
    kappa: float | None = None
    min_kappa: float = 0.6
    calibration_n: int = 0

    @property
    def trusted(self) -> bool:
        return self.available and self.kappa is not None and self.kappa >= self.min_kappa


def apply_judge(verdict: dict[str, Any] | None, judge: JudgeConfig) -> tuple[str | None, CheckResult, dict[str, Any]]:
    """Map a judge verdict to (status_override, check, judge_info). status_override None = no effect."""
    if not judge.available or verdict is None:
        info = {"status": "NOT_RUN", "reason": judge.reason or "judge not configured"}
        return None, CheckResult("judge", None, info["reason"]), info
    v = str(verdict.get("verdict", "")).lower()
    info = {
        "verdict": v,
        "rationale": str(verdict.get("rationale", ""))[:1000],
        "kappa": judge.kappa,
        "min_kappa": judge.min_kappa,
        "calibration_n": judge.calibration_n,
        "model": verdict.get("model"),
    }
    if v not in ("pass", "fail"):
        info["status"] = "INCONCLUSIVE"
        return "INCONCLUSIVE", CheckResult("judge", None, f"judge returned {v or 'no verdict'}"), info
    if not judge.trusted:
        info["status"] = "INCONCLUSIVE"
        why = "judge is uncalibrated" if judge.kappa is None else f"judge kappa {judge.kappa:.2f} < {judge.min_kappa}"
        return "INCONCLUSIVE", CheckResult("judge", None, f"judge said {v} but {why}; not trusted as a verdict"), info
    info["status"] = "PASSED" if v == "pass" else "FAILED"
    return info["status"], CheckResult("judge", v == "pass", f"calibrated judge (kappa {judge.kappa:.2f}) said {v}"), info


def combine_samples(statuses: list[str]) -> tuple[str, str]:
    """Several samples of the same case: disagreement means the result is not trustworthy."""
    if not statuses:
        return "NOT_RUN", "no samples"
    if "ERROR" in statuses:
        return "ERROR", f"target raised in {statuses.count('ERROR')}/{len(statuses)} samples"
    uniq = set(statuses)
    if len(uniq) == 1:
        return statuses[0], ""
    return "INCONCLUSIVE", f"nondeterministic: {statuses.count('FAILED')}/{len(statuses)} samples failed"


def case_status(checks: list[CheckResult], judge_override: str | None) -> tuple[str, str]:
    det = [c for c in checks if c.name != "judge"]
    failed = [c for c in det if c.passed is False]
    if failed:
        return "FAILED", "; ".join(f"{c.name}: {c.detail}" for c in failed)
    if judge_override == "FAILED":
        return "FAILED", "calibrated judge failed the answer"
    if judge_override == "INCONCLUSIVE":
        return "INCONCLUSIVE", next((c.detail for c in checks if c.name == "judge"), "judge inconclusive")
    if not [c for c in det if c.passed is not None] and judge_override is None:
        return "NOT_RUN", "only model-graded checks were defined and no trusted judge ran"
    return "PASSED", ""


# --------------------------------------------------------------------------- calibration


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Cohen's kappa for two raters over the same items. None if undefined."""
    if len(a) != len(b) or not a:
        return None
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(1 for x, y in zip(a, b, strict=False) if x == y) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    if pe >= 1.0:
        return 1.0 if po == 1.0 else None
    return (po - pe) / (1 - pe)


def calibrate(judgments: dict[str, str], human: dict[str, str]) -> dict[str, Any]:
    """Compare judge labels with human labels on shared case ids."""
    shared = sorted(set(judgments) & set(human))
    j = [judgments[k] for k in shared]
    h = [human[k] for k in shared]
    labels = sorted(set(j) | set(h))
    confusion = {hl: {jl: 0 for jl in labels} for hl in labels}
    for hv, jv in zip(h, j, strict=False):
        confusion[hv][jv] += 1
    agree = sum(1 for x, y in zip(j, h, strict=False) if x == y)
    kappa = cohen_kappa(h, j)
    return {
        "n": len(shared),
        "agreement": (agree / len(shared)) if shared else None,
        "kappa": kappa,
        "confusion_human_by_judge": confusion,
        "disagreements": [k for k in shared if judgments[k] != human[k]],
        "unmatched_judgments": sorted(set(judgments) - set(human)),
        "unlabeled_by_human": sorted(set(judgments) - set(human)),
        "note": "kappa < 0.6 is commonly read as weak agreement; QA Superteam treats such judges as untrusted",
    }


def summarize(outcomes: list[CaseOutcome]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.status] = counts.get(o.status, 0) + 1
    decided = counts.get("PASSED", 0) + counts.get("FAILED", 0)
    lat = sorted(o.latency_ms for o in outcomes if o.latency_ms is not None)

    def pct(p):
        if not lat:
            return None
        idx = min(len(lat) - 1, max(0, int(round(p * (len(lat) - 1)))))
        return round(lat[idx], 2)

    tags: dict[str, dict[str, int]] = {}
    for o in outcomes:
        for t in o.tags:
            tags.setdefault(t, {}).setdefault(o.status, 0)
            tags[t][o.status] += 1
    out_tokens = [o.usage.get("output_tokens", 0) for o in outcomes if o.usage]
    return {
        "cases": len(outcomes),
        "counts": counts,
        "pass_rate_over_decided": (counts.get("PASSED", 0) / decided) if decided else None,
        "latency_ms": {"p50": pct(0.5), "p95": pct(0.95), "max": lat[-1] if lat else None},
        "output_tokens_total": sum(out_tokens),
        "output_tokens_estimated": any(o.usage_estimated for o in outcomes),
        "by_tag": tags,
    }
