"""Change impact analysis (Phase C) from a real Git diff, plus baseline risk scoring (Phase D).

Impact is computed from ``git diff`` output — no guessing about what changed.  Test
selection uses three transparent heuristics, each recorded with the reason it fired:

1. *changed test*        — the test file itself changed
2. *name match*          — tests whose file stem matches a changed module stem
3. *import reference*    — test files that mention the changed module's import path

Risk scoring (docs/risk-model.md) is probability x impact on 1..5 scales built from
documented factors; agents may refine it, recording their rationale as assumptions.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import models as m
from .discovery import SKIP_DIRS

SENSITIVE_PATTERNS = [
    (r"(?i)auth|login|session|token|password|permission|rbac|acl|oauth|jwt|csrf|cors", "security-sensitive (authentication/authorization)", 5),
    (r"(?i)payment|billing|invoice|charge|refund|wallet|balance|ledger|transfer|price|checkout|order", "money movement / business-critical", 5),
    (r"(?i)migration|schema|\.sql$|models?\.py$|entity|repository", "data model / persistence", 4),
    (r"(?i)crypto|secret|encrypt|sign", "cryptography / secrets", 5),
    (r"(?i)prompt|llm|agent|retriev|embedding|rag|tool", "AI behaviour", 4),
    (r"(?i)api|route|router|controller|endpoint|handler|views?\.py$", "API surface", 4),
    (r"(?i)(^|/)(public|static|src/components|pages|app)/|\.(jsx|tsx|vue|svelte|html|css)$", "user interface", 3),
    (r"(?i)(^|/)(\.github|ci|deploy|docker|k8s|helm|terraform)", "build / deployment", 3),
    (r"(?i)package(-lock)?\.json$|requirements.*\.txt$|pyproject\.toml$|poetry\.lock$|go\.(mod|sum)$|uv\.lock$", "dependency change", 3),
]


@dataclass
class ChangedFile:
    path: str
    status: str  # A, M, D, R
    added: int = 0
    removed: int = 0
    kind: str = "source"
    signals: list[str] = field(default_factory=list)
    impact_hint: int = 2


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def classify_path(path: str) -> tuple[str, list[str], int]:
    low = path.lower()
    name = low.rsplit("/", 1)[-1]
    if re.search(r"(^|/)(tests?|spec|__tests__|e2e)/", low) or name.startswith("test_") or re.search(r"\.(test|spec)\.", name) or name.endswith("_test.py"):
        kind = "test"
    elif low.endswith((".md", ".rst", ".txt")) or low.startswith("docs/"):
        kind = "docs"
    elif re.search(r"\.(json|ya?ml|toml|ini|cfg|env)$", low):
        kind = "config"
    else:
        kind = "source"
    signals, hint = [], 2 if kind == "source" else 1
    for rx, label, weight in SENSITIVE_PATTERNS:
        if re.search(rx, path):
            signals.append(label)
            hint = max(hint, weight)
    if kind in ("docs",):
        hint = 1
    return kind, signals, hint


def changed_files(root: Path, base: str, head: str | None, include_worktree: bool) -> list[ChangedFile]:
    """Files changed since the merge base of ``base`` and ``head`` (or HEAD).

    * ``head`` given        -> committed changes ``merge-base(base, head)..head``
    * ``head`` omitted      -> merge base vs. the working tree (+ untracked files when
                               ``include_worktree``), i.e. what a PR would contain now
    """
    tip = head or "HEAD"
    mb = _git(root, "merge-base", base, tip).strip()
    spec = [mb, head] if head else ([mb] if include_worktree else [mb, "HEAD"])
    entries: dict[str, ChangedFile] = {}
    for line in _git(root, "diff", "--name-status", "-M", *spec).splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0][0], parts[-1]
        entries[path] = ChangedFile(path=path, status=status)
    for line in _git(root, "diff", "--numstat", "-M", *spec).splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2] in entries:
            entries[parts[2]].added = int(parts[0]) if parts[0].isdigit() else 0
            entries[parts[2]].removed = int(parts[1]) if parts[1].isdigit() else 0
    if include_worktree:
        for line in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():
            parts = set(line.split("/")[:-1])
            if (
                line
                and line not in entries
                and not (parts & SKIP_DIRS)
                and not line.endswith((".pyc", ".pyo"))
                and not line.startswith(".qa-superteam/")
            ):
                entries[line] = ChangedFile(path=line, status="A")
    for cf in entries.values():
        cf.kind, cf.signals, cf.impact_hint = classify_path(cf.path)
    return sorted(entries.values(), key=lambda c: c.path)


def _test_files(root: Path) -> list[str]:
    out = []
    for p in root.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            kind, _, _ = classify_path(rel)
            if kind == "test" and p.suffix in (".py", ".js", ".ts", ".tsx", ".jsx", ".mjs"):
                out.append(rel)
    return sorted(out)


def select_tests(root: Path, changes: list[ChangedFile]) -> list[dict]:
    tests = _test_files(root)
    selected: dict[str, list[str]] = {}
    for cf in changes:
        if cf.status == "D":
            continue
        if cf.kind == "test":
            selected.setdefault(cf.path, []).append("changed test")
            continue
        if cf.kind != "source":
            continue
        stem = Path(cf.path).stem.lower()
        module = cf.path.rsplit(".", 1)[0].replace("/", ".")
        mod_tail = module.split(".")[-1]
        for t in tests:
            tstem = Path(t).stem.lower().replace("test_", "").replace("_test", "").split(".")[0]
            if tstem and (tstem == stem or (len(stem) > 3 and stem in tstem)):
                selected.setdefault(t, []).append(f"name match: {cf.path}")
                continue
            try:
                text = (root / t).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(rf"\b{re.escape(module)}\b", text) or re.search(rf"(from|import)\s+[\w.]*\b{re.escape(mod_tail)}\b", text) or (cf.path.endswith((".js", ".ts")) and Path(cf.path).name.split(".")[0] in text):
                selected.setdefault(t, []).append(f"import reference: {cf.path}")
    return [{"test": t, "reasons": sorted(set(r))} for t, r in sorted(selected.items())]


def analyze(root: Path, base: str, head: str | None = None, include_worktree: bool = True) -> dict:
    root = root.resolve()
    changes = changed_files(root, base, head, include_worktree)
    selection = select_tests(root, changes)
    components: dict[str, dict] = {}
    for cf in changes:
        comp = cf.path.split("/")[0] if "/" in cf.path else "."
        c = components.setdefault(comp, {"component": comp, "files": 0, "lines_changed": 0, "signals": set(), "max_impact_hint": 1})
        c["files"] += 1
        c["lines_changed"] += cf.added + cf.removed
        c["signals"].update(cf.signals)
        c["max_impact_hint"] = max(c["max_impact_hint"], cf.impact_hint)
    source_without_tests = [
        cf.path for cf in changes if cf.kind == "source" and cf.status != "D" and not any(cf.path in r for s in selection for r in s["reasons"])
    ]
    return {
        "base": base,
        "head": head or ("WORKTREE" if include_worktree else "HEAD"),
        "head_sha": _git(root, "rev-parse", "HEAD").strip(),
        "files": [cf.__dict__ for cf in changes],
        "components": [{**c, "signals": sorted(c["signals"])} for c in components.values()],
        "selected_tests": selection,
        "changed_source_without_related_tests": source_without_tests,
        "method": "git diff --name-status/--numstat; tests selected by changed-test, name-match and import-reference heuristics",
        "limitations": [
            "Dynamic imports, dependency injection and cross-service calls are not traced.",
            "Selection is a starting point: high-risk changes still warrant the full mandatory suite.",
        ],
    }


# --------------------------------------------------------------------------- risk


def _level(score: int) -> m.Severity:
    if score >= 20:
        return m.Severity.CRITICAL
    if score >= 12:
        return m.Severity.HIGH
    if score >= 6:
        return m.Severity.MEDIUM
    return m.Severity.LOW


def baseline_risks(profile: m.ProjectProfile | None, impact: dict | None, critical_paths: list[str]) -> m.RiskRegister:
    """Transparent starting risk register. Each factor states its rationale and basis."""
    risks: list[m.RiskAssessment] = []
    has_tests = bool(profile and profile.test_suites)
    if impact:
        for i, comp in enumerate(sorted(impact["components"], key=lambda c: -c["max_impact_hint"]), start=1):
            files = [f for f in impact["files"] if (f["path"].split("/")[0] if "/" in f["path"] else ".") == comp["component"]]
            if all(f["kind"] in ("docs",) for f in files):
                continue
            lines = comp["lines_changed"]
            untested = [f["path"] for f in files if f["path"] in impact["changed_source_without_related_tests"]]
            size_p = 1 if lines < 20 else 2 if lines < 100 else 3 if lines < 400 else 4
            prob = min(5, size_p + (1 if untested else 0) + (1 if not has_tests else 0))
            crit = any(any(f["path"].startswith(cp) for cp in critical_paths) for f in files)
            imp = min(5, max(comp["max_impact_hint"], 5 if crit else 1))
            factors = [
                m.RiskFactor(name="change size", value=size_p, rationale=f"{lines} lines changed across {comp['files']} file(s)", basis=m.Basis.OBSERVED),
                m.RiskFactor(name="related tests", value=5 if untested else 1, rationale=(f"no related tests found for {untested}" if untested else "related tests selected"), basis=m.Basis.INFERRED),
                m.RiskFactor(name="impact signals", value=comp["max_impact_hint"], rationale=", ".join(comp["signals"]) or "no sensitive-area signals", basis=m.Basis.INFERRED),
            ]
            if crit:
                factors.append(m.RiskFactor(name="configured critical path", value=5, rationale="matches [project] critical_paths", basis=m.Basis.OBSERVED))
            risks.append(
                m.RiskAssessment(
                    id=f"R-{i:02d}",
                    area=comp["component"],
                    description=f"Regression in {comp['component']} from the current change",
                    probability=prob,
                    impact=imp,
                    score=prob * imp,
                    level=_level(prob * imp),
                    factors=factors,
                    paths=[f["path"] for f in files],
                    existing_coverage="related tests selected" if not untested else "no related tests detected",
                    assumptions=["Impact signals come from path/name heuristics; confirm business criticality with requirements."],
                )
            )
    elif profile:
        for i, comp in enumerate([c for c in profile.components if c.kind == "source"], start=1):
            _, signals, hint = classify_path(comp.path + "/")
            crit = any(cp.startswith(comp.path) for cp in critical_paths)
            imp = 5 if crit else max(hint, 2)
            prob = 3 if has_tests else 4
            risks.append(
                m.RiskAssessment(
                    id=f"R-{i:02d}",
                    area=comp.name,
                    description=f"Defects in {comp.name}",
                    probability=prob,
                    impact=imp,
                    score=prob * imp,
                    level=_level(prob * imp),
                    factors=[
                        m.RiskFactor(name="test presence", value=prob, rationale="project has automated tests" if has_tests else "no automated tests found", basis=m.Basis.OBSERVED),
                        m.RiskFactor(name="criticality", value=imp, rationale="configured critical path" if crit else (", ".join(signals) or "default"), basis=m.Basis.INFERRED),
                    ],
                    paths=[comp.path],
                    assumptions=["Full-audit baseline without a diff; refine with requirements and invariants."],
                )
            )
    return m.RiskRegister(risks=sorted(risks, key=lambda r: -r.score))
