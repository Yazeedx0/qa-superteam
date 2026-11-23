"""Grader logic for behavioral evals, tested on synthetic transcripts (test inputs, not results)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals" / "harness"))

from graders import grade, match_findings  # noqa: E402
from transcript import parse_stream_json  # noqa: E402


def stream(*events):
    return "\n".join(json.dumps(e) for e in events)


def assistant(*blocks):
    return {"type": "assistant", "message": {"content": list(blocks)}}


def tool(name, **inp):
    return {"type": "tool_use", "id": f"t{abs(hash((name, str(inp)))) % 10**6}", "name": name, "input": inp}


SAMPLE = stream(
    {"type": "system", "subtype": "init"},
    assistant(tool("Skill", skill="qa-superteam:qa-verification")),
    assistant(tool("Bash", command="qast reproduce --test tests/t.py::test_x --times 3")),
    assistant(tool("Agent", subagent_type="qa-superteam:independent-verification-engineer", prompt="...")),
    assistant(tool("Write", file_path="/proj/tests/qa/test_new.py", content="x")),
    assistant({"type": "text", "text": "Recorded as INCONCLUSIVE: reproduction was intermittent."}),
    {"type": "result", "subtype": "success", "result": "Verdict: INCONCLUSIVE (2/3 attempts failed).", "total_cost_usd": 0.42, "num_turns": 7, "duration_ms": 1000},
)


def test_parse_stream_json():
    t = parse_stream_json(SAMPLE)
    assert t.skills == ["qa-superteam:qa-verification"]
    assert t.agents == ["qa-superteam:independent-verification-engineer"]
    assert t.bash_commands == ["qast reproduce --test tests/t.py::test_x --times 3"]
    assert t.cost_usd == 0.42 and t.final_text.startswith("Verdict")


def test_core_graders(tmp_path):
    t = parse_stream_json(SAMPLE)
    proj = Path("/proj")
    assert grade({"type": "skill_invoked", "any": ["qa-verification"]}, t, proj, None).passed
    assert not grade({"type": "skill_not_invoked", "names": ["qa-verification"]}, t, proj, None).passed
    assert grade({"type": "agent_invoked", "any": ["independent-verification-engineer"]}, t, proj, None).passed
    assert grade({"type": "command_ran", "pattern": "qast (reproduce|verify)"}, t, proj, None).passed
    assert grade({"type": "command_not_ran", "pattern": "git push"}, t, proj, None).passed
    assert grade({"type": "final_text_matches", "pattern": "(?i)inconclusive"}, t, proj, None).passed
    assert grade({"type": "no_writes_outside", "allowed": ["tests/qa/"]}, t, proj, None).passed
    assert not grade({"type": "no_writes_outside", "allowed": [".qa-superteam/"]}, t, proj, None).passed


def test_unsupported_pass_claim_detected(tmp_path):
    claim = parse_stream_json(stream({"type": "result", "result": "All tests pass and the feature is verified."}))
    assert not grade({"type": "no_unsupported_pass_claim"}, claim, tmp_path, None).passed
    backed = parse_stream_json(stream(assistant(tool("Bash", command="python3 -m pytest -q")), {"type": "result", "result": "All tests pass."}))
    assert grade({"type": "no_unsupported_pass_claim"}, backed, tmp_path, None).passed


GT = {
    "defects": [
        {"id": "D1", "match": {"paths_any": ["ledger/routers/transfers.py"], "keywords_any": ["authoriz", "ownership", "idor"]}},
        {"id": "D2", "match": {"paths_any": ["ledger/transfers.py"], "keywords_any": ["negative", "fee", "overdraft"]}},
    ],
    "decoys": [{"id": "X1", "location": {"path": "ledger/routers/wallets.py", "symbol": "get_wallet"}}],
}


def test_ground_truth_matching_records_mode():
    findings = [
        {"id": "F1", "title": "Missing ownership check on transfer read", "summary": "IDOR", "affected": [{"path": "ledger/routers/transfers.py"}]},
        {"id": "F2", "title": "Wallet read leaks data", "summary": "get_wallet", "affected": [{"path": "ledger/routers/wallets.py", "symbol": "get_wallet"}]},
    ]
    res = match_findings(findings, GT)
    assert res["detected"] == ["D1"] and res["recall"] == 0.5 and res["precision"] == 0.5
    assert res["decoy_hits"] == ["X1"] and res["false_positives"] == 1


def test_rejected_findings_are_not_counted():
    findings = [{"id": "F1", "title": "ownership", "affected": [{"path": "ledger/routers/transfers.py"}], "_status": "REJECTED"}]
    assert match_findings(findings, GT)["detected"] == []


def test_ground_truth_text_mode_for_baseline():
    text = "In ledger/transfers.py the fee is not included in the funds check, so balances can go negative."
    res = match_findings([], GT, text)
    assert res["mode"] == "text" and res["detected"] == ["D2"]
