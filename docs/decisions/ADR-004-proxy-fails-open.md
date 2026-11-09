# ADR-004: MCP proxy fails open in v1

- **Date:** 2026-11-08
- **Status:** Accepted (revisit in T-33 adversarial pass)
- **Decided by:** Hamza Farooq

## Context

T-09 puts CIM between the MCP client and HexStrike on stdio. If the proxy breaks
the session, the agent stops working and the demo (C2) fails. Plan §4.8 and risk
R1 call for a fail-open v1.

## Options considered

1. **Fail closed:** drop or reject frames the proxy cannot parse. Safer against a
   server that hides behaviour in malformed frames, but any parser bug breaks
   real sessions.
2. **Fail open:** forward every line byte-for-byte; capture is best-effort and a
   parse failure produces an `alert` record (chosen).

## Decision

- Every stdio line is forwarded unchanged in both directions, parsed or not.
- Unparseable frames (bad JSON, bad UTF-8, non-object) are forwarded and recorded
  as `alert` records with code `proxy_malformed_frame`, direction, size and SHA-256.
- Store failures (cannot open the DB, a write fails) are logged to stderr and
  never stop forwarding.
- The request is registered before it is forwarded so a fast server reply is
  never missed (a race found by the 100-call replay test).
- The enforcement hook (`allow_call`) exists but allows everything; T-29 adds
  quarantine refusal there.

## Consequences

A malicious server can emit frames CIM cannot interpret; they still reach the
client, but each one leaves an alert in the hash-chained store. Fail-closed
enforcement is a Phase 2 decision (T-29 / T-33).
