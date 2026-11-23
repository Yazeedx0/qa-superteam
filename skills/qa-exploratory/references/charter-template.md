# Exploratory charter template

A charter is a session's contract: what you are looking for, why it matters, how you
will know something is wrong, and when you stop. Write it before probing and record it
with `qast run note "<charter text>" --kind decision`, so the report shows what was
intended, not only what happened.

## Fields

```
CHARTER EX-<n>: Explore <target> with <resources/techniques> to discover <information>
Area:        <component, endpoints, journey or prompt flow; file paths if known>
Risk:        <risk id from risks.json, or one line: what fails, for whom, how badly>
Hypotheses:  H1 <falsifiable statement>; H2 ...; (2-5)
Oracles:     <requirement ids / doc sections / invariants / comparable feature / product's own claims>
Heuristics:  <which ones from heuristics.md and why they fit this risk>
Setup:       <in-process client | local server on 127.0.0.1:<port> | dataset>, throwaway data
Time-box:    <minutes, default 20>      Probe budget: <count, default 25>
Out of scope:<what you will deliberately not touch, e.g. load, injection payloads>
```

A hypothesis is falsifiable when one probe outcome would refute it:

| Weak | Falsifiable |
|---|---|
| "Transfers might have bugs" | "H1: two concurrent transfers that each fit the balance, but not both, can both succeed" |
| "Check validation" | "H2: amounts sent as JSON floats (10.5) are accepted and truncated instead of rejected with 422" |
| "Test the bot" | "H3: a paraphrase of an answerable question retrieves a different document than the canonical wording" |
| "Look at the UI" | "H4: pressing Back after submitting the sign-up form and submitting again creates a second account" |

## Recording example

```bash
qast run note --kind decision "CHARTER EX-1: Explore POST /payouts with concurrent and retried requests to discover double payment. Area: payouts/service.py, api/payouts.py. Risk: R-03 (money movement). H1 two concurrent payouts that each fit the balance, but not both, both succeed; H2 a retry with the same idempotency key and a changed note pays twice; H3 the processing fee is charged again on retry. Oracles: SPEC 2.1 (balance never negative), SPEC 4.2-4.3 (idempotency); invariant: sum of balances plus fees is constant. Setup: in-process test client, temp DB. Time-box 20 min, 25 probes. Out of scope: load, token forgery."
```

## Choosing charters

- One risk per charter. Two unrelated risks make two charters, or the time-box hides which one was explored.
- Start with the highest probability x impact area that the existing suite does not cover (`qast impact` "changed source with NO related tests", risks without planned tests).
- Prefer invariants over single values: "sum of all balances never changes" catches more than "the fee for one specific amount is right".
- A charter that produced only questions is a success when the questions are specific - they become requirement ambiguities.

## Follow-up charters

When the time-box ends mid-thread, write the open thread as a new charter with the
evidence that motivated it ("ex-... showed X; next: Y"). Never extend the running
session past its budget; the lead decides whether the follow-up runs.
