# Feature Numbering — The F<NNN> Convention

## Status: MANDATORY
## Applies to: All `/spec` invocations, all tooling that reads or writes feature directories

## The rule

Every feature created through `/spec` receives a stable, project-scoped
identifier of the form `F<NNN>` (3-digit, zero-padded). The feature
directory is named `F<NNN>-<slug>` where `<slug>` is the kebab-case
version of the spec title. For example, a feature titled "Payment
Processing" becomes `F042-payment-processing`.

Two properties are independently guaranteed:

- **The ID is immutable.** Once `F042` is assigned, it refers to that
  feature for the lifetime of the project. No renumbering, no reuse, no
  reassignment — ever.
- **The slug is mutable.** Renaming a directory from
  `F042-payment-processing` to `F042-checkout-flow` is permitted and
  free. The slug is purely cosmetic; all cross-references cite by ID,
  not by directory name.

## Allocation

The allocator computes `max(existing F-IDs in .etc_sdlc/features/) + 1`
at spec-finalization time (Phase 5 of `/spec`). It then attempts to
create the directory `F<NNN>-<slug>` using POSIX `os.mkdir()`.

Because `mkdir()` is atomic at the filesystem level, concurrent `/spec`
invocations on the same project are safe: whichever call wins the
`mkdir()` gets the ID; all losers see `EEXIST`, re-read the current
maximum, and retry at `F<NNN+1>`. No file-locking library is needed
(see GA-006).

Three edge cases worth knowing:

- **Gaps are acceptable; reuse is not.** If `/spec` is aborted after
  `F043` is allocated but before the session completes, `F043` is
  consumed. The next `/spec` allocates `F044`. Gaps in the ID sequence
  are normal and expected.
- **Re-speccing an existing slug is rejected.** `/spec` refuses to
  create a directory that already exists. Use `/spec --refine F043`
  to revise a finished spec, or pick a new title.
- **The v1 ceiling is `F999`.** Attempting to allocate beyond `F999`
  produces a clear error: "Project has reached the v1 feature ID ceiling
  (999). Upgrade to 4-digit IDs is a future PRD." There is no silent
  overflow.

## Mutability

| Property | Mutable? | Notes |
|----------|----------|-------|
| `F<NNN>` numeric ID | No | Fixed at creation; never reused or reassigned |
| Directory slug | Yes | Rename the directory; update no other files |
| `spec.md` contents | Yes | Revised via `/spec --refine` |
| Git tags (`etc/feature/F<NNN>/*`) | No | Append-only; deletion breaks process metrics |

Slug mutability is free precisely because the slug carries no semantic
weight. Every artifact that references the feature — tasks, completion
reports, value-hypothesis files, release notes, git tags — cites by
`F<NNN>`. A slug rename never breaks a reference.

## Migration

The 9 feature directories that existed before this standard was
introduced keep their slug-only names (e.g., `hotfix`,
`spec-three-state-classification`, `tasks-cli`). They are grandfathered:
`F<NNN>` numbering applies forward-only, starting from the first `/spec`
invocation after this standard was adopted (see GA-002).

Grandfathered features are not retroactively renumbered. The risk of
retroactive renaming — broken commit references, PR links, and
cross-feature citations — outweighs the benefit of a uniform namespace.
Tooling that reads feature directories (notably `/metrics`) identifies
grandfathered features by the absence of the `F<NNN>-` prefix and
handles them accordingly: they may appear in process and cost metric
layers if they have matching git tags or telemetry events, but they are
excluded from the outcome metric layer because they have no
`value-hypothesis.yaml`.

## Cross-references

- **Spec:** `.etc_sdlc/features/metrics-and-release-notes/spec.md`
  — BR-001 (ID allocation), BR-002 (ID immutability), BR-003 (atomic
  allocation), and the Out-of-Scope clause on retroactive renumbering.
- **Gray areas:**
  - GA-002 — Grandfather migration policy. Records the decision to keep
    existing slug-only directories unchanged and the rationale for
    preferring forward-only migration.
  - GA-006 — POSIX atomic `mkdir()`. Records the decision to use
    filesystem atomicity rather than file-locks or a DB sequence, with
    citation to POSIX.1 `mkdir(2)` semantics.
- **Implementation:** `scripts/feature_id.py` —
  `allocate_next(features_dir, slug)` is the canonical allocator;
  `slugify(title)` produces the kebab-case slug.
- **Tests:** `tests/test_feature_id.py` — covers atomic allocation,
  EEXIST retry, F999 ceiling, and slugify edge cases.

## Origin

This standard was adopted alongside the Metrics, Release Notes, and
Feature Numbering PRD (`.etc_sdlc/features/metrics-and-release-notes/spec.md`).
Before this PRD, feature directories were slug-only; there was no stable
identifier for cross-artifact reference, no audit-safe tag namespace,
and no ceiling on uncontrolled directory growth. The `F<NNN>` convention
closes all three gaps with a single, lightweight rule enforced
mechanically by the allocator at spec-finalization time.
