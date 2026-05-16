# ADR-F020-005: profiles.lock is plain text, one profile per line

**Date:** 2026-05-16
**Status:** Accepted
**Context:** Five generalized bash hooks read the active profile list at fire time. The cache file format choice: (a) JSON (richest); (b) YAML (consistent with .etc_sdlc/profiles.yaml override); (c) plain text (one profile name per line).
**Decision:** Plain text. One profile name per line. No header, no schema version.

```
python
typescript
```

Bash hooks parse with `while read -r profile; do ... done < .etc_sdlc/profiles.lock`. No JSON parser, no `yq`, no Python boot for hook fire-time reads.
**Consequences:** *Positive:* zero dependency overhead in the hot path (every Write/Edit fires hooks; cumulative cost of a Python boot per hook would be 50-200ms × N gates × M edits per day — significant); trivial to inspect manually. *Negative:* if profiles.lock ever needs structured metadata (per-profile activation timestamp, version pin, etc.) the format must extend in a backward-compatible way OR we ship a profiles-lock-v2. The current YAGNI bar says plain text is sufficient; structured needs go in `.etc_sdlc/profiles.yaml` (the operator-authored override).
