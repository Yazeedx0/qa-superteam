# Ambiguity checklist

Run every requirement through this list. "The sources do not say" is an ambiguity:
record what is undefined and which tests it blocks. Never fill the gap with a value,
even a plausible one taken from a neighbouring rule.

## Vague words

Always an ambiguity unless defined nearby: *may, might, should* (when the rest of the
document uses MUST), *appropriate, reasonable, large, small, fast, quickly, soon,
user-friendly, secure, robust, as needed, normally, typically, where possible, etc.,
and/or*, *supports X* (without saying what support means), *is reviewed / approved /
flagged* (without saying by whom, when, and what the user sees meanwhile).

## Gap checklist

| Area | Question | Typical gap |
|---|---|---|
| Thresholds and limits | Are min and max stated, inclusive or exclusive, in which unit? | "up to 140 characters": is 140 allowed? characters or bytes? |
| Numbers and rounding | Rounding mode? Where is it applied (per item or total)? Precision, currency? | "a 2% fee" with no rounding rule |
| Time | Time zone, clock source, inclusive boundaries, calendar days vs 24-hour periods, DST, exact expiry moment | "within 30 days of purchase" |
| Text normalization | Case sensitivity, trimming, unicode normalization, locale-specific casing | "usernames are unique" |
| Identity and scope | Which roles may act? Per user, per tenant, or global scope? | "codes can be used once": once per user or once overall? |
| Error behaviour | Which status and message? Which error wins when several apply (auth vs validation vs not-found)? | unauthenticated request with an invalid body |
| Empty and missing | Empty string, null, omitted field, empty list, zero | "memo is optional": is `""` the same as absent? |
| Extremes | Maximum sizes and counts, very long input, no pagination | list endpoint with 100,000 items |
| Concurrency | Simultaneous requests, double submission, retries | two refunds for one order at the same moment |
| Repeats | What happens when the same request arrives twice | resubmitted payment form |
| State | Allowed transitions, behaviour in each state, terminal states | cancelling a shipped order |
| Side effects | Notifications, audit records, what must not change | rejected request: is anything logged or charged? |
| Consistency | Displayed vs stored vs charged values | discount shown but not applied |
| Dependencies | Which other feature or service it relies on; behaviour when that fails | payment provider timeout |
| Non-functional | Latency or throughput numbers, accessibility level, supported browsers and locales | "pages should load fast" |
| Out-of-scope lists | Is something declared out of scope still reachable in the product? | "no pagination in v1" while the list grows unbounded |

## Recording

- `ambiguities`: one line each: `<REQ id or section>: <what is undefined>; blocks <which tests>`.
- The requirement keeps status `ambiguous` and carries the question in `open_questions`.
- Say what remains testable. Example: "large orders may require approval" defines
  neither the threshold nor the user-visible behaviour, so approval cannot be tested;
  the order rules that are stated can still be tested with amounts the team confirms
  are below any threshold.
- When the code implements a concrete value for an ambiguous rule, cite it as observed
  implementation behaviour in the question. It is not the requirement.

## Conflicts

Typical pairs: README vs requirements doc, doc vs API spec, ticket vs existing test
assertion, UI copy vs backend validation, two sections of one document. Record both
sources, set status `conflicting`, and pick no winner. A test whose verdict depends on
which source is right is marked as dependent on the resolution (`depends_on` and an
assumption with `impact_if_wrong`).
