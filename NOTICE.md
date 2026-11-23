# Notices and attribution

QA Superteam is an independent project. Its skill-library *architecture* — composable
`SKILL.md` skills with precise activation criteria, progressive disclosure through
reference files, subagent delegation, and "evidence before claims" verification
discipline — is inspired by [obra/superpowers](https://github.com/obra/superpowers)
by Jesse Vincent (MIT License, Copyright (c) 2025 Jesse Vincent).

No Superpowers skill text or code is copied into this repository. Where QA Superteam
adapts an idea (for example, testing skills with pressure scenarios, or keeping
`SKILL.md` small and moving detail into `references/`), the adaptation is described in
`docs/design-decisions.md`.

Third-party tools invoked by QA Superteam adapters (pytest, Playwright, axe-core, k6,
Bandit, pip-audit, Semgrep, gitleaks, Vitest, Jest) are not distributed with this
repository and remain under their own licenses. The `examples/web-checkout` fixture
installs axe-core (MPL-2.0) locally via npm for demonstrations only.
