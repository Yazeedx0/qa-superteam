#!/usr/bin/env bash
# Oracle check for the web-checkout fixture.
#
#   1. Pristine copy: the project's own suite passes, and exactly the reference
#      tests listed for the planted defects fail (everything else passes).
#   2. For each defect's fix patch, on a fresh copy: the patch applies, the
#      project's suite still passes, that defect's reference tests now pass and
#      only the other defects' reference tests still fail.
#   3. All patches together: every test passes.
#
# Exit status: 0 = oracle holds, 1 = oracle violation, 2 = setup problem.
# Env: PYTHON (default python3), KEEP_WORK=1 keeps the temp dir for debugging.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
FIXTURE_SRC="$REPO_ROOT/examples/web-checkout"
GROUND_TRUTH="$HERE/ground_truth.json"
PYTHON="${PYTHON:-python3}"

die() { printf 'SETUP ERROR: %s\n' "$*" >&2; exit 2; }

[[ -f "$FIXTURE_SRC/serve.py" ]] || die "fixture not found at $FIXTURE_SRC"
[[ -f "$GROUND_TRUTH" ]] || die "missing $GROUND_TRUTH"
[[ -f "$FIXTURE_SRC/node_modules/axe-core/axe.min.js" ]] ||
  die "axe-core missing: run 'npm install' in $FIXTURE_SRC"
command -v patch >/dev/null || die "'patch' is required"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/web-checkout-oracle.XXXXXX")"
if [[ "${KEEP_WORK:-0}" == "1" ]]; then
  echo "work dir kept at $WORK"
else
  trap 'rm -rf "$WORK"' EXIT
fi
unset QAST_ARTIFACT_DIR

violations=0

# ---------------------------------------------------------------- ground truth

# Validate ground_truth.json and print "<id> <patch path>" per defect.
DEFECTS="$("$PYTHON" - "$GROUND_TRUTH" "$HERE" <<'PY'
import json, os, sys
gt_path, here = sys.argv[1], sys.argv[2]
gt = json.load(open(gt_path, encoding="utf-8"))
allowed = {"functional", "security", "data-integrity", "performance", "reliability",
           "accessibility", "contract", "ai-quality", "usability", "other"}
problems = []
for key in ("fixture", "description", "defects", "decoys", "ambiguities"):
    if key not in gt:
        problems.append(f"missing top-level key {key!r}")
for d in gt.get("defects", []):
    if d.get("category") not in allowed:
        problems.append(f"{d.get('id')}: category {d.get('category')!r} not allowed")
    for test in d.get("reference_tests", []):
        if not os.path.isfile(os.path.join(here, test.split("::")[0])):
            problems.append(f"{d['id']}: reference test file missing for {test}")
    if not os.path.isfile(os.path.join(here, d.get("fix_patch", ""))):
        problems.append(f"{d['id']}: fix patch missing: {d.get('fix_patch')}")
    if not d.get("reference_tests"):
        problems.append(f"{d['id']}: no reference tests")
if problems:
    sys.exit("ground_truth.json problems:\n  " + "\n  ".join(problems))
for d in gt["defects"]:
    print(d["id"], os.path.join(here, d["fix_patch"]))
PY
)" || die "invalid ground truth"

ALL_IDS="$(awk '{print $1}' <<<"$DEFECTS" | tr '\n' ' ')"

# Comma-separated "<file>::<test>" keys of the reference tests for the given defect ids.
expected_failures() {
  "$PYTHON" - "$GROUND_TRUTH" "$@" <<'PY'
import json, os, sys
gt = json.load(open(sys.argv[1], encoding="utf-8"))
present = set(sys.argv[2:])
keys = []
for d in gt["defects"]:
    if d["id"] in present:
        for test in d["reference_tests"]:
            path, _, name = test.partition("::")
            keys.append(os.path.basename(path) + "::" + name)
print(",".join(sorted(keys)))
PY
}

# ------------------------------------------------------------------- helpers

make_copy() {
  local dest="$1"
  mkdir -p "$dest"
  (cd "$FIXTURE_SRC" &&
    tar --exclude=./node_modules --exclude='__pycache__' --exclude=./.pytest_cache \
        --exclude=./test-artifacts -cf - .) | (cd "$dest" && tar -xf -)
  ln -s "$FIXTURE_SRC/node_modules" "$dest/node_modules"
  mkdir -p "$dest/tests/qa"
  cp "$HERE"/reference_tests/*.py "$dest/tests/qa/"
}

# check_run <label> <copy dir> <expected failures csv> <pytest args...>
check_run() {
  local label="$1" dir="$2" expected="$3"
  shift 3
  local junit="$dir/.oracle-$(tr -c 'A-Za-z0-9' '-' <<<"$label").xml"
  local log="${junit%.xml}.log"
  local status=0
  (cd "$dir" && "$PYTHON" -m pytest -q -p no:cacheprovider --junitxml="$junit" "$@" </dev/null) >"$log" 2>&1 || status=$?

  if ! "$PYTHON" - "$label" "$junit" "$expected" "$status" <<'PY'; then
import os, sys
import xml.etree.ElementTree as ET
label, junit, expected_csv, status = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
expected = {k for k in expected_csv.split(",") if k}
if not os.path.isfile(junit):
    print(f"  [{label}] no junit report (pytest exit {status})")
    sys.exit(1)
results = {}
for case in ET.parse(junit).getroot().iter("testcase"):
    key = case.get("classname", "").split(".")[-1] + ".py::" + case.get("name", "")
    if case.find("failure") is not None or case.find("error") is not None:
        results[key] = "failed"
    elif case.find("skipped") is not None:
        results[key] = "skipped"
    else:
        results[key] = "passed"
failed = {k for k, v in results.items() if v == "failed"}
problems = []
if not results:
    problems.append("no tests were collected")
for key in sorted(expected - results.keys()):
    problems.append(f"expected-failing test was not collected: {key}")
for key in sorted(failed - expected):
    problems.append(f"unexpected FAILURE: {key}")
for key in sorted(k for k in expected if results.get(k) == "passed"):
    problems.append(f"expected FAILURE but it passed: {key}")
for key in sorted(k for k, v in results.items() if v == "skipped"):
    problems.append(f"test was skipped: {key}")
if not expected and status != 0:
    problems.append(f"pytest exited with status {status}")
passed = sum(v == "passed" for v in results.values())
summary = f"{passed} passed, {len(failed)} failed (expected {len(expected)} failing)"
if problems:
    print(f"  [{label}] VIOLATION: {summary}")
    for p in problems:
        print(f"      - {p}")
    sys.exit(1)
print(f"  [{label}] ok: {summary}")
for key in sorted(failed):
    print(f"      fails as expected: {key}")
PY
    violations=$((violations + 1))
    echo "      --- pytest output (tail) ---"
    tail -n 40 "$log" | sed 's/^/      | /'
  fi
}

run_both() {
  local label="$1" dir="$2" expected="$3"
  check_run "$label: project suite" "$dir" "" tests --ignore=tests/qa
  check_run "$label: reference tests" "$dir" "$expected" tests/qa
}

# ---------------------------------------------------------------------- runs

echo "== pristine fixture"
make_copy "$WORK/pristine"
# shellcheck disable=SC2086
run_both "pristine" "$WORK/pristine" "$(expected_failures $ALL_IDS)"

while read -r defect_id patch_file; do
  echo "== $defect_id fixed ($(basename "$patch_file"))"
  dir="$WORK/fix-$defect_id"
  make_copy "$dir"
  if ! (cd "$dir" && patch -p1 --forward --batch --silent <"$patch_file"); then
    echo "  [$defect_id] VIOLATION: patch does not apply cleanly: $patch_file"
    violations=$((violations + 1))
    continue
  fi
  remaining=()
  for other in $ALL_IDS; do
    [[ "$other" == "$defect_id" ]] || remaining+=("$other")
  done
  run_both "$defect_id fixed" "$dir" "$(expected_failures "${remaining[@]}")"
done <<<"$DEFECTS"

echo "== all fixes applied"
dir="$WORK/fix-all"
make_copy "$dir"
all_applied=1
while read -r defect_id patch_file; do
  if ! (cd "$dir" && patch -p1 --forward --batch --silent <"$patch_file"); then
    echo "  [all fixes] VIOLATION: $defect_id patch does not apply on top of the others"
    violations=$((violations + 1))
    all_applied=0
  fi
done <<<"$DEFECTS"
if [[ "$all_applied" == "1" ]]; then
  run_both "all fixed" "$dir" ""
fi

echo
if [[ "$violations" -gt 0 ]]; then
  echo "ORACLE FAILED: $violations violation(s)"
  exit 1
fi
echo "ORACLE OK"
