"""Execution adapters. Each wraps an existing, mature tool; none re-implements one."""

from .nonfunctional import run_ai_eval, run_axe, run_k6
from .security import run_bandit, run_gitleaks, run_npm_audit, run_pip_audit, run_semgrep
from .testrunners import run_command, run_jest, run_junit, run_playwright, run_pytest, run_vitest

ADAPTER_FUNCS = {
    "pytest": run_pytest,
    "junit": run_junit,
    "vitest": run_vitest,
    "jest": run_jest,
    "playwright": run_playwright,
    "command": run_command,
    "k6": run_k6,
    "axe": run_axe,
    "ai-eval": run_ai_eval,
    "bandit": run_bandit,
    "pip-audit": run_pip_audit,
    "npm-audit": run_npm_audit,
    "semgrep": run_semgrep,
    "gitleaks": run_gitleaks,
}
