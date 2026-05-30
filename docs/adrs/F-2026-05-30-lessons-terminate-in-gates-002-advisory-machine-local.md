# ADR F-2026-05-30-lessons-terminate-in-gates-002: Advisory-only, machine-local (never a CI hard-block)

**Date:** 2026-05-30
**Status:** Accepted

**Context:**
The audit target — lesson-class memories — lives at
`~/.claude/projects/<cwd-as-slug>/memory/`, which is operator-machine-local
and gitignored. A CI runner on another machine cannot see these files. The
prior gates in the pbj trilogy (Gap A runtime totalization, Gap B
contract-completeness) are hard-blocks or WARN gates inside the build
pipeline, operating on in-repo artifacts. The feedback-loop closer operates
on a fundamentally different, non-portable surface.

**Decision:**
The audit is **advisory by construction**. `lesson_gate_audit.py audit` always
exits 0 on a completed scan — including an absent memory directory (which
yields a clean "no memory dir" report, not an error). The only non-zero exit
is an argparse usage error (code 2). A non-zero exit, if a caller ever uses
one, is informational only. The audit never participates in a /build
hard-block or WARN gate; its sole consumer-facing surface is the read-only
`/metrics` "Feedback-loop closure" section and direct operator invocation.
No memory content is transmitted anywhere (locality; mirrors `/metrics`'
no-phone-home rule).

**Consequences:**
- *Easier:* zero risk of blocking a build on a machine-local file the CI
  runner cannot see; the feature is safe to ship into the shared pipeline
  without portability hazards.
- *Harder:* loop closure depends on operator attention rather than mechanical
  enforcement — mitigated by `/metrics` surfacing the % terminated-in-gate +
  the open-loop list on every report, so an open loop is visible, not silent.
  This is the deliberate trade: the F001 failure was *invisibility*, not
  *lack of a hard block*; visibility is the fix.
- The audit can be wired into a future operator-local hook or `/janitor`
  survey without changing its contract (it already degrades cleanly), but it
  must never become a CI gate on a non-portable surface.
