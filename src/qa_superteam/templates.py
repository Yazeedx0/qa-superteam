"""Fill-in templates printed by ``qast schema <Model> --template``.

Agents write these JSON shapes and submit them with ``qast record`` / ``qast finding add``;
the CLI validates them strictly and assigns ids and timestamps.
"""

TEMPLATES = {
    "DefectFinding": {
        "title": "Any authenticated user can read another user's transfer",
        "category": "security",
        "severity": "critical",
        "summary": "GET /transfers/{id} does not check that the caller is a party to the transfer.",
        "expected": "403 or 404 for a transfer the caller neither sent nor received (REQUIREMENTS.md §3.4)",
        "actual": "200 with the full transfer body (amount, memo, wallet ids)",
        "reproduction_steps": [
            "Register users A and B; A deposits 1000 and transfers 100 to C",
            "As B, GET /transfers/<A's transfer id>",
            "Observe HTTP 200 and A's transfer data",
        ],
        "reported_by": "qa-superteam:backend-qa-engineer",
        "test_identifiers": ["tests/qa/test_authz.py::test_non_party_cannot_read_transfer"],
        "execution_ids": ["ex-<id printed by qast exec>"],
        "evidence_ids": ["ev-<artifact id printed by qast exec>"],
        "affected": [{"path": "app/routes/transfers.py", "symbol": "get_transfer"}],
        "inputs": {"transfer_id": 1},
        "environment_notes": "local TestClient, SQLite in tmp dir",
        "hypotheses": [{"statement": "Handler loads by id without filtering on sender/recipient", "confidence": "medium", "confirmed": False, "evidence_ids": []}],
        "requirement_ids": ["REQ-3.4"],
        "invariant_ids": [],
    },
    "TestPlan": {
        "scope": "PR #42: transfer fee change",
        "strategy_summary": "Risk-based: transfers (R-01, critical) get invariant + boundary tests; auth unchanged -> existing suite only. Specialists: backend-qa-engineer.",
        "test_cases": [
            {
                "id": "TC-01",
                "title": "Balance never negative when fee pushes debit over balance",
                "level": "api",
                "technique": "boundary",
                "oracle": "Transfer of 1000 with balance 1000 is rejected with 422 and balance stays 1000",
                "origin": "new",
                "test_ref": "tests/qa/test_invariants.py::test_fee_cannot_overdraw",
                "groups": ["critical-journeys"],
                "priority": "critical",
                "steps": ["deposit 1000", "transfer 1000", "read balance"],
                "inputs": {"balance": 1000, "amount": 1000},
                "requirement_ids": ["REQ-2.1"],
                "invariant_ids": ["INV-1"],
                "risk_ids": ["R-01"],
            }
        ],
        "out_of_scope": [{"item": "load behaviour", "reason": "no authorized performance environment"}],
        "assumptions": [{"statement": "Fee is 1% rounded up per REQUIREMENTS.md", "impact_if_wrong": "boundary values shift"}],
        "entry_criteria": ["existing suite runs"],
        "exit_criteria": ["all critical cases executed", "findings verified"],
        "specialists": ["qa-superteam:backend-qa-engineer"],
    },
    "RequirementSet": {
        "requirements": [
            {
                "id": "REQ-2.1",
                "title": "Balances never go negative",
                "status": "stated",
                "basis": "observed",
                "description": "A transfer is rejected if amount + fee exceeds the balance.",
                "acceptance_criteria": ["Given balance B, a transfer with amount+fee > B returns 422 and changes nothing"],
                "sources": [{"path": "docs/REQUIREMENTS.md", "line": 12}],
                "priority": "critical",
                "open_questions": [],
            }
        ],
        "invariants": [
            {
                "id": "INV-1",
                "statement": "For every wallet, balance_cents >= 0 after any committed operation",
                "criticality": "critical",
                "oracle": "After each API call in a test, GET /wallets/me shows balance_cents >= 0",
                "basis": "observed",
                "components": ["ledger/transfers.py"],
                "sources": [{"path": "docs/REQUIREMENTS.md"}],
            }
        ],
        "ambiguities": ["'Large transfers may require additional review' has no threshold or behaviour"],
        "assumptions": [{"statement": "Currency is a single implicit currency", "impact_if_wrong": "multi-currency rounding untested"}],
    },
    "RiskRegister": {
        "risks": [
            {
                "id": "R-01",
                "area": "transfers",
                "description": "Fee calculation change could allow overdraft",
                "probability": 4,
                "impact": 5,
                "score": 20,
                "level": "critical",
                "factors": [{"name": "change size", "value": 3, "rationale": "120 lines in transfers.py", "basis": "observed"}],
                "paths": ["app/transfers.py"],
                "existing_coverage": "happy-path transfer test only",
                "related_requirements": ["REQ-2.1"],
                "assumptions": [],
            }
        ],
        "method": "probability x impact, factors documented per risk (docs/risk-model.md)",
    },
}
