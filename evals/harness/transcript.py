"""Parse `claude -p --output-format stream-json --verbose` transcripts into facts graders use."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    is_error: bool = False


@dataclass
class Transcript:
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_text: str = ""
    assistant_text: list[str] = field(default_factory=list)
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    is_error: bool = False
    result_subtype: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def bash_commands(self) -> list[str]:
        return [str(c.input.get("command", "")) for c in self.tool_calls if c.name == "Bash"]

    @property
    def skills(self) -> list[str]:
        out = []
        for c in self.tool_calls:
            if c.name == "Skill":
                s = c.input.get("skill") or c.input.get("command") or c.input.get("name") or ""
                out.append(str(s).lstrip("/"))
        return out

    @property
    def agents(self) -> list[str]:
        return [str(c.input.get("subagent_type", "")) for c in self.tool_calls if c.name in ("Agent", "Task")]

    @property
    def written_paths(self) -> list[str]:
        return [str(c.input.get("file_path") or c.input.get("notebook_path") or "") for c in self.tool_calls if c.name in ("Edit", "Write", "MultiEdit", "NotebookEdit")]

    @property
    def all_text(self) -> str:
        return "\n".join(self.assistant_text + [self.final_text])


def parse_stream_json(text: str) -> Transcript:
    t = Transcript()
    pending: dict[str, ToolCall] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = ev.get("type")
        if typ == "assistant":
            for block in (ev.get("message") or {}).get("content", []) or []:
                if block.get("type") == "tool_use":
                    call = ToolCall(name=block.get("name", ""), input=block.get("input") or {})
                    t.tool_calls.append(call)
                    if block.get("id"):
                        pending[block["id"]] = call
                elif block.get("type") == "text" and block.get("text"):
                    t.assistant_text.append(block["text"])
        elif typ == "user":
            content = (ev.get("message") or {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                        call = pending.get(block.get("tool_use_id", ""))
                        if call:
                            call.is_error = True
        elif typ == "result":
            t.final_text = str(ev.get("result") or "")
            t.cost_usd = ev.get("total_cost_usd")
            t.duration_ms = ev.get("duration_ms")
            t.num_turns = ev.get("num_turns")
            t.is_error = bool(ev.get("is_error"))
            t.result_subtype = ev.get("subtype")
            t.usage = ev.get("usage") or {}
    if not t.final_text and t.assistant_text:
        t.final_text = t.assistant_text[-1]
    return t
