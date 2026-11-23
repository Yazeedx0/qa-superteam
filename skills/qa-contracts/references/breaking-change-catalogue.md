# Breaking-change catalogue

Direction decides everything. A **request** is data the consumer sends (be liberal in
what you accept); a **response**/event is data the consumer receives (never take away or
widen beyond what consumers were promised). "Breaking" means a correct consumer built
against BASE can fail against HEAD without changing its code.

Levels: **B** breaking, **P** potentially breaking (depends on consumer strictness or on
undocumented behaviour; check consumers), **S** safe.

## HTTP / OpenAPI / JSON Schema

| Change | Request side | Response side |
|---|---|---|
| Operation (path + method) removed or renamed | B | B |
| Path parameter renamed (same position) | S for clients, B for generated SDKs that use names | n/a |
| New **required** field/parameter/header | **B** | S |
| New optional field/parameter | S | S for tolerant readers; P for strict deserialisers (`additionalProperties: false`, Java `FAIL_ON_UNKNOWN_PROPERTIES`) |
| Field removed | P (B if `additionalProperties: false` or the server now rejects it) | **B** |
| Field renamed | B (old name ignored or rejected) | B |
| Optional → required | **B** | S |
| Required → optional (may be absent) | S | **B** |
| Becomes nullable | S | **B** (consumers dereference it) |
| Type changed (`integer` → `string`, object → array) | B | B |
| Type widened (`integer` → `number`) | S | B (fractions appear) |
| Format changed (`date` → `date-time`, `int32` → `int64`, string → uuid) | P | P (parsers, column sizes) |
| Constraint tightened (`maxLength`↓, `maximum`↓, `minimum`↑, new `pattern`, `minItems`↑) | **B** | S |
| Constraint loosened | S | P (values consumers validate against) |
| Enum value removed | **B** | S (P if consumers branch on it for state) |
| Enum value added | S | **P** (exhaustive switches, strict enums in generated clients) |
| Default value changed | P (behaviour of clients that omit the field) | n/a |
| Success status code changed (`201` → `200`, `200` → `204`) | n/a | **B** |
| New error status for previously accepted input | B (it was accepted before) | n/a |
| Error body shape changed (`detail` string → object, error codes renamed) | n/a | B for clients that parse errors |
| Content type changed / removed (`application/json` → `application/problem+json`) | B | B (P if clients check `Content-Type` loosely) |
| Pagination introduced on a list that returned everything | n/a | **B** (clients silently see the first page) |
| Sort order or default filter changed | n/a | P (documented order is part of the contract) |
| Auth scheme/scope requirements changed or added | B | n/a |
| Rate limit or payload size limit lowered | P | n/a |
| Deprecated flag added | S (a signal, not a break) | S |
| Server URL / base path changed | B | B |

Semantics count even when the schema is unchanged: amounts switching from cents to
units, timestamps from UTC to local, an id that used to be stable becoming per-request,
or a field that keeps its name but changes meaning are **B**. Look for them in the code
diff (`qast impact`), changelogs and response examples, not only in the spec.

## GraphQL

| Change | Level |
|---|---|
| Type, field, argument, enum value or directive removed | B |
| Output field `T!` → `T` (nullable) | B |
| Output field `T` → `T!` | S |
| Input field/argument `T` → `T!`, or new required input field/argument without default | B |
| Input field/argument `T!` → `T` | S |
| Field type changed (other than nullability rules above) | B |
| Enum value added to a type used in **output** | P (exhaustive client switches) |
| Enum value added to a type used only in input | S |
| Union member added | P (clients without `__typename` fallback) |
| Interface field added | S for clients, B for schema implementers |
| Default value of an argument changed | P |
| Field deprecated (`@deprecated`) | S |

## Protobuf / gRPC (wire and generated-code compatibility)

| Change | Level |
|---|---|
| Field number changed, or reused for a different field | B (silent data corruption) |
| Field removed without `reserved` for its number and name | B (future reuse) |
| Field type changed to a wire-incompatible type (`int32` → `string`) | B |
| `int32` ↔ `int64` / `uint32` ↔ `uint64` ↔ `bool` | P (truncation, sign) |
| `optional`/`repeated` label changed | B |
| Field renamed | S on the wire, B for JSON mapping and generated code |
| Enum value removed or renumbered | B |
| Enum value added | P (old clients see unknown values) |
| Message, service or RPC removed/renamed; package changed | B |
| Request/response message type of an RPC changed | B |
| Streaming ↔ unary changed | B |

`buf breaking` with the `FILE` or `WIRE_JSON` rule set encodes most of this; read its
configured category before trusting "no breaking changes".

## Events and messages (Kafka, SNS/SQS, webhooks)

Consumers often lag producers by days and replay old messages, so both directions
matter: producers must emit what *old* consumers understand, consumers must read what
*old* producers wrote. Apply the response column to new producer output and the request
column to what the consumer accepts. Schema registries (Avro/Protobuf/JSON Schema) have
a configured compatibility mode (`BACKWARD`, `FORWARD`, `FULL`): report changes against
that mode, and treat a mode change itself as B.

## Classifying a finding

| Situation | Record |
|---|---|
| B, consumers exist or are unknown, no version bump/deprecation | Finding, category `contract`; severity by consumer impact (see below) |
| B, intended, versioned (new major path/header, changelog, deprecation window honoured) | `qast run note --kind decision` citing the evidence; the failed `contract` check stays for a human to accept |
| P | Finding only if a known consumer breaks (show where); otherwise list under "potential, consumer review needed" |
| Spec and implementation disagree | Finding against whichever contradicts the documented intent; say which one you believe is wrong and why |

Severity guide: critical when a known production consumer's essential flow fails (e.g.
checkout client no longer parses the payment response); high when consumers fail on a
common path or data is silently misread (unit change, nullable id); medium for rarely
used endpoints or failures that are loud and easy to fix; low for SDK-ergonomics-only
changes.
