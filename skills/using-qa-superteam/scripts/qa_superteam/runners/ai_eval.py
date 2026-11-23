"""AI eval runner. Executed as a subprocess with the *project's* interpreter:

    python -m qa_superteam.runners.ai_eval --dataset D --target pkg.mod:fn --out results.jsonl

It imports the system under test (project code), so it is run like any other test
command — under the host's permission model, inside the project's environment.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

from qa_superteam import aieval
from qa_superteam.runners import judge as judge_mod


def load_target(spec: str):
    if ":" not in spec:
        raise SystemExit(f"--target must look like package.module:function, got {spec!r}")
    mod_name, fn_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, fn_name, None)
    if not callable(fn):
        raise SystemExit(f"{spec} is not callable")
    return fn


def run_case(target, case: dict, samples: int, judge_cfg: aieval.JudgeConfig, judge_model: str | None) -> aieval.CaseOutcome:
    expect = case.get("expect", {}) or {}
    statuses: list[str] = []
    last_checks: list[aieval.CheckResult] = []
    last_reason = ""
    latency = None
    usage: dict = {}
    estimated = False
    answer = ""
    judge_info = None
    for _ in range(samples):
        start = time.perf_counter()
        try:
            output = target(case["input"])
        except Exception:  # noqa: BLE001 - any exception in the SUT is an ERROR outcome
            statuses.append("ERROR")
            last_reason = "target raised: " + traceback.format_exc(limit=5)[-1500:]
            continue
        latency = (time.perf_counter() - start) * 1000.0
        if not isinstance(output, dict) or "answer" not in output:
            statuses.append("ERROR")
            last_reason = f"target returned {type(output).__name__} without an 'answer' key"
            continue
        checks, usage, estimated = aieval.deterministic_checks(expect, output, latency)
        override = None
        if case.get("judge"):
            verdict = None
            if judge_cfg.available:
                verdict = judge_mod.judge(case, output, judge_model)
            override, jcheck, judge_info = aieval.apply_judge(verdict, judge_cfg)
            checks.append(jcheck)
        st, reason = aieval.case_status(checks, override)
        statuses.append(st)
        last_checks, last_reason = checks, reason
        answer = str(output.get("answer", ""))
    status, sreason = aieval.combine_samples(statuses)
    return aieval.CaseOutcome(
        case_id=case["id"],
        status=status,
        checks=last_checks,
        reason=sreason or last_reason,
        latency_ms=round(latency, 3) if latency is not None else None,
        usage=usage,
        usage_estimated=estimated,
        answer_preview=answer[:600],
        samples=statuses if samples > 1 else [],
        judge=judge_info,
        tags=list(case.get("tags", [])),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qa_superteam.runners.ai_eval")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--judge-model", default=None, help="enable model-graded checks with this model id")
    ap.add_argument("--calibration", default=None, help="calibration.json produced by qast ai-eval calibrate")
    ap.add_argument("--min-kappa", type=float, default=0.6)
    args = ap.parse_args(argv)

    for extra in reversed([p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    sys.path.insert(0, str(Path.cwd()))
    cases = aieval.parse_dataset(Path(args.dataset).read_text(encoding="utf-8"))
    target = load_target(args.target)

    judge_cfg = aieval.JudgeConfig(available=False, reason="judge not configured (pass --judge-model to enable)", min_kappa=args.min_kappa)
    if args.judge_model:
        ok, why = judge_mod.available()
        judge_cfg.available, judge_cfg.reason = ok, why
        if args.calibration and Path(args.calibration).exists():
            cal = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
            judge_cfg.kappa = cal.get("kappa")
            judge_cfg.calibration_n = int(cal.get("n") or 0)
            judge_cfg.model_matches = cal.get("judge_model") == args.judge_model

    samples = max(1, min(args.samples, 10))
    outcomes = [run_case(target, c, samples, judge_cfg, args.judge_model) for c in cases]
    with open(args.out, "w", encoding="utf-8") as fh:
        for o in outcomes:
            fh.write(json.dumps(o.as_dict(), ensure_ascii=False) + "\n")
    summary = aieval.summarize(outcomes)
    summary["judge"] = {"available": judge_cfg.available, "reason": judge_cfg.reason, "kappa": judge_cfg.kappa, "min_kappa": judge_cfg.min_kappa}
    Path(args.out).with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
