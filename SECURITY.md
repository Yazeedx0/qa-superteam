# Security policy

## Reporting a vulnerability
Please report vulnerabilities privately through GitHub's "Report a vulnerability"
(Security Advisories) on this repository. Do not open public issues for security problems.
Include affected version, impact, and reproduction steps. We aim to acknowledge within
5 business days.

## In scope
- Ways for repository content or tool output to make QA Superteam act on embedded
  instructions, leak secrets into reports, or bypass the guard hook or target allowlists.
- Redaction failures for common credential formats.
- Evidence or verification gate bypasses (recording CONFIRMED without the required evidence).

## Out of scope
- The behaviour of third-party test tools invoked by adapters.
- Pattern-evasion of the guard hook by deliberately obfuscated commands you typed yourself
  (the hook is a seatbelt, not a sandbox; see docs/security.md).

The full threat model is in [docs/security.md](docs/security.md).
