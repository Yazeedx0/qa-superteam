# Troubleshooting

**`qast doctor` first.** It lists every capability, its version, and the exact install
command for anything missing.

| Problem | Cause | Fix |
|---|---|---|
| `qast: command not found` in a session | Plugin not enabled, or session started before install | `/plugin` to enable, then `/reload-plugins`; outside Claude Code use `<clone>/bin/qast` |
| `qast requires Python >= 3.11` | Old system Python | `export QAST_PYTHON=/usr/bin/python3.12` |
| `no QA run found` | No run started in this project | `qast run start --mode adhoc --scope "..."` (workflows do this for you) |
| `already exists; pass --supersede` | Singletons are versioned | Add `--supersede`; the old version moves to `history/` |
| `refused: finding references evidence that does not exist` | Typo'd or foreign execution/evidence id | Copy ids from `qast run status` / the `qast exec` output |
| `qast verify` exits 3 | The verdict is not supported (self-verification, code-inspection only, no failing execution of your own, flaky) | Run your own `qast reproduce`/`qast exec`, or record `INCONCLUSIVE` with the reason |
| pytest executions `BLOCKED: pytest is not installed for interpreter` | qast picked an interpreter without pytest | `--python .venv/bin/python` or `[python] interpreter` in config |
| pytest `ERROR` with exit code 4 | Usage error (bad path/flag) — see the log artifact | Fix the arguments after `--` |
| Playwright: `Executable doesn't exist` | Browser build missing for the installed Playwright | `python -m playwright install chromium`, or `export CHROMIUM_EXECUTABLE=/path/to/chrome` |
| axe `BLOCKED: axe-core not found` | No `node_modules/axe-core` | `npm i -D axe-core` or `export QAST_AXE_PATH=/path/axe.min.js` |
| k6 `BLOCKED ... authorized_targets` | Target not allowlisted | Add the origin to `[permissions] authorized_targets` (never production unless intended) |
| k6 `BLOCKED ... __ENV.TARGET` | Script hard-codes its base URL | Use `${__ENV.TARGET}` in the script |
| Gate `REVIEW_REQUIRED` with nothing failing | Missing mandatory evidence, skipped mandatory tests, untriaged failures, or untested high risks | Read the triggered rules in `qast gate`; each names what is missing |
| Report says `decision.json is stale` | Evidence was recorded after `qast gate` | Re-run `qast gate`, then `qast report` |
| Guard hook keeps asking | A QA run is active and the action is risky or outside permissions | Approve if intended, adjust `.qa-superteam/config.toml`, or `qast run finish` when done |
| Guard hook active after a crash | Marker left behind | `qast run finish` (markers older than 12 h are ignored anyway) |
