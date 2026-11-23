#!/usr/bin/env bash
# Oracle self-check for the backend-api fixture.
#
#   1. Copy examples/backend-api to a temp dir and add reference_tests/ as tests/qa/.
#   2. The project's existing suite must pass on the defective code.
#   3. The reference tests must fail for exactly the tests listed under
#      defects[].reference_tests in ground_truth.json (as assertion failures),
#      and every other reference test must pass.
#   4. For each defect, on a fresh copy with only its fix patch applied: the
#      existing suite still passes, that defect's reference tests now pass, and
#      the other defects' reference tests still fail.
#   5. With all patches applied, every test passes.
#
# Exits non-zero on any oracle violation.
# Env: PYTHON (default python3), KEEP_WORK=1 to keep the temp dir, TMPDIR.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
FIXTURE_DIR="$REPO_ROOT/examples/backend-api"
GT_JSON="$SCRIPT_DIR/ground_truth.json"
REF_DIR="$SCRIPT_DIR/reference_tests"
PYTHON="${PYTHON:-python3}"

for required in "$FIXTURE_DIR/ledger" "$GT_JSON" "$REF_DIR"; do
    if [[ ! -e "$required" ]]; then
        echo "oracle: missing $required" >&2
        exit 2
    fi
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/backend-api-oracle.XXXXXX")"
cleanup() {
    if [[ "${KEEP_WORK:-0}" == "1" ]]; then
        echo "work dir kept: $WORK"
    else
        rm -rf "$WORK"
    fi
}
trap cleanup EXIT

HELPER="$WORK/oracle_helper.py"
cat > "$HELPER" <<'PY'
import json
import sys
import xml.etree.ElementTree as ET


def load_gt(path):
    with open(path) as fh:
        return json.load(fh)


def cmd_defects(gt_path):
    for defect in load_gt(gt_path)["defects"]:
        print(f"{defect['id']}\t{defect['fix_patch']}")


def outcomes(junit_path):
    """Map reference-test node ids (reference_tests/<file>::<name>) to outcome."""
    result = {}
    for case in ET.parse(junit_path).getroot().iter("testcase"):
        parts = case.get("classname", "").split(".")
        # classname is tests.qa.<module>[.<Class>...] when run from the copy root
        if parts[:2] != ["tests", "qa"] or len(parts) < 3:
            continue
        node = f"reference_tests/{parts[2]}.py::" + "::".join(parts[3:] + [case.get("name")])
        if case.find("failure") is not None:
            outcome = "failed"
        elif case.find("error") is not None:
            outcome = "error"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        result[node] = outcome
    return result


def cmd_check(junit_path, gt_path, fixed_csv, label):
    gt = load_gt(gt_path)
    fixed = {d for d in fixed_csv.split(",") if d}
    results = outcomes(junit_path)
    owner = {}
    for defect in gt["defects"]:
        for test in defect["reference_tests"]:
            owner[test] = defect["id"]
    problems = []

    for test, defect_id in owner.items():
        got = results.get(test)
        want = "passed" if defect_id in fixed else "failed"
        if got is None:
            problems.append(f"{test} [{defect_id}] was not collected")
        elif got != want:
            problems.append(f"{test} [{defect_id}] expected {want}, got {got}")

    for test, got in sorted(results.items()):
        if test not in owner and got != "passed":
            problems.append(f"{test} [no defect] expected passed, got {got}")

    n_fail = sum(1 for o in results.values() if o in ("failed", "error"))
    n_pass = sum(1 for o in results.values() if o == "passed")
    print(f"    reference tests: {n_pass} passed, {n_fail} failed ({len(results)} total)")
    for defect in gt["defects"]:
        states = [results.get(t, "missing") for t in defect["reference_tests"]]
        want = "passed" if defect["id"] in fixed else "failed"
        mark = "ok " if all(s == want for s in states) else "BAD"
        print(f"    [{mark}] {defect['id']}: expected {want:<6} -> " + ", ".join(states))
    for problem in problems:
        print(f"    VIOLATION: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "defects":
        cmd_defects(*args)
    elif command == "check":
        sys.exit(cmd_check(*args))
    else:
        sys.exit(f"unknown command {command}")
PY

VIOLATIONS=0
SUMMARY=()

record() {  # record <ok|FAIL> <message>
    if [[ "$1" == "ok" ]]; then
        SUMMARY+=("  PASS  $2")
    else
        SUMMARY+=("  FAIL  $2")
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
}

fresh_copy() {  # fresh_copy <name> -> prints path
    local dest="$WORK/$1"
    cp -R "$FIXTURE_DIR" "$dest"
    find "$dest" -name "__pycache__" -type d -prune -exec rm -rf {} +
    rm -rf "$dest/.pytest_cache" "$dest/tests/qa"
    find "$dest" -maxdepth 1 -name "*.db*" -type f -delete
    mkdir -p "$dest/tests/qa"
    cp "$REF_DIR"/*.py "$dest/tests/qa/"
    printf '%s\n' "$dest"
}

run_existing() {  # run_existing <dir> <label>
    local dir="$1" label="$2" log="$1/existing.log" rc
    (cd "$dir" && "$PYTHON" -m pytest -q -p no:cacheprovider tests --ignore=tests/qa) >"$log" 2>&1
    rc=$?
    echo "    existing suite: $(tail -n 1 "$log")"
    if [[ $rc -eq 0 ]]; then
        record ok "$label: existing suite passes"
    else
        sed 's/^/      | /' "$log" | tail -n 40
        record FAIL "$label: existing suite failed (pytest exit $rc)"
    fi
}

run_reference() {  # run_reference <dir> <label> <fixed-defect-ids-csv>
    local dir="$1" label="$2" fixed="$3" log="$1/qa.log" xml="$1/qa.xml" rc
    (cd "$dir" && "$PYTHON" -m pytest -q -p no:cacheprovider tests/qa --junitxml="$xml") >"$log" 2>&1
    rc=$?
    if [[ $rc -gt 1 || ! -s "$xml" ]]; then
        sed 's/^/      | /' "$log" | tail -n 40
        record FAIL "$label: reference tests did not run cleanly (pytest exit $rc)"
        return
    fi
    if "$PYTHON" "$HELPER" check "$xml" "$GT_JSON" "$fixed" "$label"; then
        record ok "$label: reference tests fail for exactly the unfixed defects"
    else
        grep -E "^(FAILED|ERROR) " "$log" | sed 's/^/      | /'
        record FAIL "$label: reference test outcomes do not match the oracle"
    fi
}

apply_patch() {  # apply_patch <dir> <patch> <label>
    local dir="$1" patch_file="$2" label="$3"
    if (cd "$dir" && patch -p1 --batch --forward --fuzz=0 --dry-run -i "$patch_file" >/dev/null 2>&1 \
        && patch -p1 --batch --forward --fuzz=0 -i "$patch_file" >/dev/null); then
        record ok "$label: $(basename "$patch_file") applies cleanly"
        return 0
    fi
    record FAIL "$label: $(basename "$patch_file") does not apply cleanly"
    return 1
}

DEFECT_LINES=()
while IFS= read -r line; do
    [[ -n "$line" ]] && DEFECT_LINES+=("$line")
done < <("$PYTHON" "$HELPER" defects "$GT_JSON")
if [[ ${#DEFECT_LINES[@]} -eq 0 ]]; then
    echo "oracle: no defects found in $GT_JSON" >&2
    exit 2
fi

echo "backend-api oracle check"
echo "  fixture:      $FIXTURE_DIR"
echo "  ground truth: $GT_JSON"
echo "  work dir:     $WORK"
echo

echo "== defective app (no fixes) =="
dir="$(fresh_copy baseline)"
run_existing "$dir" "defective"
run_reference "$dir" "defective" ""
echo

ALL_IDS=()
ALL_PATCHES=()
for line in "${DEFECT_LINES[@]}"; do
    IFS=$'\t' read -r defect_id patch_rel <<<"$line"
    patch_file="$SCRIPT_DIR/$patch_rel"
    ALL_IDS+=("$defect_id")
    ALL_PATCHES+=("$patch_file")
    echo "== $defect_id fixed ($patch_rel) =="
    if [[ ! -f "$patch_file" ]]; then
        record FAIL "$defect_id: patch file $patch_rel missing"
        echo
        continue
    fi
    dir="$(fresh_copy "fix-$defect_id")"
    if apply_patch "$dir" "$patch_file" "$defect_id"; then
        run_existing "$dir" "$defect_id fixed"
        run_reference "$dir" "$defect_id fixed" "$defect_id"
    fi
    echo
done

echo "== all fixes applied =="
dir="$(fresh_copy fix-all)"
all_applied=1
for i in "${!ALL_PATCHES[@]}"; do
    apply_patch "$dir" "${ALL_PATCHES[$i]}" "all-fixes/${ALL_IDS[$i]}" || all_applied=0
done
if [[ $all_applied -eq 1 ]]; then
    fixed_csv="$(IFS=,; echo "${ALL_IDS[*]}")"
    run_existing "$dir" "all fixed"
    run_reference "$dir" "all fixed" "$fixed_csv"
fi
echo

echo "== summary =="
printf '%s\n' "${SUMMARY[@]}"
echo
if [[ $VIOLATIONS -eq 0 ]]; then
    echo "ORACLE OK: ${#SUMMARY[@]} checks passed"
    exit 0
fi
echo "ORACLE VIOLATED: $VIOLATIONS of ${#SUMMARY[@]} checks failed"
exit 1
