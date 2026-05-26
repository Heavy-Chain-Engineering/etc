# ADR-F-2026-05-26-004: Each rubric item carries a `mechanizable` flag; fitness-function graduation is deferred

**Date:** 2026-05-26
**Status:** Accepted

**Context:** Some rubric criteria are inherently human-judgment ("is this service boundary cohesive?"); others are mechanically checkable ("every new query-filter column has a backing index"). Building Evolutionary Architectures (Ford, Parsons, Kua, Sadalage) makes the endpoint explicit: "anything in an automated fitness function, you never have to review, because the build fails." A mechanizable criterion should eventually graduate from a manual matrix-walk cell to an automated `/build` check, removing it from the architect's manual burden and making it un-skippable in code rather than in discipline.

The question is how much of that to build now. The operator chose mechanism option 1 (registry + matrix-walk phase), explicitly NOT the "ship a fitness function now" option. So this feature must set the trajectory without building the automation — and must do so in a way that a follow-up feature can act on without re-deciding which criteria are mechanizable.

**Decision:** Every rubric item in the registry carries a boolean `mechanizable` flag, authored at rubric-definition time, indicating whether the criterion can graduate to an automated `/build` fitness-function check in a follow-up feature. This feature builds NO fitness function — the flag is roadmap metadata only. A future feature reads the flag to know which criteria to mechanize first (e.g., the data-access index-coverage criterion is `mechanizable: true`; "is the service boundary cohesive" is `mechanizable: false`).

The flag is part of the registry schema (ADR-001) and is asserted present-and-boolean by a schema test (spec AC-013).

**Consequences:** *Positive:* the automation trajectory is set declaratively at the point of maximum context (when the criterion is authored, the author knows whether it is mechanizable); a follow-up fitness-function feature has a ready-made worklist (filter the registry by `mechanizable: true`) and does not re-litigate which criteria qualify; zero blast radius now — no /build fitness-function machinery, no new test infrastructure, no false-positive risk from immature automated checks; honors the operator's explicit scope choice (option 1, not option 3). *Negative:* the flag is inert until a follow-up feature consumes it — it is documentation-of-intent that could drift if criteria change without the flag being revisited (mitigation: the flag is a required field, so every new criterion forces an explicit mechanizable decision; a stale flag is a small, correctable data error); marking `mechanizable: true` is a prediction that may prove wrong when someone tries to build the actual check (mitigation: the follow-up feature validates feasibility per criterion; the flag is a starting hypothesis, not a contract).

**Alternatives considered:**

*Build the data-access fitness function now* (rejected — and was offered to the operator as option 3, who declined). *Positive:* immediate automated teeth on the exact prod-bug class; proves the graduation path end-to-end. *Negative:* touches /build with new fitness-function machinery (blast radius the operator chose to avoid this session); requires the registry + matrix-walk to be settled first (this feature), so it is naturally a follow-up; couples the framework's first release to a working automated check, raising the risk surface of a feature whose value is the framework itself.

*No flag; decide mechanizability later* (rejected). Ship the registry without the flag; a follow-up adds it. *Positive:* smaller schema now. *Negative:* loses the author-time context (whoever adds a criterion later must re-derive whether each existing criterion is mechanizable, with less context than the original author had); the follow-up feature inherits an un-annotated registry and must do the mechanizability triage from scratch; a required flag is nearly free to add now and expensive to backfill later.

**Related ADRs:**
- F-2026-05-26-001 (declarative registry) — the flag is a registry-schema field.
- F-2026-05-26-002 (matrix-walk) — mechanized criteria eventually leave the manual walk.
- F010 / fitness-function follow-up (future) — the consumer of this flag.
