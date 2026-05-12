# ADR-F011-004: Minimal file-watch JSON schema (session_id + decisions delta)

**Date:** 2026-05-11
**Status:** Accepted

**Context:**
The file-watch JSON file (per ADR-F011-002) is the contract surface between impeccable's browser extension (writer) and /design (reader). Three schema variants were considered: (a) minimal — only the most recent designer-decision delta (`session_id` + `decisions[]`); (b) detailed — full impeccable decision-history for the project (cumulative, replay-capable); (c) deferred-to-implementation (no /architect-level schema decision; let /build decide).

The deciding force is **coupling**. Detailed schemas tie F011 to impeccable's internal storage format; future impeccable schema changes ripple into /design. Minimal schemas trade audit-replay capability for isolation: /design knows only what the browser extension wants to apply *right now*, not everything impeccable has ever decided.

**Decision:**
Minimal schema:

```json
{
  "session_id": "<impeccable session UUID>",
  "decisions": [
    {
      "token_or_component": "<string identifier>",
      "value": "<arbitrary JSON value>",
      "decided_at": "<ISO-8601 timestamp>"
    }
  ]
}
```

/design reads this file at Phase 5 entry and on `/design --sync`. Decisions are applied to /design's in-memory state during the current session; full impeccable history stays in impeccable's own storage and is NOT mirrored into /design's state.yaml.

Validation: malformed JSON → halt with Pattern B parse error; missing required fields → halt with Pattern B field-name error; valid schema → apply decisions and re-present Phase 3 sections for re-approval.

**Consequences:**
- **Easier:** Small surface, small failure modes, easy to parse and validate; preserves wrap-and-invoke isolation (ADR-F011-001) — /design never touches impeccable's internal storage; cross-platform JSON parsing (stdlib only, no new deps).
- **Harder:** Loses full audit-replay capability — if a designer's complete decision history needs to be reconstructed from /design's side, the data isn't there (impeccable retains it; /design does not mirror).
- **Deferred:** Full-history schema (future PRD if audit-replay becomes a requirement); cross-session merge semantics (handling multiple JSON files from different sessions); JSON schema versioning (forward-only — F011 ships v0; future PRD adds explicit `version` field if schema changes).
- **Cannot defer:** The minimal-schema decision itself — /design's reader implementation needs the schema to know what to parse.
- **Related ADRs:** ADR-F011-002 (file-watch protocol choice) defines the transport; this ADR defines the payload shape.
