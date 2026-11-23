"""Fill-in templates printed by ``qast schema <Model> --template``.

Agents write these JSON shapes and submit them with ``qast record`` / ``qast finding add``;
the CLI validates them strictly and assigns ids and timestamps. The examples use a
neutral, fictional document-sharing service.
"""

TEMPLATES = {
    "DefectFinding": {
        "title": "Viewer role can delete a shared document",
        "category": "security",
        "severity": "high",
        "summary": "DELETE /documents/{id} checks that the caller has access to the document but not that the role permits deletion.",
        "expected": "403 for a caller whose role on the document is 'viewer' (docs/PERMISSIONS.md §2)",
        "actual": "204 and the document is removed for all collaborators",
        "reproduction_steps": [
            "Owner creates document D and shares it with user V as 'viewer'",
            "As V, DELETE /documents/<D id>",
            "Observe 204; GET /documents/<D id> as owner returns 404",
        ],
        "reported_by": "qa-superteam:backend-qa-engineer",
        "test_identifiers": ["tests/qa/test_permissions.py::test_viewer_cannot_delete"],
        "execution_ids": ["ex-<id printed by qast exec>"],
        "evidence_ids": ["ev-<artifact id printed by qast exec>"],
        "affected": [{"path": "app/documents/routes.py", "symbol": "delete_document"}],
        "inputs": {"role": "viewer"},
        "environment_notes": "in-process TestClient, temporary SQLite database",
        "hypotheses": [{"statement": "The handler reuses the read-access check for deletion", "confidence": "medium", "confirmed": False, "evidence_ids": []}],
        "requirement_ids": ["REQ-PERM-2"],
        "invariant_ids": [],
    },
    "TestPlan": {
        "scope": "PR #87: document version history",
        "strategy_summary": "Risk-based: version restore (R-01, high) gets state-transition and permission tests; rendering unchanged -> existing suite only. Specialists: backend-qa-engineer.",
        "test_cases": [
            {
                "id": "TC-01",
                "title": "Restoring a version never loses the current content",
                "level": "api",
                "technique": "state-transition",
                "oracle": "After restore of v2, version history contains the pre-restore content as a new version",
                "origin": "new",
                "test_ref": "tests/qa/test_versions.py::test_restore_keeps_current_as_version",
                "groups": ["critical-journeys"],
                "priority": "high",
                "steps": ["create doc", "edit twice", "restore v1", "list versions"],
                "inputs": {"edits": 2},
                "requirement_ids": ["REQ-VER-3"],
                "invariant_ids": ["INV-1"],
                "risk_ids": ["R-01"],
            }
        ],
        "out_of_scope": [{"item": "load behaviour", "reason": "no authorized performance environment"}],
        "assumptions": [{"statement": "Version numbers are per document", "impact_if_wrong": "restore tests target the wrong version"}],
        "entry_criteria": ["existing suite runs"],
        "exit_criteria": ["all high/critical cases executed", "findings verified"],
        "specialists": ["qa-superteam:backend-qa-engineer"],
    },
    "RequirementSet": {
        "requirements": [
            {
                "id": "REQ-VER-3",
                "title": "Restoring a version keeps the current content as a new version",
                "status": "stated",
                "basis": "observed",
                "description": "Restore never destroys content; it appends.",
                "acceptance_criteria": ["Given versions v1..vn, restoring vk creates v(n+1) with vk content and keeps vn"],
                "sources": [{"path": "docs/VERSIONING.md", "line": 12}],
                "priority": "high",
                "open_questions": [],
            }
        ],
        "invariants": [
            {
                "id": "INV-1",
                "statement": "The number of versions of a document never decreases",
                "criticality": "high",
                "oracle": "After each API call in a test, GET /documents/{id}/versions returns at least as many items as before",
                "basis": "observed",
                "components": ["app/documents/versions.py"],
                "sources": [{"path": "docs/VERSIONING.md"}],
            }
        ],
        "ambiguities": ["'Old versions may be pruned' gives no retention period or trigger"],
        "assumptions": [{"statement": "Restores are not rate-limited", "impact_if_wrong": "repeated-restore tests may be throttled"}],
    },
    "RiskRegister": {
        "risks": [
            {
                "id": "R-01",
                "area": "document versions",
                "description": "Restore refactor could drop the current version",
                "probability": 3,
                "impact": 5,
                "score": 15,
                "level": "high",
                "factors": [{"name": "change size", "value": 3, "rationale": "140 lines in versions.py", "basis": "observed"}],
                "paths": ["app/documents/versions.py"],
                "existing_coverage": "happy-path restore test only",
                "related_requirements": ["REQ-VER-3"],
                "assumptions": [],
            }
        ],
        "method": "probability x impact, factors documented per risk (docs/risk-model.md)",
    },
}
