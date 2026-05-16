# ADR-F020-003: Warn-and-skip fallback when no profile matches

**Date:** 2026-05-16
**Status:** Accepted
**Context:** A hook fires on a file with no active profile claiming it — e.g., a `.lua` file in a Python+TS monorepo where no lua profile is installed. Three options: (a) silent skip (today's behavior on non-Python files); (b) hard-block until a profile is declared; (c) warn-and-skip (emit a stderr WARN line naming the gate that did not apply, exit 0).
**Decision:** Warn-and-skip. Hooks MUST emit a stderr line of the form `[<gate-name>] WARN: no profile matches <file>` and exit 0. Silent exit is forbidden; non-zero exit is forbidden.
**Consequences:** *Positive:* operator sees the gap at edit time without being blocked; closes the recurring "silent gap" failure mode (the F004/F009/F011 pattern where non-Python work escaped enforcement and nobody knew); greenfield repos remain workable. *Negative:* operators on truly multi-language stacks may see WARN lines for files etc legitimately can't police; if the WARNs are noisy the operator may suppress them via `.etc_sdlc/profiles.yaml exclude_paths`, which silences the gate again (intentional — operator's call, audit-trail in the override file).
