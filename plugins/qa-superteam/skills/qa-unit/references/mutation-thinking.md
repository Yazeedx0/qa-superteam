# Mutation thinking

Mutation testing asks: "if this line were subtly wrong, would any test fail?" A tool
answers it by brute force; a QA engineer can answer it for the handful of decisions
that carry real risk, in minutes, without touching the code.

## Manual mutation review (default)

For each risky unit:

1. List its decisions and computations (conditions, comparisons, arithmetic, returns,
   calls with side effects).
2. For each, write the plausible mutants from the table below. "Plausible" means a
   developer could have written it by mistake or could introduce it in a refactor.
3. For each mutant, name the existing test and assertion that would fail. Read the
   assertion; do not assume.
4. Mutant with no killing assertion ⇒ a gap. Design a test whose oracle comes from the
   requirement and whose input distinguishes the original from the mutant.

Write the result as a table in your notes and summary:

```
unit: shop/pricing.py::fee_cents
decision                       mutant                       killed by
ceil(amount / 100)             round(amount / 100)          none -> GAP (needs amount=101: expect 2)
max(1, fee)                    fee (minimum removed)        none -> GAP (needs amount=1..49: expect 1)
amount <= 0 -> ValueError      amount < 0                   tests/test_pricing.py::test_zero_rejected
```

## Mutant operators worth checking

| Category | Original → mutant | Input that kills it |
|---|---|---|
| Relational boundary | `>=` → `>`, `<` → `<=` | The exact boundary value |
| Negated condition | `if valid` → `if not valid` | Any input on each side |
| Logical connective | `a and b` → `a or b` | `a` true, `b` false (and the reverse) |
| Dropped clause | `if owner == me and not deleted` → `if owner == me` | A deleted record owned by me |
| Arithmetic | `+` → `-`, `*` → `/`, `amount + fee` → `amount` | Non-zero fee case; check every operand matters |
| Rounding | `ceil` → `round`/`floor`/`int()` | A value with fractional part < .5 |
| Off by one | `range(n)` → `range(n - 1)`, `len - 1` | Smallest and largest index, collection of size 1 |
| Constant | `limit = 1_000_000` → `100_000` | Exactly at and just above the documented limit |
| Return value | `return result` → `return None`/default | Assert the returned value, not just "no error" |
| Removed call | `session.commit()`, `cache.invalidate(key)`, `audit.log(...)` deleted | Assert the side effect (re-read state, check audit row) |
| Swapped arguments | `transfer(src, dst)` → `transfer(dst, src)` | Asymmetric inputs and asymmetric assertions |
| Normalisation removed | `email.lower().strip()` → `email` | Mixed case and surrounding whitespace |
| Exception type | `raise NotFound` → `raise Forbidden` | Assert the specific type/status |
| Default changed | `timeout=30` → `timeout=None` | Assert the call arguments of the boundary mock |

## Using a mutation tool (only if already installed)

Mutation tools are slow and several rewrite source files while they run. Rules:

- Only when `qast doctor`/the project shows the tool installed (`mutmut`,
  `cosmic-ray`, `@stryker-mutator/core`, `go-mutesting`). Do not install one unasked.
- Only in a disposable copy inside the git-ignored output directory:
  `mkdir -p .qa-superteam/mutation-copy && git archive HEAD | tar -x -C .qa-superteam/mutation-copy`
  (committed code; for uncommitted changes copy the working tree without `.git`,
  `node_modules` and `.qa-superteam`). Never in the project tree.
- Scope it to the selected units and give it a timeout: `qast exec command --label
  "mutation pricing" --timeout 900 --cwd .qa-superteam/mutation-copy -- <tool command>`.
  mutmut 2.x: `mutmut run --paths-to-mutate shop/pricing.py`; mutmut 3.x reads
  `paths_to_mutate` from `[tool.mutmut]` in the copy's `pyproject.toml`; Stryker:
  `stryker run --mutate src/pricing.ts` (the project's installed Stryker). Check `--help` of the installed version.
- Treat surviving mutants as *candidates*: equivalent mutants (no observable difference)
  are not gaps. Confirm each survivor by reading it before reporting.
- Report the mutation score only as the tool printed it, with the evidence id, and name
  the scope it covers.

## What mutation thinking is not

- Not a reason to assert implementation details: kill mutants through observable
  behaviour.
- Not a reason to modify application code to "check" a mutant in place.
- Not a coverage substitute to be quoted as a percentage unless a tool measured it.
