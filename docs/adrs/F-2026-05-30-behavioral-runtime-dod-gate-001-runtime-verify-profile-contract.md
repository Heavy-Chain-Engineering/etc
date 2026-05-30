# ADR-001: Runtime-verify as a conductor-invoked per-profile script with a thin JSON contract

**Date:** 2026-05-30
**Status:** Accepted
**Feature:** F-2026-05-30-behavioral-runtime-dod-gate (Gap A)

**Context:** Gap A must stand an assembled application up with real data + real auth and
prove declared-live user-outcome ACs at runtime, across arbitrary client stacks. The
mechanism must (a) not depend on the Claude Code Stop event — the #47 spike found
Stop→SubagentStop conversion silently skips Stop-keyed gates under workflow subagents;
(b) let each stack own its own stand-up without the conductor knowing stack internals;
and (c) reuse the proven F020 profile-as-primitive rather than fork a new mechanism.

**Decision:** The runtime gate is a **conductor-invoked script**, exactly as `/build`
Step 6c already invokes the structural gate (`printf '{"cwd":…}' | bash hooks/verify-green.sh`).
`hooks/runtime-verify.sh` is the dispatcher: it iterates `.etc_sdlc/profiles.lock` and
invokes each active profile's `standards/code/profiles/<p>/runtime-verify.sh` (warn-and-skip
on missing lock/script, parity with verify-green). The per-profile contract is a thin JSON
pipe:

- **stdin:** `{"feature_path": <str>, "live_ac_ids": ["AC-3", …]}`
- **stdout:** `{"results": [{"ac_id": <str>, "status": "pass"|"fail"|"no-test", "evidence": <str>}]}`
- The profile owns stand-up (real data + real auth — never `canActivate:()=>true`) and
  teardown. The dispatcher reads `status` per AC, not the process exit code, for per-AC
  verdicts; a non-zero exit means the profile itself could not stand up.

The behavioral assertion lives in an **e2e/smoke test tagged with its AC id** (python(CLI)
profile: `@pytest.mark.ac("AC-3")` or a `test_ac_3_*` name fallback). runtime-verify
selects tests by AC id; a declared-live AC with no matching test returns `no-test` →
gate failure (the F001 hole). No separate `behavior.yaml` is introduced (YAGNI; Gap B
ADR-002's "no machine block until a consumer needs it" — the prose acceptance_statement
plus the AC-tagged test are sufficient).

This realizes the **consumer** half of the Consumer-Driven-Contracts split Gap B
ADR-001 named: Gap B's liveness block is the producer; this script is the verifier.

**Consequences:**
- *Easier:* zero new primitive kind (same F020 dispatch shape); no Stop-event dependency
  (#47 dissolved); each stack owns stand-up behind a stable JSON contract; the python(CLI)
  reference profile is dogfoodable on etc with no mocks.
- *Harder:* every stack that wants runtime verification must implement its own
  `runtime-verify.sh` (the web/Playwright profile is a declared follow-up); profile
  scripts run arbitrary stand-up commands and must be treated as trusted harness code.
- *Constrains:* the JSON contract is now a versioned wire interface (v1, additive-only);
  reshaping it is a breaking change for every profile.
