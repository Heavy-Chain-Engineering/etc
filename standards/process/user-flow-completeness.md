# User-Flow Completeness for User-Facing Acceptance Criteria

## Status: MANDATORY
## Applies to: /spec

## The Problem

A user-facing acceptance criterion can be satisfied by a unit test that
imports the target component directly, while the navigation path that leads
a real user to that component is never wired up. The component compiles, its
tests pass, and the spec-enforcer returns COMPLIANT — but a user opening the
app cannot reach the surface. This failure mode shipped seven times in
venlink-platform's F4 capability-entitlements build (19% of leaf tasks
delivered orphan surfaces) and was caught only when a user opened the running
app and tried to navigate.

This standard defines the contract that closes the gap at authorship: before
a spec is finalized, every user-facing AC must include a sentence that forces
the author to mentally trace the full navigation path to the surface.

## The Contract

Every user-facing acceptance criterion in a `/spec`-produced PRD includes a
User-flow sentence in the canonical form:

`"As {role}, navigate from {parent route} via {affordance label}, complete {happy path}, observe {outcome}."`

This sentence is the forcing function. It cannot be written without naming the
parent route and the affordance that gets the user there — exactly the two
elements that orphan-route bugs omit.

## Surface-Detection Signal List

The following signals are used by `/spec` Phase 3 to classify each AC. The
classification governs whether the User-flow sentence elicitation step runs.

### Strong user-facing signals

- **Route paths** matching the pattern `/[a-z][a-z0-9/_$-]*` (e.g.,
  `/platform/organizations`, `/settings/billing`, `/users/$id/profile`)
- **UI nouns:** `modal`, `page`, `wizard step`, `tab`, `button`, `drawer`,
  `menu`, `dialog`, `form`, `screen`, `panel`, `sidebar`, `link`, `card`
- **User verbs:** `navigate`, `click`, `submit`, `see`, `view`, `open`,
  `select`, `enter`

An AC containing any route path, any UI noun, or any user verb is classified
user-facing unless the conflict-default rule applies and the author overrides.

### Strong backend-only signals

An AC is classified backend-only when ALL of the following are true:

- Its only assertions are one or more of: HTTP status codes, database row
  counts, background-job behaviors, or pure migration outcomes.
- It contains no UI noun from the list above.
- It contains no user verb from the list above.

If even one UI noun or user verb is present alongside backend-only assertions,
the AC is not backend-only — see the conflict-default rule below.

## Conflict-Default Rule

When an AC mixes user-facing and backend-only signals — for example, "When
the wizard submits, the API returns 201 with X" — it defaults to user-facing.

This boundary is the F4 failure mode. The wizard submission is the user
action; the 201 is the backend assertion. Both belong in the spec. But the
correct classification is user-facing, because the user's navigation path to
the wizard is what the User-flow sentence must capture. Classifying such an
AC as backend-only would leave the orphan-route gap intact.

When in doubt, classify user-facing and let the author mark not-user-facing
during the Phase 3 elicitation step if the classification is wrong.

## Enforcement Model (WARN-with-YES/NO Gate)

The rule is enforced in two phases of `/spec`, neither of which hard-blocks.
Backend-only and intentionally-unreleased surfaces are legitimate exceptions.

### Phase 3 — Auto-detection and per-AC elicitation

After the initial Acceptance Criteria section is drafted, `/spec` scans each
AC for user-facing signals using the signal list above. For each AC classified
user-facing, the skill presents the AC alongside a prefilled User-flow
sentence drafted from the surrounding PRD prose, and prompts the author via
`AskUserQuestion` (Pattern A) to:

1. **Accept the draft User-flow sentence (Recommended)** — the sentence is
   appended verbatim to the AC.
2. **Refine — I have changes** — a Pattern B (`**▶ Your answer needed:**`)
   follow-up captures the revised sentence, then re-prompts.
3. **Mark this AC not-user-facing** — the AC is recorded as
   `surface_status: backend_only` and no User-flow sentence is required.

An AC that already contains the canonical prefix `"As {role}, navigate from`
is treated as already-compliant; the elicitation step is skipped for that AC.

### Phase 4 — Definition-of-Ready gate

After the six existing DoR items, the skill enumerates ACs flagged
user-facing during Phase 3 and checks whether each has a User-flow sentence
appended. If any user-facing AC lacks a sentence, the gate enters a WARN and
presents the offending AC list via `AskUserQuestion` (Pattern A):

1. **No, fix the missing sentences first (Recommended)** — the skill returns
   to Phase 3 AC editing.
2. **Yes, ship without — these surfaces are intentionally deferred** — the
   skill records a `surface_status: deferred` line for each offending AC in
   the spec's Edge Cases section and proceeds to Phase 5. Future maintainers
   can audit these lines and add User-flow sentences when the surface is wired.

The gate does NOT hard-block. Selecting "Yes, ship without" is recorded so
the deferral is auditable; it is not treated as a policy violation.

## Scope

This rule applies to **web/app UI surfaces**: route-shaped paths and clickable
affordances rendered in a browser or native-app view.

The following surface types are out of scope; analogous rules for them are
future work:

- **Email** — transactional or notification emails the user receives
- **Webhooks** — payloads delivered to external systems
- **CLI** — command-line interfaces and terminal output

## Worked Example (F4 AC-44)

This rule originated from venlink-platform's F4 capability-entitlements
feature build, where orphan surfaces were the dominant failure mode. AC-44
from that build is the canonical reference example.

### Before (system-perspective — violates this standard)

> "Org-creation second page captures vendor cap + entitlements: ... when they
> submit, the response is 201 with the created Organization,
> paid_vendor_count = 250, and exactly 3 customer_entitlement rows in ACTIVE
> status with source = 'org_creation'."

This AC mixes a user action ("when they submit") with backend assertions (201,
row counts). The conflict-default rule classifies it user-facing. But it names
no parent route and no affordance label — a developer reading it cannot know
which nav path wires to the org-creation wizard's second page.

### After (with User-flow sentence — compliant)

> "Org-creation second page captures vendor cap + entitlements: ... when they
> submit, the response is 201 with the created Organization,
> paid_vendor_count = 250, and exactly 3 customer_entitlement rows in ACTIVE
> status with source = 'org_creation'."
>
> "As a platform operator, navigate from `/platform/organizations` via the
> 'Create Organization' button, complete both wizard pages (basic profile +
> cap/entitlements), submit, observe a 201 response with
> `paid_vendor_count = 250` and exactly 3 customer_entitlement rows, and
> observe the browser landing on `/platform/organizations/$orgId`."

The User-flow sentence names the parent route (`/platform/organizations`),
the affordance label ('Create Organization' button), the happy path (both
wizard pages), and the observable outcome (201 + row count + redirect). A
developer implementing this AC now has everything needed to wire the route.

**Origin:** venlink-platform capability-entitlements feature directory, F4
build retrospective (2026-04-10). See the project memory for the full
failure-mode analysis.

## Multiple Entry Points

When a surface is reachable from more than one affordance (e.g., main nav AND
a contextual menu), two patterns are acceptable:

1. **One AC per entry point** — write a separate User-flow sentence for each
   navigation path. Preferred when the paths have different preconditions or
   roles.
2. **Single AC with a note** — write one User-flow sentence for the primary
   path and add a free-text note in the AC body listing the alternate entry
   points. Acceptable when the paths are functionally identical.

## Cross-References

- `standards/process/interactive-user-input.md` — Pattern A (`AskUserQuestion`)
  and Pattern B (visual marker) rules that govern the Phase 3 elicitation and
  Phase 4 gate prompts.
- `skills/spec/SKILL.md` — the `/spec` skill that implements the Phase 3
  detection step and Phase 4 gate described in this standard.
- `hooks/inject-standards.sh` — injects a summary of this rule into every
  subagent's onboarding context (section: User-Flow Completeness for
  User-Facing ACs).

## Reachability Evidence

The User-flow sentence is authored at `/spec` time; this section defines the
verify-time half of the contract. The reachability check fires only when an
AC carries a User-flow sentence (canonical prefix `As {role}, navigate from`).
Only then does spec-enforcer require reachability evidence. ACs without the
sentence pass through spec-enforcer's existing per-AC evaluation unchanged.

Three evidence forms are accepted, in preference order. spec-enforcer stops
at the first form found.

### 1. E2E test (preferred)

A test file that programmatically navigates from `{parent route}`, interacts
with `{affordance label}`, completes `{happy path}`, and asserts `{outcome}`.
Acceptable frameworks: Playwright, Cypress, or any equivalent end-to-end
browser-driving framework. Framework choice is the deliverable team's
decision; the contract is the navigation-and-assertion behavior.

Evidence shape: `<test_file_path>: <quoted line>`.

### 2. Static nav-graph reference

A single grep finds the `{affordance label}` substring OR the `{parent route}`
substring in any file outside the AC's own component dir. The match signals a
real `<Link>`, sidebar entry, tab definition, or other wiring that connects
the parent route to the surface.

The grep is loose by design (per GA-003): false positives are accepted because
spec-enforcer records the file:line of the match for human review. A comment
or string literal that happens to contain the affordance label is recorded
the same as a real wiring; the human reviewer is the disambiguator. Tightening
the rule is future work.

Evidence shape: `<file_path>:<line>: <quoted match>`.

### 3. Manual reachability proof

A screencap, screen recording, or operator-attested log entry naming the
artifact path, an ISO8601 timestamp, and a free-form operator name.

Free-form attestation contract (per GA-004): the operator name is accepted as
any string and recorded verbatim by spec-enforcer. There is no harness-identity
gate, no allowlist, no LDAP lookup — accountability lives in the recorded
evidence, not in a runtime identity check. Audit trails downstream of
spec-enforcer surface the operator name as written.

Evidence shape: `<artifact_path> @ <ISO8601> by <operator_name>`.

### Verdict Mapping

- Zero evidence forms found → `NOT_SATISFIED`.
- Attempted-but-inconclusive (e.g., grep returned a partial match, manual
  proof has missing metadata) → `INSUFFICIENT_EVIDENCE`.

Both states fail closed downstream: `/build` Step 7 treats either verdict as
`NON_COMPLIANT` and blocks the release tag and `release-notes.md`.

### Security Constraints (spec-enforcer behavior)

- **No automatic Read of artifact paths.** spec-enforcer records the
  manual-proof artifact path verbatim but MUST NOT `Read` the file. This
  prevents directory-traversal attacks via a hostile AC pointing the agent at
  `/etc/passwd`, `~/.aws/credentials`, or other sensitive files outside the
  project tree. The path is a string for human review, not a runtime fetch
  target.
- **Operator-name sanitization.** Before recording, spec-enforcer strips
  control characters (regex `[\x00-\x1f\x7f]`) and caps the operator-name
  string at 64 characters. Mirrors the `/spec` Phase 1 "Other" sanitization
  contract. Mitigates log-injection and CSV-injection attacks against
  downstream auditing tools that may parse the JSON output.

### Scope

This rule applies to web/app UI surfaces only. CLI, webhook, and email
surfaces are out of scope per the F001 Scope section above. An AC whose
User-flow sentence names a non-web/app surface is treated as a configuration
error: spec-enforcer records `NOT_SATISFIED` with evidence noting the
out-of-scope surface type.
