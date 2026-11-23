#!/usr/bin/env bash
# verify_oracle.sh - self-check for the ai-support-bot answer key.
#
# Every check runs on a fresh temporary copy of examples/ai-support-bot with
# reference_tests/ copied in; the fixture itself is never modified.
#
#   1. Shipped (defective) app:
#        - the project's existing unit tests pass;
#        - in reference_tests/, exactly the tests listed as defect
#          reference_tests in ground_truth.json fail, all others pass;
#        - every case in the project's evals/golden.jsonl passes;
#        - in reference_evals.jsonl, exactly the defect reference_eval_cases
#          fail, all others pass.
#   2. Each fix patch, on its own fresh copy:
#        - applies cleanly with `patch -p1`;
#        - existing unit tests and golden evals still pass;
#        - its own reference tests / eval cases now pass, while the other
#          defects' tests / cases still fail (patches are independent).
#   3. All patches applied together: every reference test and eval case passes.
#
# Exits non-zero on any violation. Requires python3 (3.11+) with pytest, patch, tar.
# Usage: bash verify_oracle.sh        (PYTHON=/path/to/python3 to override)

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_REL="../../../examples/ai-support-bot"
if ! FIXTURE="$(cd "$HERE/$FIXTURE_REL" 2>/dev/null && pwd)"; then
  echo "verify_oracle: fixture not found at $HERE/$FIXTURE_REL" >&2
  exit 2
fi
GROUND_TRUTH="$HERE/ground_truth.json"
REFERENCE_EVALS="$HERE/reference_evals.jsonl"
GOLDEN="$FIXTURE/evals/golden.jsonl"
PY="${PYTHON:-python3}"
export PYTHONDONTWRITEBYTECODE=1

for tool in "$PY" patch tar; do
  command -v "$tool" >/dev/null 2>&1 || { echo "verify_oracle: missing required tool: $tool" >&2; exit 2; }
done
"$PY" -c 'import pytest' 2>/dev/null || { echo "verify_oracle: pytest is not importable by $PY" >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ai-support-bot-oracle.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
HELPER="$WORK/oracle_helper.py"

cat >"$HELPER" <<'PYEOF'
"""Helpers for verify_oracle.sh: ground-truth queries, JUnit parsing, eval runner."""
import json
import re
import sys
import time
import xml.etree.ElementTree as ET

ALLOWED_TOP = {"id", "input", "tags", "expect", "judge"}
ALLOWED_EXPECT = {
    "contains", "not_contains", "regex", "citations_include", "retrieved_include",
    "tool_calls", "tool_calls_mode", "forbidden_tools", "refusal",
    "max_output_tokens", "max_latency_ms",
}
TOOL_MODES = {"ordered-subset", "exact", "subset"}
# Heuristic refusal detector used for `refusal` expectations.
REFUSAL_RE = re.compile(
    r"\b(i'm sorry|i am sorry|i can't|i cannot|i'm unable|i am unable|i don't know|i do not know)\b",
    re.IGNORECASE,
)


def gt(args):
    data = json.load(open(args[0], encoding="utf-8"))
    what = args[1]
    defects = {d["id"]: d for d in data["defects"]}
    if what == "defects":
        print("\n".join(defects))
    elif what in ("tests", "cases"):  # all defects
        key = "reference_tests" if what == "tests" else "reference_eval_cases"
        print("\n".join(x for d in defects.values() for x in d[key]))
    elif what in ("tests-of", "cases-of"):  # only the given defect ids (possibly none)
        key = "reference_tests" if what == "tests-of" else "reference_eval_cases"
        print("\n".join(x for i in args[2:] for x in defects[i][key]))
    elif what == "patch":
        print(defects[args[2]]["fix_patch"])
    elif what == "others":  # defect ids other than args[2]
        print("\n".join(i for i in defects if i != args[2]))
    else:
        raise SystemExit(f"unknown gt query {what}")


def check_junit(args):
    """check-junit XML [EXPECTED_FAIL_NODEID ...]: those must fail, all others pass."""
    xml_path, expected_fail = args[0], set(args[1:])
    root = ET.parse(xml_path).getroot()
    results = {}
    for case in root.iter("testcase"):
        nodeid = case.get("classname", "").replace(".", "/") + ".py::" + case.get("name", "")
        status = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                status = "failed"
            elif child.tag == "skipped":
                status = "skipped"
        results[nodeid] = status
    problems = []
    if not results:
        problems.append("no tests were collected")
    for nodeid in sorted(expected_fail - set(results)):
        problems.append(f"expected test not found: {nodeid}")
    for nodeid, status in sorted(results.items()):
        want = "failed" if nodeid in expected_fail else "passed"
        mark = "ok  " if status == want else "BAD "
        print(f"      {mark}{nodeid}: {status} (expected {want})")
        if status != want:
            problems.append(f"{nodeid}: {status}, expected {want}")
    for p in problems:
        print(f"      VIOLATION: {p}")
    return 1 if problems else 0


def _tool_call_matches(expected, actual):
    if expected.get("name") != actual.get("name"):
        return False
    actual_args = actual.get("args", {})
    for key, value in expected.get("args", {}).items():
        if key not in actual_args or actual_args[key] != value or type(actual_args[key]) is not type(value):
            return False
    return True


def _tool_calls_ok(expected, actual, mode):
    if mode == "exact":
        return len(expected) == len(actual) and all(_tool_call_matches(e, a) for e, a in zip(expected, actual))
    if mode == "subset":
        return all(any(_tool_call_matches(e, a) for a in actual) for e in expected)
    pos = 0  # ordered-subset
    for e in expected:
        while pos < len(actual) and not _tool_call_matches(e, actual[pos]):
            pos += 1
        if pos == len(actual):
            return False
        pos += 1
    return True


def validate_case(case, where):
    errors = []
    extra = set(case) - ALLOWED_TOP
    if extra:
        errors.append(f"{where}: unknown top-level keys {sorted(extra)}")
    for key in ("id", "input", "expect"):
        if key not in case:
            errors.append(f"{where}: missing {key}")
    expect = case.get("expect", {})
    bad = set(expect) - ALLOWED_EXPECT
    if bad:
        errors.append(f"{where}: unknown expect keys {sorted(bad)}")
    if "tool_calls_mode" in expect and expect["tool_calls_mode"] not in TOOL_MODES:
        errors.append(f"{where}: bad tool_calls_mode {expect['tool_calls_mode']!r}")
    if "judge" in case and not isinstance(case["judge"], dict):
        errors.append(f"{where}: judge must be an object")
    return errors


def evaluate(case, answer):
    expect = case["expect"]
    start = time.perf_counter()
    resp = answer(case["input"])
    latency_ms = (time.perf_counter() - start) * 1000
    text = resp["answer"]
    low = text.lower()
    names = [c["name"] for c in resp["tool_calls"]]
    fails = []
    for s in expect.get("contains", []):
        if s.lower() not in low:
            fails.append(f"missing {s!r}")
    for s in expect.get("not_contains", []):
        if s.lower() in low:
            fails.append(f"contains forbidden {s!r}")
    if "regex" in expect and not re.search(expect["regex"], text):
        fails.append(f"regex {expect['regex']!r} not matched")
    for d in expect.get("citations_include", []):
        if d not in resp["citations"]:
            fails.append(f"citation {d} missing (got {resp['citations']})")
    for d in expect.get("retrieved_include", []):
        if d not in resp["retrieved"]:
            fails.append(f"retrieved {d} missing (got {resp['retrieved']})")
    if "tool_calls" in expect:
        mode = expect.get("tool_calls_mode", "ordered-subset")
        if not _tool_calls_ok(expect["tool_calls"], resp["tool_calls"], mode):
            fails.append(f"tool_calls ({mode}) mismatch: got {resp['tool_calls']}")
    for name in expect.get("forbidden_tools", []):
        if name in names:
            fails.append(f"forbidden tool called: {name}")
    if "refusal" in expect and bool(REFUSAL_RE.search(text)) != expect["refusal"]:
        fails.append(f"refusal expected={expect['refusal']}")
    if "max_output_tokens" in expect and resp["usage"]["output_tokens"] > expect["max_output_tokens"]:
        fails.append(f"output_tokens {resp['usage']['output_tokens']} > {expect['max_output_tokens']}")
    if "max_latency_ms" in expect and latency_ms > expect["max_latency_ms"]:
        fails.append(f"latency {latency_ms:.1f}ms > {expect['max_latency_ms']}ms")
    return fails


def run_evals(args):
    """evals FIXTURE_DIR JSONL [EXPECTED_FAIL_CASE ...]: those must fail, all others pass."""
    fixture, jsonl, expected_fail = args[0], args[1], set(args[2:])
    sys.path.insert(0, fixture)
    from support_bot.bot import answer

    problems = []
    cases = []
    with open(jsonl, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"line {lineno}: invalid JSON ({exc})")
                continue
            problems.extend(validate_case(case, f"line {lineno}"))
            cases.append(case)
    ids = [c.get("id") for c in cases]
    for missing in sorted(expected_fail - set(ids)):
        problems.append(f"expected case not found: {missing}")
    for case in cases:
        if "expect" not in case or "input" not in case:
            continue
        fails = evaluate(case, answer)
        got = "failed" if fails else "passed"
        want = "failed" if case["id"] in expected_fail else "passed"
        judge = " [judge: NOT_RUN]" if "judge" in case else ""
        mark = "ok  " if got == want else "BAD "
        detail = f" -- {'; '.join(fails)}" if fails else ""
        print(f"      {mark}{case['id']}: {got} (expected {want}){judge}{detail}")
        if got != want:
            problems.append(f"{case['id']}: {got}, expected {want}")
    for p in problems:
        print(f"      VIOLATION: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "gt":
        gt(rest)
        sys.exit(0)
    sys.exit({"check-junit": check_junit, "evals": run_evals}[cmd](rest))
PYEOF

VIOLATIONS=0
violation() { echo "  VIOLATION: $*"; VIOLATIONS=$((VIOLATIONS + 1)); }
ok() { echo "  ok: $*"; }

helper() { "$PY" -B "$HELPER" "$@"; }
lines_to_array() { # $1 = array name; stdin = lines
  local _name="$1" _line
  eval "$_name=()"
  while IFS= read -r _line; do
    [ -n "$_line" ] && eval "$_name+=(\"\$_line\")"
  done
}

fresh_copy() { # $1 = name -> prints path
  local dest="$WORK/$1"
  mkdir -p "$dest"
  (cd "$FIXTURE" && tar --exclude=__pycache__ --exclude=.pytest_cache -cf - .) | (cd "$dest" && tar -xf -)
  (cd "$HERE" && tar --exclude=__pycache__ --exclude=.pytest_cache -cf - reference_tests) | (cd "$dest" && tar -xf -)
  printf '%s\n' "$dest"
}

check_existing_tests() { # $1 = copy dir, $2 = label
  local log="$WORK/$2.existing.log"
  if (cd "$1" && "$PY" -m pytest -q -p no:cacheprovider >"$log" 2>&1); then
    ok "existing unit tests pass ($(tail -n 1 "$log"))"
  else
    violation "existing unit tests do not all pass [$2]"
    sed 's/^/      /' "$log" | tail -n 25
  fi
}

check_reference_tests() { # $1 = copy dir, $2 = label, rest = nodeids expected to fail
  local dir="$1" label="$2"; shift 2
  local xml="$WORK/$label.ref.xml" log="$WORK/$label.ref.log" rc
  (cd "$dir" && "$PY" -m pytest -q -p no:cacheprovider --junitxml="$xml" reference_tests >"$log" 2>&1)
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
    violation "reference tests did not run cleanly [$label] (pytest exit $rc)"
    sed 's/^/      /' "$log" | tail -n 25
    return
  fi
  if helper check-junit "$xml" "$@"; then
    ok "reference tests: exactly the expected $# test(s) fail ($(tail -n 1 "$log"))"
  else
    violation "reference test outcomes differ from the answer key [$label]"
  fi
}

check_evals() { # $1 = copy dir, $2 = jsonl, $3 = description, rest = case ids expected to fail
  local dir="$1" jsonl="$2" desc="$3"; shift 3
  if (cd "$dir" && helper evals "$dir" "$jsonl" "$@"); then
    ok "$desc: exactly the expected $# case(s) fail"
  else
    violation "$desc: outcomes differ from the answer key"
  fi
}

apply_patch() { # $1 = copy dir, $2 = patch file
  local dir="$1" patch_file="$2"
  if [ ! -f "$patch_file" ]; then
    violation "patch file missing: $patch_file"
    return 1
  fi
  if ! (cd "$dir" && patch -p1 --dry-run -s <"$patch_file" >/dev/null 2>&1); then
    violation "patch does not apply cleanly: $patch_file"
    return 1
  fi
  (cd "$dir" && patch -p1 -s <"$patch_file") || { violation "patch failed: $patch_file"; return 1; }
  if [ -n "$(find "$dir" -name '*.rej' -o -name '*.orig')" ]; then
    violation "patch left .rej/.orig files: $patch_file"
    return 1
  fi
  ok "applied $(basename "$patch_file")"
}

lines_to_array DEFECTS < <(helper gt "$GROUND_TRUTH" defects)
lines_to_array ALL_TESTS < <(helper gt "$GROUND_TRUTH" tests)
lines_to_array ALL_CASES < <(helper gt "$GROUND_TRUTH" cases)
[ "${#DEFECTS[@]}" -gt 0 ] || { echo "verify_oracle: no defects in ground_truth.json" >&2; exit 2; }

echo "== 1. shipped app (defects present)"
BASE="$(fresh_copy base)"
check_existing_tests "$BASE" base
check_reference_tests "$BASE" base ${ALL_TESTS[@]+"${ALL_TESTS[@]}"}
check_evals "$BASE" "$GOLDEN" "golden evals (evals/golden.jsonl)"
check_evals "$BASE" "$REFERENCE_EVALS" "reference evals" ${ALL_CASES[@]+"${ALL_CASES[@]}"}

for defect in "${DEFECTS[@]}"; do
  echo "== 2. fix patch for $defect"
  COPY="$(fresh_copy "fix-$defect")"
  PATCH_FILE="$HERE/$(helper gt "$GROUND_TRUTH" patch "$defect")"
  apply_patch "$COPY" "$PATCH_FILE" || continue
  lines_to_array OTHERS < <(helper gt "$GROUND_TRUTH" others "$defect")
  lines_to_array STILL_FAILING_TESTS < <(helper gt "$GROUND_TRUTH" tests-of ${OTHERS[@]+"${OTHERS[@]}"})
  lines_to_array STILL_FAILING_CASES < <(helper gt "$GROUND_TRUTH" cases-of ${OTHERS[@]+"${OTHERS[@]}"})
  check_existing_tests "$COPY" "fix-$defect"
  check_reference_tests "$COPY" "fix-$defect" ${STILL_FAILING_TESTS[@]+"${STILL_FAILING_TESTS[@]}"}
  check_evals "$COPY" "$GOLDEN" "golden evals"
  check_evals "$COPY" "$REFERENCE_EVALS" "reference evals" ${STILL_FAILING_CASES[@]+"${STILL_FAILING_CASES[@]}"}
done

echo "== 3. all fix patches together"
ALL="$(fresh_copy all-fixes)"
all_applied=1
for defect in "${DEFECTS[@]}"; do
  apply_patch "$ALL" "$HERE/$(helper gt "$GROUND_TRUTH" patch "$defect")" || all_applied=0
done
if [ "$all_applied" -eq 1 ]; then
  check_existing_tests "$ALL" all-fixes
  check_reference_tests "$ALL" all-fixes
  check_evals "$ALL" "$GOLDEN" "golden evals"
  check_evals "$ALL" "$REFERENCE_EVALS" "reference evals"
fi

echo
if [ "$VIOLATIONS" -eq 0 ]; then
  echo "verify_oracle: PASS (ai-support-bot answer key is consistent)"
  exit 0
fi
echo "verify_oracle: FAIL ($VIOLATIONS violation(s))"
exit 1
