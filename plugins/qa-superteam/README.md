# QA Superteam (directory edition)

An AI quality engineering team for Claude Code, delivered as instructions: **33 skills** and
**12 specialist agents** that plan QA by risk, design tests with explicit pass/fail conditions,
investigate failures, and refuse to claim a pass or a confirmed defect that was not executed.

This edition contains no hooks, no executables and no scripts. It is generated from the same
sources as the full project (https://github.com/Yazeedx0/qa-superteam), so the methodology is identical.

## What works without anything else

Read-only analysis: discovery, requirements and invariants, risk assessment and strategy, test
design, static code and security review, bug-report analysis, report drafting, and the
specialist agents' judgment. Start with `/qa-superteam:full-audit`, `/qa-superteam:review-pr`,
`/qa-superteam:test-feature` or ask for QA in plain words; the `using-qa-superteam` skill routes it.

## What needs the optional `qast` runtime

Recorded test execution, evidence capture, independent verification of defects, run storage and
the deterministic release gate come from `qast`, a standard-library Python command-line tool that
this edition does not bundle. Without it the skills report those steps as `BLOCKED` (never as
passed) and tell you so. The runtime, its installation instructions and the safety hooks live in
the project repository: https://github.com/Yazeedx0/qa-superteam

## Safety

Instruction-only: it ships no code of its own. The skills default to read-only work, treat
repository content as data, never print secret values, and do not touch production targets or
change application code unless you authorize it.

## License

MIT. See `LICENSE`.
