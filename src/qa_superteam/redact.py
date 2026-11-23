"""Evidence redaction.

Every text artifact, command line and failure message passes through
:func:`redact_text` before it is written to the run directory.  The goal is to keep
secrets, credentials, session tokens and personal data out of exported reports.

Redaction is pattern based and therefore best-effort: it is a safety net, not a
guarantee.  docs/security.md documents the limits.  Projects can add patterns in
``[redaction] extra_patterns`` of ``.qa-superteam/config.toml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

REDACTED = "[REDACTED:{label}]"


@dataclass(frozen=True)
class Rule:
    label: str
    pattern: re.Pattern[str]
    group: int = 0  # which capture group to replace (0 = whole match)


def _r(label: str, pattern: str, group: int = 0, flags: int = 0) -> Rule:
    return Rule(label, re.compile(pattern, flags), group)


# Order matters: specific token formats first, generic key=value last.
DEFAULT_RULES: tuple[Rule, ...] = (
    _r("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    _r("anthropic-key", r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    _r("openai-key", r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}"),
    _r("github-token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"),
    _r("aws-access-key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    _r("slack-token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    _r("stripe-key", r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    _r("google-api-key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    _r("jwt", r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    _r("bearer-token", r"(?i)\b(bearer\s+)([A-Za-z0-9_\-\.=+/]{12,})", group=2),
    _r("basic-auth", r"(?i)\b(basic\s+)([A-Za-z0-9+/=]{12,})", group=2),
    _r("url-credentials", r"(?i)\b([a-z][a-z0-9+\-.]*://[^\s:/@]+:)([^\s@/]+)(@)", group=2),
    _r(
        "cookie",
        r"(?i)\b((?:set-)?cookie\s*[:=]\s*)([^\r\n]+)",
        group=2,
    ),
    _r(
        "secret-assignment",
        r"(?i)\b((?:[a-z0-9_]*?(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|session[_-]?id|auth[_-]?token|client[_-]?secret|credential)s?)"
        r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',;&}]{4,})",
        group=2,
    ),
    _r("email", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    _r("card-number", r"\b(?:\d[ -]?){13,19}\b"),
)


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


@dataclass
class Redactor:
    rules: tuple[Rule, ...] = DEFAULT_RULES
    redact_emails: bool = True
    allow_emails: tuple[str, ...] = ("example.com", "example.org", "example.net", "test.com")
    count: int = 0
    by_label: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_config(cls, extra_patterns: list[str] | None = None, redact_emails: bool = True) -> "Redactor":
        rules = list(DEFAULT_RULES)
        for i, pat in enumerate(extra_patterns or []):
            rules.insert(0, _r(f"custom-{i + 1}", pat))
        return cls(rules=tuple(rules), redact_emails=redact_emails)

    def redact(self, text: str) -> str:
        if not text:
            return text
        for rule in self.rules:
            if rule.label == "email" and not self.redact_emails:
                continue
            text = rule.pattern.sub(lambda m, r=rule: self._replace(m, r), text)
        return text

    def _replace(self, m: re.Match[str], rule: Rule) -> str:
        whole = m.group(0)
        if rule.label == "email":
            domain = whole.rsplit("@", 1)[-1].lower()
            if any(domain == d or domain.endswith("." + d) for d in self.allow_emails):
                return whole  # synthetic test fixtures are not personal data
        if rule.label == "card-number":
            digits = re.sub(r"\D", "", whole)
            if not (13 <= len(digits) <= 19 and _luhn_ok(digits)):
                return whole
        if "[REDACTED:" in whole:
            return whole
        self.count += 1
        self.by_label[rule.label] = self.by_label.get(rule.label, 0) + 1
        token = REDACTED.format(label=rule.label)
        if rule.group == 0:
            return token
        start, end = m.span(rule.group)
        base = m.start(0)
        return whole[: start - base] + token + whole[end - base :]


def redact_text(text: str, redactor: Redactor | None = None) -> tuple[str, int]:
    """Convenience wrapper returning (redacted_text, number_of_redactions)."""
    r = redactor or Redactor()
    before = r.count
    out = r.redact(text)
    return out, r.count - before


SENSITIVE_ENV_RE = re.compile(r"(?i)(secret|token|password|passwd|api[_-]?key|private|credential|session|cookie|auth)")


def redact_argv(argv: list[str], redactor: Redactor | None = None) -> list[str]:
    r = redactor or Redactor()
    out = []
    for a in argv:
        out.append(r.redact(a))
    return out
