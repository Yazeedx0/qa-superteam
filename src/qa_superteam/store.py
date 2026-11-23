"""Run directory store.

Layout of ``<output_dir>/runs/<run_id>/``::

    run.json                 RunInfo
    journal.jsonl            append-only event log (phases, commands, mutations)
    profile.json             ProjectProfile          (singleton, supersede keeps history)
    impact.json              change impact           (singleton)
    requirements.json        RequirementSet          (singleton)
    risks.json               RiskRegister            (singleton)
    plan.json                TestPlan                (singleton)
    executions/<id>.json     TestExecution           (write-once)
    evidence/<id>.json       EvidenceArtifact        (content-addressed, write-once)
    artifacts/<id>-<name>    raw artifact bytes (text artifacts are redacted first)
    findings/<id>.json       DefectFinding           (write-once)
    verifications/<id>.json  VerificationResult      (write-once)
    decision.json            ReleaseDecision         (singleton)
    report.json / report.md  QAReport

Write-once records mean specialist agents cannot overwrite each other's results;
finding status is *derived* from reproduction/verification records.
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
from pathlib import Path
from typing import Any, Iterator

from . import models as m
from .config import Config
from .redact import Redactor
from .serde import from_dict, to_dict
from .util import (
    now_iso,
    read_json,
    sha256_bytes,
    slug,
    stable_id,
    write_json_atomic,
    write_json_exclusive,
)

SINGLETONS: dict[str, type] = {
    "profile": m.ProjectProfile,
    "requirements": m.RequirementSet,
    "risks": m.RiskRegister,
    "plan": m.TestPlan,
    "decision": m.ReleaseDecision,
    "coverage": m.CoverageAssessment,
    "impact": dict,  # free-form, produced only by qast impact
}

TEXT_SUFFIXES = {".txt", ".log", ".json", ".jsonl", ".xml", ".html", ".md", ".csv", ".har", ".yaml", ".yml", ".out"}

PHASES = (
    "discovery",
    "requirements",
    "impact",
    "risk",
    "planning",
    "delegation",
    "execution",
    "investigation",
    "verification",
    "release",
    "reporting",
    "regression",
)


class StoreError(RuntimeError):
    pass


class RunStore:
    def __init__(self, config: Config, run_id: str):
        self.config = config
        self.run_id = run_id
        self.dir = config.runs_dir / run_id
        self.redactor = Redactor.from_config(config.redaction_patterns, config.redact_emails)

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def create(
        cls,
        config: Config,
        mode: str,
        scope: str,
        base_ref: str | None = None,
        head_ref: str | None = None,
        environment: m.EnvironmentInfo | None = None,
        activate: bool = True,
    ) -> "RunStore":
        stamp = now_iso().replace("-", "").replace(":", "").replace("T", "-").rstrip("Z")
        run_id = f"{stamp}-{slug(mode, 16)}-{secrets.token_hex(2)}"
        store = cls(config, run_id)
        store.dir.mkdir(parents=True, exist_ok=False)
        _ensure_gitignore(config.output_dir)
        info = m.RunInfo(
            run_id=run_id,
            mode=mode,
            created_at=now_iso(),
            scope=scope,
            base_ref=base_ref,
            head_ref=head_ref,
            project_name=config.project_name or config.project_root.name,
            environment=environment,
        )
        write_json_exclusive(store.dir / "run.json", to_dict(info))
        store.journal("run.created", mode=mode, scope=scope)
        if activate:
            store.activate()
        return store

    @classmethod
    def resolve(cls, config: Config, run_id: str | None = None) -> "RunStore":
        if run_id:
            store = cls(config, run_id)
            if not (store.dir / "run.json").exists():
                raise StoreError(f"run not found: {run_id}")
            return store
        marker = active_marker(config)
        if marker.exists():
            rid = marker.read_text(encoding="utf-8").split()[0].strip()
            store = cls(config, rid)
            if (store.dir / "run.json").exists():
                return store
        runs = sorted(p.name for p in config.runs_dir.glob("*") if (p / "run.json").exists()) if config.runs_dir.exists() else []
        if not runs:
            raise StoreError("no QA run found; start one with: qast run start --mode <mode> --scope '<scope>'")
        return cls(config, runs[-1])

    def activate(self) -> None:
        marker = active_marker(self.config)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{self.run_id}\n{now_iso()}\n{self.dir}\n", encoding="utf-8")

    def deactivate(self) -> None:
        marker = active_marker(self.config)
        if marker.exists() and marker.read_text(encoding="utf-8").split()[0] == self.run_id:
            marker.unlink()

    @property
    def info(self) -> m.RunInfo:
        return from_dict(m.RunInfo, read_json(self.dir / "run.json"))

    # ------------------------------------------------------------------ journal
    def journal(self, event: str, **data: Any) -> None:
        rec = {"ts": now_iso(), "event": event, **data}
        line = json.dumps(rec, ensure_ascii=False)
        line = self.redactor.redact(line)
        with open(self.dir / "journal.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def journal_events(self) -> list[dict[str, Any]]:
        path = self.dir / "journal.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def phase_states(self) -> dict[str, str]:
        states = {p: "pending" for p in PHASES}
        for ev in self.journal_events():
            if ev.get("event") == "phase" and ev.get("phase") in states:
                states[ev["phase"]] = ev.get("state", "pending")
        return states

    # ------------------------------------------------------------------ artifacts
    def add_artifact(
        self,
        name: str,
        data: bytes,
        kind: m.ArtifactKind,
        execution_id: str | None = None,
        description: str | None = None,
        media_type: str | None = None,
    ) -> m.EvidenceArtifact:
        redacted = False
        redactions = 0
        suffix = Path(name).suffix.lower()
        if suffix in TEXT_SUFFIXES or kind in (m.ArtifactKind.LOG, m.ArtifactKind.JUNIT, m.ArtifactKind.REPORT):
            text = data.decode("utf-8", errors="replace")
            before = self.redactor.count
            text = self.redactor.redact(text)
            redactions = self.redactor.count - before
            data = text.encode("utf-8")
            redacted = True
        max_bytes = self.config.budgets.max_artifact_bytes
        if len(data) > max_bytes:
            raise StoreError(f"artifact {name} is {len(data)} bytes, over budget ({max_bytes})")
        digest = sha256_bytes(data)
        art_id = f"ev-{digest[:12]}"
        rec_path = self.dir / "evidence" / f"{art_id}.json"
        if rec_path.exists():  # content-addressed: identical evidence is stored once
            return from_dict(m.EvidenceArtifact, read_json(rec_path))
        safe_name = slug(Path(name).stem, 60) + suffix
        rel = f"artifacts/{art_id}-{safe_name}"
        out = self.dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        art = m.EvidenceArtifact(
            id=art_id,
            kind=kind,
            path=rel,
            sha256=digest,
            size_bytes=len(data),
            media_type=media_type or mimetypes.guess_type(name)[0] or "application/octet-stream",
            created_at=now_iso(),
            redacted=redacted,
            redactions=redactions,
            execution_id=execution_id,
            description=description,
        )
        write_json_exclusive(rec_path, to_dict(art))
        return art

    def artifacts(self) -> list[m.EvidenceArtifact]:
        return [from_dict(m.EvidenceArtifact, d) for d in self._iter_dir("evidence")]

    def verify_artifact(self, art: m.EvidenceArtifact) -> str | None:
        """Return a problem description if the artifact is missing or tampered, else None."""
        path = self.dir / art.path
        if not path.exists():
            return f"{art.id}: file missing ({art.path})"
        if sha256_bytes(path.read_bytes()) != art.sha256:
            return f"{art.id}: sha256 mismatch (file modified after recording)"
        return None

    # ------------------------------------------------------------------ records
    def next_sequence(self, sub: str) -> int:
        d = self.dir / sub
        return (len(list(d.glob("*.json"))) if d.exists() else 0) + 1

    def save_execution(self, ex: m.TestExecution) -> Path:
        return self._write_once("executions", ex.id, ex)

    def save_finding(self, f: m.DefectFinding) -> Path:
        return self._write_once("findings", f.id, f)

    def save_verification(self, v: m.VerificationResult) -> Path:
        return self._write_once("verifications", v.id, v)

    def _write_once(self, sub: str, rec_id: str, obj: Any) -> Path:
        path = self.dir / sub / f"{rec_id}.json"
        try:
            write_json_exclusive(path, to_dict(obj))
        except FileExistsError:
            raise StoreError(f"{sub[:-1]} {rec_id} already recorded; records are write-once") from None
        self.journal(f"{sub[:-1]}.recorded", id=rec_id)
        return path

    def executions(self) -> list[m.TestExecution]:
        return [from_dict(m.TestExecution, d) for d in self._iter_dir("executions")]

    def findings(self) -> list[m.DefectFinding]:
        return [from_dict(m.DefectFinding, d) for d in self._iter_dir("findings")]

    def verifications(self) -> list[m.VerificationResult]:
        return [from_dict(m.VerificationResult, d) for d in self._iter_dir("verifications")]

    def _iter_dir(self, sub: str) -> Iterator[dict]:
        d = self.dir / sub
        if not d.exists():
            return iter(())
        files = sorted(d.glob("*.json"), key=lambda p: (os.path.getmtime(p), p.name))
        return (read_json(p) for p in files)

    # ------------------------------------------------------------------ singletons
    def save_singleton(self, name: str, obj: Any, supersede: bool = False) -> Path:
        if name not in SINGLETONS:
            raise StoreError(f"unknown record kind: {name}")
        path = self.dir / f"{name}.json"
        data = obj if isinstance(obj, dict) else to_dict(obj)
        if path.exists():
            if not supersede:
                raise StoreError(f"{name}.json already exists; pass --supersede to replace it (old version is kept in history/)")
            hist = self.dir / "history"
            hist.mkdir(exist_ok=True)
            n = len(list(hist.glob(f"{name}.v*.json"))) + 1
            os.replace(path, hist / f"{name}.v{n}.json")
            self.journal("record.superseded", kind=name, version=n)
        write_json_atomic(path, data)
        self.journal("record.saved", kind=name)
        return path

    def load_singleton(self, name: str) -> Any | None:
        path = self.dir / f"{name}.json"
        if not path.exists():
            return None
        data = read_json(path)
        cls = SINGLETONS.get(name)
        if cls is None or cls is dict:
            return data
        return from_dict(cls, data)

    # ------------------------------------------------------------------ ids
    def execution_id(self, adapter: str, label: str) -> str:
        return stable_id("ex", self.run_id, str(self.next_sequence("executions")), adapter, label)

    def finding_id(self, title: str, paths: list[str], tests: list[str]) -> str:
        return stable_id("F", self.run_id, title.strip().lower(), *sorted(paths), *sorted(tests), length=8)

    def verification_id(self, finding_id: str, verifier: str) -> str:
        return stable_id("V", self.run_id, finding_id, verifier, str(self.next_sequence("verifications")), length=8)


def active_marker(config: Config) -> Path:
    """Fixed location (independent of [output] dir) so the guard hook can find it cheaply."""
    return config.project_root / ".qa-superteam" / "active-run"


def _ensure_gitignore(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    gi = output_dir / ".gitignore"
    if not gi.exists():
        gi.write_text("# QA Superteam run output (evidence may be sensitive even after redaction)\nruns/\nactive-run\n", encoding="utf-8")
