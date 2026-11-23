"""Pytest plugin loaded by the qast pytest adapter (``-p qa_superteam.pytest_reporter``).

Writes one JSON line per test to ``$QAST_PYTEST_REPORT`` with the exact node id and a
precise outcome, distinguishing assertion failures (FAILED) from setup/teardown
crashes (ERROR), and recording skip/xfail reasons.  Stdlib only.
"""

from __future__ import annotations

import json
import os

_PATH = os.environ.get("QAST_PYTEST_REPORT")
_state: dict[str, dict] = {}
_MAX_MSG = 4000


def _emit(rec: dict) -> None:
    if not _PATH:
        return
    with open(_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _msg(report) -> str | None:
    text = getattr(report, "longreprtext", None) or ""
    if report.skipped and isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
        text = str(report.longrepr[2])
    if not text:
        return None
    return text if len(text) <= _MAX_MSG else text[: _MAX_MSG // 2] + "\n...\n" + text[-_MAX_MSG // 2 :]


def pytest_runtest_logreport(report) -> None:  # noqa: D401 - pytest hook
    st = _state.setdefault(
        report.nodeid,
        {"nodeid": report.nodeid, "status": None, "duration_s": 0.0, "message": None, "location": list(report.location)},
    )
    st["duration_s"] += float(getattr(report, "duration", 0.0) or 0.0)
    wasxfail = getattr(report, "wasxfail", None)
    if report.when == "setup":
        if report.failed:
            st["status"], st["message"] = "ERROR", _msg(report)
        elif report.skipped:
            st["status"], st["message"] = "SKIPPED", ("xfail: " + str(wasxfail)) if wasxfail is not None else _msg(report)
    elif report.when == "call":
        if report.passed:
            st["status"] = "PASSED"
            if wasxfail is not None:
                st["message"] = "XPASS (expected to fail but passed): " + str(wasxfail)
        elif report.failed:
            st["status"], st["message"] = "FAILED", _msg(report)
        elif report.skipped:
            if wasxfail is not None:
                st["status"], st["message"] = "SKIPPED", "xfail: " + str(wasxfail)
            else:
                st["status"], st["message"] = "SKIPPED", _msg(report)
    elif report.when == "teardown":
        if report.failed and st["status"] in (None, "PASSED", "SKIPPED"):
            st["status"], st["message"] = "ERROR", "teardown failed: " + (_msg(report) or "")
        if st["status"] is None:
            st["status"] = "ERROR"
            st["message"] = st["message"] or "no outcome recorded"
        st["duration_s"] = round(st["duration_s"], 4)
        _emit(_state.pop(report.nodeid))


def pytest_collectreport(report) -> None:
    if report.failed:
        _emit(
            {
                "nodeid": report.nodeid or "<collection>",
                "status": "ERROR",
                "duration_s": 0.0,
                "message": "collection error: " + (_msg(report) or ""),
                "location": [report.nodeid.split("::")[0] if report.nodeid else "", None, ""],
            }
        )
