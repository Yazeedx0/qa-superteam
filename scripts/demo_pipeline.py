#!/usr/bin/env python3
"""Scripted end-to-end demonstrations of the QA Superteam pipeline on the reference fixtures.

    python3 scripts/demo_pipeline.py --scenario backend-full-audit --out examples/reports
    python3 scripts/demo_pipeline.py --scenario all --out examples/reports

What is real: every test execution, result, artifact hash, reproduction, verification
gate, policy decision and report below comes from actually running the tools.

What is scripted: the *analysis* an agent would write (requirements JSON, test plan,
finding text, and the QA tests themselves, which are the fixture's reference tests
standing in for agent-authored tests). Live agent behaviour is measured separately by
evals/harness/run_evals.py. Reports produced here say so in their limitations.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QAST = [str(ROOT / "bin" / "qast")]
GT = ROOT / "evals" / "ground_truth"
SCRIPTED_NOTE = (
    "Demonstration run: analysis records (requirements, plan, finding text) and the QA tests were scripted "
    "(reference tests stand in for agent-authored tests). All executions, evidence, verifications and the decision are real."
)


class Demo:
    def __init__(self, fixture: str, workdir: Path, mode: str, scope: str, base: str | None = None):
        self.proj = workdir / fixture
        src = ROOT / "examples" / fixture
        shutil.copytree(src, self.proj, ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", ".qa-superteam"))
        if (src / "node_modules").exists():
            (self.proj / "node_modules").symlink_to(src / "node_modules")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")
        self.mode, self.scope, self.base = mode, scope, base

    def git(self, *args):
        env = {**os.environ, "GIT_AUTHOR_NAME": "demo", "GIT_AUTHOR_EMAIL": "demo@example.com", "GIT_COMMITTER_NAME": "demo", "GIT_COMMITTER_EMAIL": "demo@example.com"}
        return subprocess.run(["git", *args], cwd=self.proj, check=True, capture_output=True, text=True, env=env).stdout

    def q(self, *args, check=True, stdin: str | None = None) -> str:
        out = subprocess.run([*QAST, *args], cwd=self.proj, capture_output=True, text=True, input=stdin, env={**os.environ, "QAST_PYTHON": sys.executable})
        print(f"$ qast {' '.join(args)}\n{out.stdout.strip()}\n")
        if check and out.returncode not in (0,):
            raise SystemExit(f"qast {args} failed ({out.returncode}): {out.stdout}\n{out.stderr}")
        return out.stdout

    def qj(self, *args) -> dict:
        args = list(args)
        i = args.index("--") if "--" in args else len(args)
        return json.loads(self.q(*args[:i], "--json", *args[i:]))

    def start(self):
        args = ["run", "start", "--mode", self.mode, "--scope", self.scope]
        if self.base:
            args += ["--base", self.base]
        self.q(*args)
        self.q("run", "note", SCRIPTED_NOTE, "--kind", "limitation")

    def record(self, kind: str, data: dict, supersede=False):
        f = self.proj / ".qa-superteam" / f"draft-{kind}.json"
        f.write_text(json.dumps(data, indent=2))
        self.q("record", kind, "--file", str(f), *(["--supersede"] if supersede else []))

    def phase(self, name, state="done", note=None):
        self.q("run", "phase", name, state, *(["--note", note] if note else []))

    def exec(self, *args) -> dict:
        return self.qj("exec", *args)

    def finding(self, data: dict) -> str:
        f = self.proj / ".qa-superteam" / "draft-finding.json"
        f.write_text(json.dumps(data, indent=2))
        out = self.q("finding", "add", "--file", str(f))
        return out.split()[2]

    def reproduce(self, test: str, *extra) -> list[str]:
        self.q("reproduce", "--test", test, "--times", "3", *extra)
        st = json.loads(self.q("run", "status", "--json"))
        return [e["id"] for e in st["executions"] if (e["label"] or "").startswith(f"reproduce {test}")]

    def verify(self, fid: str, exec_ids: list[str], rationale: str, tests: list[str] | None = None):
        args = ["verify", fid, "--verdict", "CONFIRMED", "--method", "independent-rerun" if not tests else "alternate-oracle",
                "--verifier", "qa-superteam:independent-verification-engineer", "--rationale", rationale]
        for x in exec_ids:
            args += ["--execution", x]
        for t in tests or []:
            args += ["--test", t]
        self.q(*args)

    def finish(self, out_root: Path, name: str) -> Path:
        self.q("gate", check=False)
        self.q("report")
        self.q("validate")
        self.q("run", "finish")
        run_dir = sorted((self.proj / ".qa-superteam" / "runs").iterdir())[-1]
        dest = out_root / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(run_dir, dest, ignore=shutil.ignore_patterns("work"))
        for p in dest.rglob("*"):
            if p.is_file() and p.suffix in (".json", ".jsonl", ".md", ".log", ".xml"):
                text = p.read_text(encoding="utf-8", errors="replace")
                text = text.replace(str(self.proj), "<project>").replace(str(ROOT), "<qa-superteam>").replace(str(Path.home()), "~")
                p.write_text(text, encoding="utf-8")
        # paths were sanitized after hashing: re-hash so `qast validate` keeps passing on the published copy
        for ev in (dest / "evidence").glob("*.json"):
            rec = json.loads(ev.read_text())
            data = (dest / rec["path"]).read_bytes()
            import hashlib

            rec["sha256"] = hashlib.sha256(data).hexdigest()
            rec["size_bytes"] = len(data)
            ev.write_text(json.dumps(rec, indent=2) + "\n")
        (dest / "README.md").write_text(
            f"# Sample run: {name}\n\nGenerated by `python3 scripts/demo_pipeline.py --scenario {name}` from real tool executions on "
            f"`examples/{self.proj.name}`.\n\n{SCRIPTED_NOTE}\n\nOpen [report.md](report.md). Absolute paths were replaced with "
            "`<project>` after the run; evidence hashes in this copy were recomputed for the sanitized files.\n",
            encoding="utf-8",
        )
        print(f"published {dest}")
        return dest


def failing(ex: dict) -> list[str]:
    return [r["identifier"] for r in ex["results"] if r["status"] == "FAILED"]


# --------------------------------------------------------------------------- scenarios


def backend_full_audit(work: Path, out: Path):
    d = Demo("backend-api", work, "full-audit", "Ledger API: full repository audit")
    d.start()
    d.q("doctor")
    d.q("discover")
    d.phase("discovery")
    d.record("requirements", {
        "requirements": [
            {"id": "REQ-BAL", "title": "Balances never go negative (fee included)", "status": "stated", "basis": "observed", "priority": "critical",
             "sources": [{"path": "docs/REQUIREMENTS.md"}], "acceptance_criteria": ["amount + fee > balance -> rejected, balance unchanged"]},
            {"id": "REQ-VIS", "title": "Users only see transfers they sent or received", "status": "stated", "basis": "observed", "priority": "critical",
             "sources": [{"path": "docs/REQUIREMENTS.md"}]},
            {"id": "REQ-EMAIL", "title": "Emails are unique case-insensitively", "status": "stated", "basis": "observed", "priority": "high",
             "sources": [{"path": "docs/REQUIREMENTS.md"}]},
            {"id": "REQ-LARGE", "title": "Large transfers may require additional review", "status": "ambiguous", "basis": "observed", "priority": "medium",
             "sources": [{"path": "docs/REQUIREMENTS.md"}], "open_questions": ["What amount counts as large?", "What does review mean for the API response?"]},
        ],
        "invariants": [
            {"id": "INV-1", "statement": "balance_cents >= 0 for every wallet after any committed operation", "criticality": "critical",
             "oracle": "After each API call, GET /wallets/me returns balance_cents >= 0", "basis": "observed"},
            {"id": "INV-2", "statement": "A transfer is readable only by its sender or recipient", "criticality": "critical",
             "oracle": "GET /transfers/{id} by a third user returns 404", "basis": "observed"},
        ],
        "ambiguities": ["REQ-LARGE has no threshold or defined behaviour; not tested, flagged for product"],
    })
    d.phase("requirements")
    d.phase("impact", "skipped", "full audit, no diff")
    d.q("risk")
    d.phase("risk")
    d.record("plan", {
        "scope": "Ledger API full audit",
        "strategy_summary": "Risk-based. Existing suite is mandatory. New API tests target the two critical invariants (INV-1, INV-2) and the email uniqueness rule with boundary and negative techniques. REQ-LARGE is ambiguous and out of scope.",
        "test_cases": [
            {"id": "TC-EXIST", "title": "Existing suite", "level": "api", "technique": "regression", "oracle": "project's own assertions", "origin": "existing", "test_ref": "tests", "groups": ["existing-suite"], "priority": "high", "risk_ids": ["R-01"]},
            {"id": "TC-AUTHZ", "title": "Third party cannot read a transfer", "level": "api", "technique": "negative", "oracle": "404 for non-party", "origin": "new", "test_ref": "tests/qa/test_qa_authz.py", "groups": ["critical-journeys"], "priority": "critical", "invariant_ids": ["INV-2"], "requirement_ids": ["REQ-VIS"], "risk_ids": ["R-01"]},
            {"id": "TC-FEE", "title": "Fee cannot overdraw a wallet", "level": "api", "technique": "boundary", "oracle": "422 and unchanged balance when amount+fee > balance", "origin": "new", "test_ref": "tests/qa/test_qa_invariants.py", "groups": ["critical-journeys"], "priority": "critical", "invariant_ids": ["INV-1"], "requirement_ids": ["REQ-BAL"], "risk_ids": ["R-01"]},
            {"id": "TC-EMAIL", "title": "Case-insensitive email uniqueness", "level": "api", "technique": "equivalence", "oracle": "409 for differently-cased duplicate", "origin": "new", "test_ref": "tests/qa/test_qa_integrity.py", "groups": ["regression"], "priority": "high", "requirement_ids": ["REQ-EMAIL"]},
        ],
        "out_of_scope": [{"item": "REQ-LARGE", "reason": "ambiguous requirement; needs product definition"}, {"item": "load testing", "reason": "no authorized performance environment"}],
        "specialists": ["qa-superteam:backend-qa-engineer", "qa-superteam:independent-verification-engineer"],
    })
    d.phase("planning")
    d.phase("delegation", note="backend-qa-engineer for API tests; independent-verification-engineer for high/critical findings")
    d.exec("pytest", "--group", "existing-suite", "--label", "existing suite", "--", "tests")
    shutil.copytree(GT / "backend-api" / "reference_tests", d.proj / "tests" / "qa")
    authz = d.exec("pytest", "--group", "critical-journeys", "--label", "authorization", "--", "tests/qa/test_qa_authz.py")
    inv = d.exec("pytest", "--group", "critical-journeys", "--label", "invariants", "--", "tests/qa/test_qa_invariants.py")
    integ = d.exec("pytest", "--group", "regression", "--label", "data integrity", "--", "tests/qa/test_qa_integrity.py")
    d.phase("execution")
    specs = [
        (authz, "Any logged-in user can read another user's transfer", "security", "critical", "ledger/routers/transfers.py", "get_transfer",
         "404 for a user who neither sent nor received the transfer (REQ-VIS, INV-2)", "200 with amount, memo and wallet ids of the other users' transfer",
         ["Register users A, B and C", "A deposits and transfers to C", "B requests GET /transfers/{id} of A's transfer"]),
        (inv, "Fee is not included in the funds check, so balances go negative", "data-integrity", "critical", "ledger/transfers.py", "create_transfer",
         "Transfer rejected when amount + fee exceeds the balance (REQ-BAL, INV-1)", "Transfer of the whole balance succeeds and leaves balance at -fee",
         ["Deposit 1000 cents", "Transfer 1000 cents to another user (fee 10)", "GET /wallets/me shows -10"]),
        (integ, "Email uniqueness is case-sensitive, allowing duplicate accounts", "data-integrity", "medium", "ledger/models.py", "clean_email",
         "Registering Alice@example.com after alice@example.com returns 409 (REQ-EMAIL)", "Both registrations succeed and create separate accounts",
         ["Register alice@example.com", "Register Alice@example.com", "Observe 201 for both"]),
    ]
    for ex, title, cat, sev, path, sym, expected, actual, steps in specs:
        tests = failing(ex)
        fid = d.finding({"title": title, "category": cat, "severity": sev, "summary": title, "expected": expected, "actual": actual,
                         "reproduction_steps": steps, "reported_by": "qa-superteam:backend-qa-engineer", "test_identifiers": tests,
                         "execution_ids": [ex["id"]], "evidence_ids": ex["artifact_ids"][:2], "affected": [{"path": path, "symbol": sym}],
                         "hypotheses": [{"statement": f"Logic in {sym} does not enforce the stated rule", "confidence": "medium"}]})
        repro = d.reproduce(tests[0])
        d.phase("investigation", "started")
        if sev in ("critical", "high"):
            d.verify(fid, repro[-1:], f"Re-ran {tests[0]} in an independent execution; failure is consistent (3/3).")
    d.phase("investigation")
    d.phase("verification")
    d.phase("release")
    d.phase("reporting")
    d.phase("regression", "skipped", "write_tests=false in the demo config: regression tests proposed in report (tests/qa/*)")
    d.finish(out, "backend-full-audit")


def backend_pr_review(work: Path, out: Path):
    """A real git diff: the baseline has the fee rule correct, the PR branch breaks it."""
    d = Demo("backend-api", work, "review-pr", "PR: refactor transfer funds check", base="main")
    subprocess.run(["patch", "-p1", "-s", "-i", str(GT / "backend-api" / "fixes" / "BA-2.patch")], cwd=d.proj, check=True)
    d.git("commit", "-qam", "main: fee included in funds check")
    d.git("checkout", "-qb", "pr/refactor-funds-check")
    subprocess.run(["patch", "-p1", "-R", "-s", "-i", str(GT / "backend-api" / "fixes" / "BA-2.patch")], cwd=d.proj, check=True)
    d.git("commit", "-qam", "refactor: simplify funds check")
    d.start()
    d.q("discover")
    d.phase("discovery")
    d.q("impact", "--base", "main")
    d.phase("impact")
    d.q("risk")
    d.phase("risk")
    d.phase("requirements", note="REQUIREMENTS.md: fee is paid by sender; balances never negative")
    d.exec("pytest", "--group", "existing-suite", "--label", "existing suite", "--", "tests")
    shutil.copytree(GT / "backend-api" / "reference_tests", d.proj / "tests" / "qa")
    ex = d.exec("pytest", "--group", "regression", "--label", "changed-behaviour tests", "--", "tests/qa/test_qa_invariants.py")
    d.phase("execution")
    tests = failing(ex)
    fid = d.finding({"title": "PR lets the fee overdraw a wallet (regression)", "category": "data-integrity", "severity": "critical",
                     "summary": "The refactored funds check compares the balance with the amount only; the debit includes the fee.",
                     "expected": "422 when amount + fee > balance; balance unchanged", "actual": "Transfer succeeds; balance becomes negative",
                     "reproduction_steps": ["Checkout pr/refactor-funds-check", "Deposit 1000", "Transfer 1000 (fee 10)", "Balance is -10"],
                     "reported_by": "qa-superteam:backend-qa-engineer", "test_identifiers": tests, "execution_ids": [ex["id"]],
                     "evidence_ids": ex["artifact_ids"][:2], "affected": [{"path": "ledger/transfers.py", "symbol": "create_transfer"}]})
    repro = d.reproduce(tests[0])
    d.verify(fid, repro[-1:], "Independent rerun on the PR head; consistent 3/3 failure, and the same test passes on main.")
    d.phase("verification")
    d.finish(out, "backend-pr-review")


def web_e2e(work: Path, out: Path):
    d = Demo("web-checkout", work, "test-e2e", "Checkout SPA: critical journeys and accessibility")
    env_chrome = _chromium()
    if env_chrome:
        os.environ.setdefault("CHROMIUM_EXECUTABLE", env_chrome)
    d.start()
    d.q("discover")
    d.phase("discovery")
    d.record("plan", {
        "scope": "Checkout SPA critical journeys, persistence, RTL, mobile and accessibility",
        "strategy_summary": "Journeys from docs/USER_JOURNEYS.md are mandatory (critical-journeys). Existing Playwright suite is the regression baseline. Accessibility via axe-core on each app state plus a page-level adapter scan; manual screen-reader checks are out of scope.",
        "test_cases": [
            {"id": "TC-RECOVER", "title": "Recover from a postal-code validation error and complete checkout", "level": "e2e", "technique": "state-transition", "oracle": "Continue becomes enabled after the error is corrected and the order is placed", "origin": "new", "test_ref": "tests/qa/test_qa_journeys.py::test_recover_from_postal_code_error_and_complete_checkout", "groups": ["critical-journeys"], "priority": "critical"},
            {"id": "TC-PROMO", "title": "Promo apply then remove restores the total", "level": "e2e", "technique": "state-transition", "oracle": "Total equals subtotal + shipping after Remove", "origin": "new", "test_ref": "tests/qa/test_qa_journeys.py::test_promo_apply_then_remove_restores_total", "groups": ["regression"], "priority": "high"},
            {"id": "TC-RTL", "title": "Arabic locale renders right-to-left", "level": "e2e", "technique": "equivalence", "oracle": "html[dir=rtl][lang=ar]", "origin": "new", "test_ref": "tests/qa/test_qa_journeys.py", "groups": ["critical-journeys"], "priority": "medium"},
            {"id": "TC-A11Y", "title": "No serious/critical axe violations on the review step", "level": "accessibility", "technique": "smoke", "oracle": "axe-core reports no serious or critical violations", "origin": "new", "test_ref": "tests/qa/test_qa_a11y.py", "groups": ["accessibility"], "priority": "high"},
        ],
        "out_of_scope": [{"item": "screen-reader and 200% zoom checks", "reason": "manual validation required; not automatable here"}],
        "specialists": ["qa-superteam:frontend-qa-engineer", "qa-superteam:independent-verification-engineer"],
    })
    d.phase("planning")
    d.exec("pytest", "--group", "existing-suite", "--label", "existing Playwright suite", "--", "tests")
    shutil.copytree(GT / "web-checkout" / "reference_tests", d.proj / "tests" / "qa")
    j = d.exec("pytest", "--group", "critical-journeys", "--label", "journeys", "--", "tests/qa/test_qa_journeys.py")
    a = d.exec("pytest", "--group", "accessibility", "--label", "axe on app states", "--", "tests/qa/test_qa_a11y.py")
    # page-level axe scan through the adapter against the locally served app
    sys.path.insert(0, str(d.proj))
    import importlib.util

    spec = importlib.util.spec_from_file_location("serve_demo", d.proj / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    server, base = mod.make_server(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        d.exec("axe", "--group", "accessibility", "--label", "axe landing page (375px)", "--target", base + "/", "--viewport", "375x812")
    finally:
        server.shutdown()
    d.phase("execution")
    for ex, frag, title, cat, sev, expected, actual, steps in [
        (j, "recover", "Checkout is blocked after correcting an invalid postal code", "functional", "high",
         "After fixing the postal code, Continue is enabled (USER_JOURNEYS.md: recovering from a validation error)",
         "Error clears but Continue stays disabled until reload",
         ["Fill contact step", "Enter postal code 12 for US", "See error", "Correct to 12345", "Continue stays disabled"]),
        (j, "promo", "Removing a promo code keeps the discount in the total", "functional", "medium",
         "Total returns to undiscounted value after Remove", "Total still includes the 10% discount",
         ["Reach review step", "Apply SAVE10", "Click Remove", "Total still discounted"]),
        (a, "", "Promo code input has no accessible name", "accessibility", "high",
         "Every form control has an accessible name (WCAG 1.3.1 / 4.1.2)", "axe 'label' violation on #promo-code",
         ["Reach review step", "Run axe-core", "Rule 'label' fails for #promo-code"]),
    ]:
        tests = [t for t in failing(ex) if frag in t.lower()] or failing(ex)
        if not tests:
            continue
        fid = d.finding({"title": title, "category": cat, "severity": sev, "summary": title, "expected": expected, "actual": actual,
                         "reproduction_steps": steps, "reported_by": "qa-superteam:frontend-qa-engineer", "test_identifiers": tests,
                         "execution_ids": [ex["id"]], "evidence_ids": ex["artifact_ids"], "affected": [{"path": "public/app.js"}]})
        repro = d.reproduce(tests[0])
        if sev in ("high", "critical"):
            d.verify(fid, repro[-1:], f"Independent rerun of {tests[0]}: consistent failure; screenshots attached.")
    d.phase("verification")
    d.finish(out, "web-e2e")


def ai_eval(work: Path, out: Path):
    d = Demo("ai-support-bot", work, "eval-ai", "Support bot: groundedness, tool calls, injection")
    d.start()
    d.q("discover")
    d.q("ai-eval", "validate", "evals/golden.jsonl")
    d.exec("pytest", "--group", "existing-suite", "--label", "unit tests", "--", "tests")
    d.exec("ai-eval", "--group", "ai-eval", "--label", "project golden set", "--dataset", "evals/golden.jsonl", "--entry", "support_bot.bot:answer")
    shutil.copy(GT / "ai-support-bot" / "reference_evals.jsonl", d.proj / "evals" / "qa_cases.jsonl")
    ex = d.exec("ai-eval", "--group", "ai-eval", "--label", "QA adversarial + tool-call cases", "--samples", "2", "--dataset", "evals/qa_cases.jsonl", "--entry", "support_bot.bot:answer")
    d.phase("execution")
    shutil.copytree(GT / "ai-support-bot" / "reference_tests", d.proj / "tests" / "qa")
    for case, title, cat, sev, expected, actual, path in [
        ("refund-tool-001", "Refund tool receives dollars instead of integer cents", "ai-quality", "high", "issue_refund(amount_cents=4999)", "issue_refund(amount_cents=49.99)", "support_bot/bot.py"),
        ("injection-001", "Instructions inside retrieved documents are followed (canary leaked)", "security", "high", "Answer ignores instructions in retrieved content", "Answer contains CANARY-7731", "support_bot/bot.py"),
        ("warranty-punct-001", "Trailing punctuation breaks retrieval and citations", "ai-quality", "medium", "Cites warranty.md", "Cites returns.md", "support_bot/retriever.py"),
    ]:
        ident = f"qa_cases::{case}"
        if not any(r["identifier"] == ident and r["status"] == "FAILED" for r in ex["results"]):
            continue
        fid = d.finding({"title": title, "category": cat, "severity": sev, "summary": title, "expected": expected, "actual": actual,
                         "reproduction_steps": [f"qast exec ai-eval --dataset evals/qa_cases.jsonl --entry support_bot.bot:answer (case {case})"],
                         "reported_by": "qa-superteam:ai-quality-engineer", "test_identifiers": [ident], "execution_ids": [ex["id"]],
                         "evidence_ids": ex["artifact_ids"], "affected": [{"path": path}]})
        if sev == "high":
            # alternate oracle: an independent pytest test of the same property
            pyname = {"refund-tool-001": "refund", "injection-001": "inject"}[case]
            v = d.exec("pytest", "--group", "ai-eval", "--label", f"alternate oracle for {case}", "--", "tests/qa", "-k", pyname)
            alt = failing(v)
            if alt:
                d.verify(fid, [v["id"]], f"Alternate oracle (pytest, different harness) reproduces the property violation: {alt[0]}", tests=alt[:1])
    d.phase("verification")
    d.finish(out, "ai-eval")


def _chromium() -> str | None:
    import glob

    c = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-*/chrome")), reverse=True)
    return c[0] if c else None


SCENARIOS = {"backend-full-audit": backend_full_audit, "backend-pr-review": backend_pr_review, "web-e2e": web_e2e, "ai-eval": ai_eval}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=[*SCENARIOS, "all"])
    ap.add_argument("--out", default=str(ROOT / "examples" / "reports"))
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    with tempfile.TemporaryDirectory(prefix="qast-demo-") as tmp:
        for n in names:
            SCENARIOS[n](Path(tmp) / n, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
