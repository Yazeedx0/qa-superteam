"""Typed records for QA Superteam.

These dataclasses are the single source of truth for every JSON record the framework
reads or writes.  ``scripts/gen_schemas.py`` exports them to ``schemas/*.schema.json``
and CI fails if the committed schemas drift from this module.

Design rules encoded here:

* Execution outcomes use seven explicit states (:class:`Status`).  They are never
  collapsed into a boolean.
* Every fact carries a :class:`Basis` (observed / inferred / assumed) and a
  :class:`Confidence`.  Confidence is a documented ordinal judgement, never an
  invented percentage.
* A :class:`TestCase` must state its oracle (expected observable outcome).
* A :class:`DefectFinding` must reference evidence; its effective status is derived
  from reproduction and verification records rather than edited in place.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from .serde import field

SCHEMA_VERSION = "1.0"


# --------------------------------------------------------------------------- enums


class Status(enum.StrEnum):
    """Normalized execution status. Never collapse to pass/fail."""

    PASSED = "PASSED"  # executed and the oracle held
    FAILED = "FAILED"  # executed and the oracle was violated (product behaviour)
    ERROR = "ERROR"  # executed but the test/tooling itself broke (setup crash, timeout)
    SKIPPED = "SKIPPED"  # the test framework deliberately skipped it
    BLOCKED = "BLOCKED"  # could not execute: missing tool, environment or authorization
    NOT_RUN = "NOT_RUN"  # planned but not attempted (budget, deselected, no tests collected)
    INCONCLUSIVE = "INCONCLUSIVE"  # executed but the outcome cannot be trusted (flaky, judge uncertainty)


class Severity(enum.StrEnum):
    """Impact of a defect if it reaches users. Definitions live in the active policy."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


SEVERITY_RANK = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}


class Confidence(enum.StrEnum):
    """Ordinal confidence. See docs/evidence-model.md for the measurement basis."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Basis(enum.StrEnum):
    """How a fact was established."""

    OBSERVED = "observed"  # read directly from a file, command output or test result
    INFERRED = "inferred"  # derived from observed facts by a documented heuristic
    ASSUMED = "assumed"  # adopted without evidence; must be listed as an assumption


class Category(enum.StrEnum):
    FUNCTIONAL = "functional"
    SECURITY = "security"
    DATA_INTEGRITY = "data-integrity"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    ACCESSIBILITY = "accessibility"
    CONTRACT = "contract"
    AI_QUALITY = "ai-quality"
    USABILITY = "usability"
    OTHER = "other"


class FindingStatus(enum.StrEnum):
    """Lifecycle of a defect claim. Only CONFIRMED findings count as verified defects."""

    SUSPECTED = "SUSPECTED"  # hypothesis, no reproduction yet
    REPRODUCED = "REPRODUCED"  # failing evidence exists, not independently verified
    NOT_REPRODUCED = "NOT_REPRODUCED"  # reproduction attempted and the symptom did not occur
    CONFIRMED = "CONFIRMED"  # independently verified with evidence
    REJECTED = "REJECTED"  # verification showed the claim is wrong
    INCONCLUSIVE = "INCONCLUSIVE"  # evidence is mixed (e.g. flaky) or insufficient


class Verdict(enum.StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class Decision(enum.StrEnum):
    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCK = "BLOCK"


DECISION_RANK = {Decision.PASS: 0, Decision.REVIEW_REQUIRED: 1, Decision.BLOCK: 2}


class RequirementStatus(enum.StrEnum):
    STATED = "stated"  # explicitly written in a requirement source
    INFERRED = "inferred"  # derived from code/tests behaviour; needs confirmation
    AMBIGUOUS = "ambiguous"  # stated but not testable as written
    CONFLICTING = "conflicting"  # sources disagree


class TestOrigin(enum.StrEnum):

    __test__ = False  # not a pytest test class
    EXISTING = "existing"  # already in the project
    NEW = "new"  # written during this QA run
    PROPOSED = "proposed"  # designed but not implemented


class ArtifactKind(enum.StrEnum):
    LOG = "log"
    JUNIT = "junit"
    REPORT = "report"
    SCREENSHOT = "screenshot"
    TRACE = "trace"
    VIDEO = "video"
    COVERAGE = "coverage"
    DIFF = "diff"
    DATA = "data"
    OTHER = "other"


class FactKind(enum.StrEnum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    RUNTIME = "runtime"
    TEST_FRAMEWORK = "test-framework"
    CI = "ci"
    API_CONTRACT = "api-contract"
    DATA_STORE = "data-store"
    AUTH = "auth"
    INTEGRATION = "integration"
    AI_COMPONENT = "ai-component"
    DOCUMENTATION = "documentation"
    INFRASTRUCTURE = "infrastructure"
    SECURITY_TOOLING = "security-tooling"
    OTHER = "other"


def risk_level(score: int) -> Severity:
    """Documented risk bands (docs/risk-model.md); shared by qast risk and record validation."""
    if score >= 20:
        return Severity.CRITICAL
    if score >= 12:
        return Severity.HIGH
    if score >= 6:
        return Severity.MEDIUM
    return Severity.LOW


# ------------------------------------------------------------------ shared pieces


@dataclass
class SourceRef:
    """A pointer into the project: file path relative to the project root."""

    path: str
    line: int | None = None
    symbol: str | None = None
    note: str | None = None


@dataclass
class Fact:
    """A single confidence-tagged statement about the project."""

    kind: FactKind
    name: str
    basis: Basis
    confidence: Confidence
    detail: str | None = None
    evidence: list[SourceRef] = field(default_factory=list)


@dataclass
class Assumption:
    statement: str
    impact_if_wrong: str | None = None


# ------------------------------------------------------------------ ProjectProfile


@dataclass
class LanguageStat:
    name: str
    files: int
    basis: Basis = Basis.OBSERVED


@dataclass
class Component:
    name: str
    path: str
    kind: str = field(doc="e.g. package, service, frontend, tests, infra, docs")
    files: int = 0


@dataclass
class TestSuiteInfo:

    __test__ = False  # not a pytest test class
    framework: str
    paths: list[str]
    test_files: int
    suggested_command: list[str] = field(default_factory=list, doc="argv for qast exec, not a shell string")
    basis: Basis = Basis.OBSERVED
    confidence: Confidence = Confidence.MEDIUM


@dataclass
class GitInfo:
    is_repo: bool
    head: str | None = None
    branch: str | None = None
    dirty: bool | None = None


@dataclass
class ProjectProfile:
    """Confidence-tagged description of the project under test (Phase A output)."""

    schema_version: str
    generated_at: str
    project_name: str
    git: GitInfo
    languages: list[LanguageStat]
    components: list[Component]
    test_suites: list[TestSuiteInfo]
    facts: list[Fact]
    unknowns: list[str] = field(default_factory=list, doc="Questions discovery could not answer")
    files_scanned: int = 0
    truncated: bool = False


# --------------------------------------------------------- requirements & invariants


@dataclass
class Requirement:
    id: str
    title: str
    status: RequirementStatus
    basis: Basis
    description: str | None = None
    acceptance_criteria: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    priority: Severity = Severity.MEDIUM
    open_questions: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class BusinessInvariant:
    """A property that must always hold, with an executable oracle."""

    id: str
    statement: str
    criticality: Severity
    oracle: str = field(doc="How a test observes whether the invariant holds")
    basis: Basis = Basis.INFERRED
    components: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)

    def _validate(self) -> str | None:
        if not self.oracle.strip():
            return "invariant oracle must not be empty"
        return None


@dataclass
class RequirementSet:
    """Container written to requirements.json (Phase B output)."""

    requirements: list[Requirement]
    invariants: list[BusinessInvariant] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)


# ------------------------------------------------------------------ risk & planning


@dataclass
class RiskFactor:
    name: str
    value: int = field(doc="1 (low) .. 5 (high)")
    rationale: str
    basis: Basis = Basis.INFERRED


@dataclass
class RiskAssessment:
    """Probability x impact risk for an area. Score = probability * impact (1..25)."""

    id: str
    area: str
    description: str
    probability: int
    impact: int
    score: int
    level: Severity
    factors: list[RiskFactor] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    existing_coverage: str | None = None
    related_requirements: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def _validate(self) -> str | None:
        if not (1 <= self.probability <= 5 and 1 <= self.impact <= 5):
            return "probability and impact must be in 1..5"
        if self.score != self.probability * self.impact:
            return "score must equal probability * impact"
        band = risk_level(self.score)
        if self.level != band:
            return f"level must be '{band.value}' for score {self.score} (bands: >=20 critical, 12-19 high, 6-11 medium, <=5 low)"
        return None


@dataclass
class RiskRegister:
    risks: list[RiskAssessment]
    method: str = "probability x impact, factors documented per risk (docs/risk-model.md)"


@dataclass
class TestCase:

    __test__ = False  # not a pytest test class
    id: str
    title: str
    level: str = field(doc="unit|integration|api|e2e|contract|security|performance|accessibility|reliability|ai-eval|exploratory")
    technique: str = field(doc="equivalence|boundary|decision-table|state-transition|pairwise|property|negative|metamorphic|invariant|regression|smoke|exploratory")
    oracle: str = field(doc="Expected observable outcome. Required.")
    origin: TestOrigin = TestOrigin.PROPOSED
    test_ref: str | None = field(default=None, doc="Executable identifier, e.g. tests/test_x.py::test_y")
    groups: list[str] = field(default_factory=list, doc="Policy groups, e.g. existing-suite, critical-journeys, contract")
    priority: Severity = Severity.MEDIUM
    preconditions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    requirement_ids: list[str] = field(default_factory=list)
    invariant_ids: list[str] = field(default_factory=list)
    risk_ids: list[str] = field(default_factory=list)

    def _validate(self) -> str | None:
        if not self.oracle.strip():
            return f"test case {self.id} has no oracle (expected observable outcome)"
        return None


@dataclass
class OutOfScope:
    item: str
    reason: str


@dataclass
class TestPlan:
    """Prioritized, executable plan (Phase E output)."""

    __test__ = False  # not a pytest test class

    id: str
    scope: str
    strategy_summary: str
    test_cases: list[TestCase]
    out_of_scope: list[OutOfScope] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    entry_criteria: list[str] = field(default_factory=list)
    exit_criteria: list[str] = field(default_factory=list)
    specialists: list[str] = field(default_factory=list, doc="Agents/skills selected in Phase F, with reasons in strategy_summary")


# ------------------------------------------------------------------ execution


@dataclass
class TestResult:
    """Outcome of one test within an execution."""

    __test__ = False  # not a pytest test class

    id: str = field(doc="Deterministic: hash of adapter + identifier")
    identifier: str
    status: Status
    name: str | None = None
    duration_s: float | None = None
    message: str | None = None
    file: str | None = None
    line: int | None = None
    groups: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)


@dataclass
class EnvironmentInfo:
    platform: str
    python: str
    hostname_hash: str = field(doc="sha256 prefix of hostname; raw hostname is never stored")
    tool_versions: dict[str, str] = field(default_factory=dict)
    ci: bool = False
    git_head: str | None = None
    git_dirty: bool | None = None


@dataclass
class TestExecution:
    """One adapter invocation and its normalized results."""

    __test__ = False  # not a pytest test class

    id: str
    run_id: str
    adapter: str
    status: Status
    started_at: str
    finished_at: str
    duration_s: float
    command: list[str]
    cwd: str
    exit_code: int | None
    timed_out: bool
    counts: dict[str, int]
    results: list[TestResult]
    environment: EnvironmentInfo
    groups: list[str] = field(default_factory=list)
    label: str | None = None
    status_reason: str | None = field(default=None, doc="Why the overall status was assigned (always set for BLOCKED/ERROR/NOT_RUN/INCONCLUSIVE)")
    artifact_ids: list[str] = field(default_factory=list)
    attempt: int = 1
    reproduction_of: str | None = field(default=None, doc="Test identifier this execution re-ran for reproduction")
    actor: str | None = field(default=None, doc="Agent or person that ran it (qast exec --actor); verification requires the verifier's own executions")


@dataclass
class EvidenceArtifact:
    id: str = field(doc="ev-<sha256 prefix>; content addressed")
    kind: ArtifactKind
    path: str = field(doc="Relative to the run directory")
    sha256: str
    size_bytes: int
    media_type: str
    created_at: str
    redacted: bool
    redactions: int = 0
    execution_id: str | None = None
    description: str | None = None


# ------------------------------------------------------------------ findings


@dataclass
class Hypothesis:
    statement: str
    confidence: Confidence
    confirmed: bool = field(default=False, doc="True only when backed by evidence_ids")
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class Reproduction:
    attempts: int
    failures: int
    execution_ids: list[str]
    classification: str = field(doc="consistent | intermittent | not-reproduced | blocked")


@dataclass
class DefectFinding:
    id: str
    title: str
    category: Category
    severity: Severity
    summary: str
    expected: str
    actual: str
    reproduction_steps: list[str]
    reported_by: str
    created_at: str
    evidence_ids: list[str] = field(default_factory=list)
    execution_ids: list[str] = field(default_factory=list)
    test_identifiers: list[str] = field(default_factory=list)
    affected: list[SourceRef] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    environment_notes: str | None = None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    requirement_ids: list[str] = field(default_factory=list)
    invariant_ids: list[str] = field(default_factory=list)
    reproduction: Reproduction | None = None
    regression_test: str | None = None

    def _validate(self) -> str | None:
        if not self.reproduction_steps:
            return "a finding needs reproduction_steps (exact steps, even for suspected defects)"
        if not (self.expected.strip() and self.actual.strip()):
            return "a finding needs both expected and actual behaviour"
        for h in self.hypotheses:
            if h.confirmed and not h.evidence_ids:
                return "a hypothesis cannot be confirmed without evidence_ids"
        return None


@dataclass
class VerificationCheck:
    check: str
    passed: bool
    detail: str | None = None


@dataclass
class VerificationResult:
    id: str
    finding_id: str
    verdict: Verdict
    method: str = field(doc="independent-rerun | alternate-oracle | code-inspection | manual")
    verifier: str
    rationale: str
    created_at: str
    evidence_ids: list[str] = field(default_factory=list)
    execution_ids: list[str] = field(default_factory=list)
    test_identifiers: list[str] = field(default_factory=list, doc="Tests the verifier ran (alternate oracle)")
    checks: list[VerificationCheck] = field(default_factory=list, doc="Machine checks run by qast verify")


# ------------------------------------------------------------------ coverage & decision


@dataclass
class MeasuredMetric:
    """A coverage/quality number measured by a tool. Never estimated."""

    metric: str
    value: float
    unit: str
    tool: str
    artifact_id: str | None = None


@dataclass
class TraceRow:
    item_id: str = field(doc="Requirement, invariant or risk id")
    test_case_ids: list[str]
    statuses: list[Status]


@dataclass
class UntestedArea:
    area: str
    reason: str
    risk: Severity = Severity.MEDIUM


@dataclass
class CoverageAssessment:
    measured: list[MeasuredMetric]
    traceability: list[TraceRow]
    untested: list[UntestedArea]
    status_counts: dict[str, int]
    basis: str = "Counts derived from recorded executions; percentages only from coverage tools."


@dataclass
class RuleOutcome:
    rule_id: str
    outcome: Decision
    triggered: bool
    reason: str
    refs: list[str] = field(default_factory=list)


@dataclass
class PolicyRef:
    name: str
    version: str
    sha256: str
    path: str


@dataclass
class ReleaseDecision:
    decision: Decision
    policy: PolicyRef
    rules: list[RuleOutcome]
    evaluated_at: str
    inputs_digest: str = field(doc="sha256 over the records the decision was computed from")
    summary: str


# ------------------------------------------------------------------ run & report


@dataclass
class RunInfo:
    run_id: str
    mode: str = field(doc="full-audit | review-pr | test-feature | test-api | test-e2e | security-review | eval-ai | explore | verify-bug | regression | release-check | improve-suite | adhoc")
    created_at: str
    scope: str
    base_ref: str | None = None
    head_ref: str | None = None
    project_name: str | None = None
    environment: EnvironmentInfo | None = None


@dataclass
class FindingView:
    """A finding with its derived (effective) status, as presented in reports."""

    finding: DefectFinding
    effective_status: FindingStatus
    status_basis: str
    evidence_valid: bool
    integrity_problems: list[str] = field(default_factory=list)


@dataclass
class QAReport:
    schema_version: str
    run: RunInfo
    generated_at: str
    decision: ReleaseDecision | None
    executions: list[TestExecution]
    findings: list[FindingView]
    verifications: list[VerificationResult]
    coverage: CoverageAssessment
    artifacts: list[EvidenceArtifact]
    limitations: list[str]
    phases: dict[str, str] = field(default_factory=dict)
    plan: TestPlan | None = None
    risks: list[RiskAssessment] = field(default_factory=list)
    requirements: RequirementSet | None = None
    profile_summary: dict[str, Any] = field(default_factory=dict)
    integrity_warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list, doc="Decision and assumption notes recorded with qast run note")


# Models exported as standalone schemas (name -> class)
EXPORTED_MODELS: dict[str, type] = {
    "ProjectProfile": ProjectProfile,
    "Requirement": Requirement,
    "BusinessInvariant": BusinessInvariant,
    "RequirementSet": RequirementSet,
    "RiskAssessment": RiskAssessment,
    "RiskRegister": RiskRegister,
    "TestPlan": TestPlan,
    "TestCase": TestCase,
    "TestExecution": TestExecution,
    "EvidenceArtifact": EvidenceArtifact,
    "DefectFinding": DefectFinding,
    "VerificationResult": VerificationResult,
    "CoverageAssessment": CoverageAssessment,
    "ReleaseDecision": ReleaseDecision,
    "QAReport": QAReport,
    "RunInfo": RunInfo,
}
