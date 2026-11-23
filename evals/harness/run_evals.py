#!/usr/bin/env python3
"""Behavioral evaluation runner: baseline (no plugin) vs skill-enabled Claude Code.

    python3 evals/harness/run_evals.py --list
    python3 evals/harness/run_evals.py                      # dry run: all NOT_RUN, nothing invented
    python3 evals/harness/run_evals.py --live --model sonnet --only qa-verification,review-pr --conditions plugin,baseline

Safety: the agent under evaluation runs in a throw-away copy of a fixture with a tool
allowlist (no --dangerously-skip-permissions unless --unsafe-bypass is passed, which
should only ever be used inside a disposable container/CI runner).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from graders import grade, run_dir_records  # noqa: E402
from transcript import parse_stream_json  # noqa: E402

FIXTURES = {"backend-api", "web-checkout", "ai-support-bot"}
USAGE_LIMIT_RE = __import__("re").compile(r"(?i)(hit your .{0,20}limit|usage limit|out of (usage )?credits|rate limit|overloaded|invalid api key|not logged in|please run /login)")
ALLOWED_TOOLS = [
    "Read", "Grep", "Glob", "Write", "Edit", "Skill", "Agent", "TodoWrite",
    "Bash(qast:*)", "Bash(python3:*)", "Bash(python:*)", "Bash(pytest:*)", "Bash(npx playwright:*)", "Bash(npm test:*)",
    "Bash(git diff:*)", "Bash(git log:*)", "Bash(git status:*)", "Bash(git show:*)", "Bash(git rev-parse:*)", "Bash(git branch:*)",
    "Bash(git archive:*)", "Bash(tar:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(grep:*)", "Bash(find:*)", "Bash(mkdir:*)", "Bash(cp:*)",
]


def load_scenarios(only: set[str] | None) -> list[dict]:
    out = []
    for f in sorted((ROOT / "evals" / "scenarios").glob("*.json")):
        for sc in json.loads(f.read_text(encoding="utf-8")):
            sc.setdefault("conditions", ["plugin"])
            sc.setdefault("max_turns", 30)
            if only and sc["skill"] not in only and sc["id"] not in only:
                continue
            out.append(sc)
    return out


def ground_truth(fixture: str | None) -> dict | None:
    if not fixture:
        return None
    p = ROOT / "evals" / "ground_truth" / fixture / "ground_truth.json"
    return json.loads(p.read_text()) if p.exists() else None


def prepare_project(sc: dict, workdir: Path) -> Path:
    proj = workdir / "project"
    fx = sc.get("fixture")
    if fx:
        src = ROOT / "examples" / fx
        shutil.copytree(src, proj, ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", ".qa-superteam"))
        if (src / "node_modules").exists():
            (proj / "node_modules").symlink_to(src / "node_modules")
    else:
        proj.mkdir(parents=True)
    for rel, content in (sc.get("files") or {}).items():
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "eval@example.com", "GIT_COMMITTER_NAME": "eval", "GIT_COMMITTER_EMAIL": "eval@example.com"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=proj, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=proj, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "fixture baseline", "--allow-empty"], cwd=proj, check=True, env=env)
    env["PATH"] = f"{ROOT / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    for cmd in sc.get("setup", []):
        r = subprocess.run(cmd, shell=True, cwd=proj, env=env, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"setup failed: {cmd}: {r.stderr[-500:]}")
    return proj


def prompt_for(sc: dict, condition: str) -> str:
    """Baseline runs have no plugin, so slash commands become the equivalent plain request."""
    if condition != "baseline":
        return sc["prompt"]
    if sc.get("baseline_prompt"):
        return sc["baseline_prompt"]
    p = sc["prompt"].strip()
    if p.startswith("/qa-superteam:"):
        name, _, rest = p[len("/qa-superteam:"):].partition(" ")
        return f"Act as a QA engineer and perform a {name.replace('-', ' ')} for this project. {rest}".strip()
    return p


def run_claude(sc: dict, proj: Path, condition: str, args) -> tuple[str, float]:
    cmd = ["claude", "-p", prompt_for(sc, condition), "--output-format", "stream-json", "--verbose", "--max-turns", str(sc["max_turns"]),
           "--setting-sources", "project", "--strict-mcp-config", "--no-session-persistence"]
    if args.model:
        cmd += ["--model", args.model]
    if args.bare:
        cmd.append("--bare")
    if condition == "plugin":
        cmd += ["--plugin-dir", str(ROOT)]
    if args.unsafe_bypass:
        cmd.append("--dangerously-skip-permissions")
    else:
        cmd += ["--allowedTools", *ALLOWED_TOOLS]
    env = dict(os.environ)
    if condition == "baseline":  # the baseline agent does not get qast on PATH
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if not p.startswith(str(ROOT)))
    start = time.monotonic()
    out = subprocess.run(cmd, cwd=proj, env=env, capture_output=True, text=True, timeout=args.timeout)
    return out.stdout + ("\n" + out.stderr if out.returncode else ""), time.monotonic() - start


def evaluate(sc: dict, condition: str, args, out_dir: Path) -> dict:
    rec = {"scenario": sc["id"], "skill": sc["skill"], "condition": condition, "fixture": sc.get("fixture")}
    if not args.live:
        return {**rec, "status": "NOT_RUN", "reason": "live execution disabled (pass --live)"}
    if shutil.which("claude") is None:
        return {**rec, "status": "NOT_RUN", "reason": "claude CLI not found"}
    with tempfile.TemporaryDirectory(prefix="qast-eval-") as tmp:
        try:
            proj = prepare_project(sc, Path(tmp))
            raw, secs = run_claude(sc, proj, condition, args)
        except subprocess.TimeoutExpired:
            return {**rec, "status": "ERROR", "reason": f"timed out after {args.timeout}s"}
        except Exception as e:  # noqa: BLE001
            return {**rec, "status": "ERROR", "reason": str(e)[:500]}
        safe = sc["id"].replace("/", "__")
        (out_dir / f"{safe}.{condition}.jsonl").write_text(raw, encoding="utf-8")
        t = parse_stream_json(raw)
        if not t.tool_calls and not t.final_text:
            return {**rec, "status": "ERROR", "reason": "no transcript (auth or CLI error): " + raw[-300:]}
        limit = USAGE_LIMIT_RE.search(t.final_text or "")
        if (t.is_error or limit) and not t.tool_calls:
            # the session never started working: not a behavioral result
            return {**rec, "status": "NOT_RUN", "reason": f"session did not run: {(t.final_text or raw)[-200:].strip()}", "cost_usd": t.cost_usd}
        if limit:
            return {**rec, "status": "ERROR", "reason": f"session interrupted by a usage/rate limit after {len(t.tool_calls)} tool calls", "cost_usd": t.cost_usd}
        p = sc["prompt"].strip()
        if condition == "plugin" and p.startswith("/qa-superteam:"):
            t.slash_skill = p[len("/qa-superteam:"):].split()[0]
        gt = ground_truth(sc.get("fixture"))
        results = [grade(c, t, proj, gt) for c in sc["checks"]]
        recs = run_dir_records(proj)
        findings = recs["findings"]
        views = recs.get("views", {})
        valid_evidence = [f for f in findings if f.get("execution_ids") and f.get("evidence_ids")]
        return {
            **rec,
            "status": "PASSED" if all(r.passed for r in results) else "FAILED",
            "checks": [r.__dict__ for r in results],
            "duration_s": round(secs, 1),
            "cost_usd": t.cost_usd,
            "turns": t.num_turns,
            "skills": t.skills,
            "agents": t.agents,
            "findings": len(findings),
            "findings_reproduced_or_confirmed": sum(1 for f in findings if views.get(f.get("id")) in ("REPRODUCED", "CONFIRMED")),
            "findings_with_evidence": len(valid_evidence),
            "final_text_excerpt": t.final_text[:1500],
        }


def aggregate(results: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for cond in sorted({r["condition"] for r in results}):
        rs = [r for r in results if r["condition"] == cond]
        ran = [r for r in rs if r["status"] in ("PASSED", "FAILED")]
        checks = [c for r in ran for c in r.get("checks", [])]

        def rate(typ, checks=checks):
            cs = [c for c in checks if c["type"] == typ]
            return round(sum(c["passed"] for c in cs) / len(cs), 3) if cs else None

        gts = [c["metrics"] for c in checks if c["type"] == "findings_vs_ground_truth" and c.get("metrics")]
        recalls = [g["recall"] for g in gts if g.get("recall") is not None]
        precs = [g["precision"] for g in gts if g.get("precision") is not None]
        fps = sum(g.get("false_positives", 0) for g in gts)
        claims = [c for c in checks if c["type"] == "no_unsupported_pass_claim"]
        nfind = sum(r.get("findings", 0) for r in ran)
        out[cond] = {
            "scenarios": len(rs),
            "executed": len(ran),
            "not_run": sum(r["status"] == "NOT_RUN" for r in rs),
            "errors": sum(r["status"] == "ERROR" for r in rs),
            "scenario_pass_rate": round(sum(r["status"] == "PASSED" for r in ran) / len(ran), 3) if ran else None,
            "skill_selection_accuracy": rate("skill_invoked"),
            "defect_recall_mean": round(sum(recalls) / len(recalls), 3) if recalls else None,
            "defect_precision_mean": round(sum(precs) / len(precs), 3) if precs else None,
            "false_positives": fps if gts else None,
            "reproduction_success_rate": round(sum(r.get("findings_reproduced_or_confirmed", 0) for r in ran) / nfind, 3) if nfind else None,
            "evidence_completeness": round(sum(r.get("findings_with_evidence", 0) for r in ran) / nfind, 3) if nfind else None,
            "unsupported_claim_rate": round(sum(1 for c in claims if not c["passed"]) / len(claims), 3) if claims else None,
            "total_duration_s": round(sum(r.get("duration_s", 0) for r in ran), 1) if ran else None,
            "total_cost_usd": round(sum(r.get("cost_usd") or 0 for r in ran), 4) if any(r.get("cost_usd") for r in ran) else None,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--live", action="store_true", help="actually run Claude Code (costs tokens)")
    ap.add_argument("--only", help="comma-separated skill names or scenario ids")
    ap.add_argument("--conditions", default="plugin,baseline")
    ap.add_argument("--model", default=None)
    ap.add_argument("--bare", action="store_true", help="pass --bare (CI with ANTHROPIC_API_KEY; skips user plugins, hooks, CLAUDE.md)")
    ap.add_argument("--unsafe-bypass", action="store_true", help="--dangerously-skip-permissions; disposable containers only")
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--max-scenarios", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    scenarios = load_scenarios(only)
    if args.max_scenarios:
        scenarios = scenarios[: args.max_scenarios]
    if args.list:
        for sc in scenarios:
            print(f"{sc['id']:<60} skill={sc['skill']:<22} fixture={sc.get('fixture')} conditions={','.join(sc['conditions'])} checks={len(sc['checks'])}")
        print(f"{len(scenarios)} scenario(s)")
        return 0
    conditions = [c for c in args.conditions.split(",") if c]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) if args.out else ROOT / "evals" / "results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for sc in scenarios:
        for cond in conditions:
            if cond not in sc["conditions"]:
                continue
            r = evaluate(sc, cond, args, out_dir)
            results.append(r)
            print(f"[{r['status']:<8}] {cond:<8} {sc['id']}" + (f" — {r.get('reason')}" if r.get("reason") else "") + (f" ({r.get('duration_s')}s, ${r.get('cost_usd')})" if r.get("duration_s") else ""))
    summary = {"generated": stamp, "live": args.live, "model": args.model, "metrics": aggregate(results), "results": results}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["metrics"], indent=2))
    print(f"results: {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
