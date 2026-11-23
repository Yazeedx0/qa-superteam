"""Project configuration (``.qa-superteam/config.toml``) and safety permissions.

Defaults are deliberately conservative: read-only, local targets only, no load or
active security testing, no application code modification.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

PLUGIN_ROOT = Path(os.environ.get("QAST_PLUGIN_ROOT") or Path(__file__).resolve().parents[2])
DEFAULT_POLICY = PLUGIN_ROOT / "policies" / "default.toml"
CONFIG_TEMPLATE = PLUGIN_ROOT / "templates" / "config.toml"

LOCAL_TARGETS = ("http://127.0.0.1", "http://localhost", "http://[::1]", "https://127.0.0.1", "https://localhost")


class ConfigError(ValueError):
    pass


@dataclass
class Permissions:
    write_tests: bool = False
    test_dir: str = "tests/qa"
    modify_app_code: bool = False
    authorized_targets: list[str] = field(default_factory=lambda: list(LOCAL_TARGETS))
    allow_load_testing: bool = False
    allow_active_security: bool = False
    allow_fault_injection: bool = False


@dataclass
class Budgets:
    command_timeout_s: int = 900
    max_reproduce_attempts: int = 5
    max_output_bytes: int = 2_000_000
    max_artifact_bytes: int = 50_000_000
    max_scan_files: int = 20_000


@dataclass
class Config:
    project_root: Path
    output_dir: Path
    permissions: Permissions = field(default_factory=Permissions)
    budgets: Budgets = field(default_factory=Budgets)
    policy_path: Path = DEFAULT_POLICY
    critical_paths: list[str] = field(default_factory=list)
    groups: dict[str, list[str]] = field(default_factory=dict)
    redaction_patterns: list[str] = field(default_factory=list)
    redact_emails: bool = True
    python: str = ""
    project_name: str = ""
    source: str = "defaults"

    @property
    def runs_dir(self) -> Path:
        return self.output_dir / "runs"

    def is_authorized_target(self, url: str) -> bool:
        return is_authorized(url, self.permissions.authorized_targets)


def is_authorized(url: str, allowlist: list[str]) -> bool:
    """True if ``url`` falls under an allowlisted origin (scheme, host, port and path prefix)."""
    try:
        u = urlsplit(url)
    except ValueError:
        return False
    if u.scheme not in ("http", "https", "ws", "wss") or not u.hostname:
        return False
    for entry in allowlist:
        a = urlsplit(entry)
        if a.scheme != u.scheme or (a.hostname or "").lower() != u.hostname.lower():
            continue
        if a.port is not None and a.port != u.port:
            continue
        prefix = a.path.rstrip("/")
        if prefix and not (u.path == prefix or u.path.startswith(prefix + "/")):
            continue
        return True
    return False


def _get(d: dict, key: str, typ: type, default):
    if key not in d:
        return default
    val = d[key]
    if typ is list:
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            raise ConfigError(f"'{key}' must be a list of strings")
        return val
    if typ is int and isinstance(val, bool):
        raise ConfigError(f"'{key}' must be an integer")
    if not isinstance(val, typ):
        raise ConfigError(f"'{key}' must be {typ.__name__}")
    return val


def load_config(project_root: Path | str = ".", config_path: Path | None = None) -> Config:
    root = Path(project_root).resolve()
    path = config_path or (root / ".qa-superteam" / "config.toml")
    data: dict = {}
    source = "defaults"
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: {e}") from None
        source = str(path)

    known = {"project", "output", "permissions", "budgets", "policy", "groups", "redaction", "python"}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"unknown config section(s): {', '.join(sorted(unknown))}")

    proj = data.get("project", {})
    out = data.get("output", {})
    perm = data.get("permissions", {})
    bud = data.get("budgets", {})
    pol = data.get("policy", {})
    red = data.get("redaction", {})
    py = data.get("python", {})

    output_dir = Path(_get(out, "dir", str, ".qa-superteam"))
    if not output_dir.is_absolute():
        output_dir = root / output_dir

    p = Permissions(
        write_tests=_get(perm, "write_tests", bool, False),
        test_dir=_get(perm, "test_dir", str, "tests/qa"),
        modify_app_code=_get(perm, "modify_app_code", bool, False),
        authorized_targets=_get(perm, "authorized_targets", list, list(LOCAL_TARGETS)),
        allow_load_testing=_get(perm, "allow_load_testing", bool, False),
        allow_active_security=_get(perm, "allow_active_security", bool, False),
        allow_fault_injection=_get(perm, "allow_fault_injection", bool, False),
    )
    b = Budgets(
        command_timeout_s=_get(bud, "command_timeout_s", int, 900),
        max_reproduce_attempts=_get(bud, "max_reproduce_attempts", int, 5),
        max_output_bytes=_get(bud, "max_output_bytes", int, 2_000_000),
        max_artifact_bytes=_get(bud, "max_artifact_bytes", int, 50_000_000),
        max_scan_files=_get(bud, "max_scan_files", int, 20_000),
    )
    if b.max_reproduce_attempts > 20:
        raise ConfigError("budgets.max_reproduce_attempts is capped at 20 to prevent retry loops")

    policy_path = DEFAULT_POLICY
    pol_str = _get(pol, "path", str, "")
    if pol_str:
        policy_path = Path(pol_str)
        if not policy_path.is_absolute():
            candidate = root / policy_path
            policy_path = candidate if candidate.exists() else PLUGIN_ROOT / pol_str

    groups_raw = data.get("groups", {})
    groups: dict[str, list[str]] = {}
    for name, sel in groups_raw.items():
        if not isinstance(sel, list) or not all(isinstance(x, str) for x in sel):
            raise ConfigError(f"groups.{name} must be a list of test selectors")
        groups[name] = sel

    return Config(
        project_root=root,
        output_dir=output_dir,
        permissions=p,
        budgets=b,
        policy_path=policy_path,
        critical_paths=_get(proj, "critical_paths", list, []),
        groups=groups,
        redaction_patterns=_get(red, "extra_patterns", list, []),
        redact_emails=_get(red, "redact_emails", bool, True),
        python=_get(py, "interpreter", str, ""),
        project_name=_get(proj, "name", str, ""),
        source=source,
    )
