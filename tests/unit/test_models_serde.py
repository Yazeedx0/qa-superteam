import json

import jsonschema
import pytest

from qa_superteam import models as m
from qa_superteam.serde import SchemaError, from_dict, json_schema, to_dict
from qa_superteam.templates import TEMPLATES


def test_status_has_seven_distinct_values():
    assert [s.value for s in m.Status] == ["PASSED", "FAILED", "ERROR", "SKIPPED", "BLOCKED", "NOT_RUN", "INCONCLUSIVE"]


def test_roundtrip_preserves_data():
    tc = m.TestCase(id="TC-1", title="t", level="api", technique="boundary", oracle="returns 422", groups=["contract"])
    data = to_dict(tc)
    assert data["origin"] == "proposed"
    assert from_dict(m.TestCase, data) == tc


def test_unknown_fields_are_rejected_with_path():
    with pytest.raises(SchemaError) as e:
        from_dict(m.TestCase, {"id": "x", "title": "t", "level": "api", "technique": "b", "oracle": "o", "oracel": "typo"})
    assert "oracel" in str(e.value)


def test_test_case_requires_an_oracle():
    with pytest.raises(SchemaError, match="no oracle"):
        from_dict(m.TestCase, {"id": "x", "title": "t", "level": "api", "technique": "b", "oracle": "  "})


def test_enum_values_validated():
    with pytest.raises(SchemaError, match="not one of"):
        from_dict(m.Requirement, {"id": "R", "title": "t", "status": "maybe", "basis": "observed"})


def test_bool_is_not_an_int():
    with pytest.raises(SchemaError, match="expected integer"):
        from_dict(m.RiskFactor, {"name": "x", "value": True, "rationale": "r"})


def test_risk_score_must_equal_probability_times_impact():
    base = {"id": "R", "area": "a", "description": "d", "probability": 3, "impact": 4, "level": "high"}
    assert from_dict(m.RiskAssessment, {**base, "score": 12}).score == 12
    with pytest.raises(SchemaError, match="score must equal"):
        from_dict(m.RiskAssessment, {**base, "score": 20})


def test_finding_requires_repro_steps_and_expected_actual():
    t = dict(TEMPLATES["DefectFinding"], id="F-1", created_at="2026-01-01T00:00:00Z")
    from_dict(m.DefectFinding, t)
    with pytest.raises(SchemaError, match="reproduction_steps"):
        from_dict(m.DefectFinding, {**t, "reproduction_steps": []})
    with pytest.raises(SchemaError, match="expected and actual"):
        from_dict(m.DefectFinding, {**t, "actual": " "})


def test_confirmed_hypothesis_needs_evidence():
    t = dict(TEMPLATES["DefectFinding"], id="F-1", created_at="2026-01-01T00:00:00Z")
    t["hypotheses"] = [{"statement": "x", "confidence": "high", "confirmed": True, "evidence_ids": []}]
    with pytest.raises(SchemaError, match="hypothesis cannot be confirmed"):
        from_dict(m.DefectFinding, t)


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_templates_validate_against_models_and_schemas(name):
    cls = m.EXPORTED_MODELS[name]
    data = dict(TEMPLATES[name])
    if name == "DefectFinding":
        data.update(id="F-1", created_at="2026-01-01T00:00:00Z")
    if name == "TestPlan":
        data["id"] = "TP-1"
    obj = from_dict(cls, data)
    jsonschema.validate(to_dict(obj), json_schema(cls))


@pytest.mark.parametrize("name", sorted(m.EXPORTED_MODELS))
def test_generated_schemas_are_valid_2020_12(name):
    schema = json_schema(m.EXPORTED_MODELS[name])
    jsonschema.Draft202012Validator.check_schema(schema)
    json.dumps(schema)


def test_committed_schemas_match_models():
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    out = subprocess.run([sys.executable, str(root / "scripts" / "gen_schemas.py"), "--check"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout
