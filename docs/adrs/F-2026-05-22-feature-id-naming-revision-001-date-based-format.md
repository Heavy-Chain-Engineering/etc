# ADR-001: Date-based feature ID format

**Date:** 2026-05-22
**Status:** Accepted
**Supersedes:** ADR-F023-001 (Ftmp-<hex> temp-ID format)

**Context:**
F023-001 introduced a branch-local temp-ID format `Ftmp-<8-char-hex>` for
the `/spec`-time feature directory, intended to be renamed to a sequential
`F<NNN>` form at `/build` Step 7c (terminal phase close). The rationale
was cross-machine collision-safety: two operators running `/spec`
simultaneously on different machines could not race on the same `F<NNN>`
slot. The temp form would be assigned a final sequential ID at build
close.

The hex form turned out to be poor UX in practice (operator feedback
2026-05-22):

- The hex string carries no semantic content. `Ftmp-5afddbce-installer-rewrite`
  is harder to scan in `ls` output than a meaningful prefix.
- The temp→final rename added load-bearing plumbing in `/build` (Step 7c.0
  resolve-final-id) plus matching ADR rename logic, plus `id_history`
  tracking in `state.yaml`.
- The phase tags written during build kept the `Ftmp-<hex>` form (per
  ADR-F023-004), so the temp identifier persisted in the audit trail
  forever — the rename only affected the dir name + new tags, not history.
- `ls .etc_sdlc/features/active/` produced unsortable noise during
  multi-feature work.

Three alternative formats were considered:

| Format | Sortable | Collision-safe | Readable |
|--------|----------|----------------|----------|
| `F-YYYY-MM-DD-<slug>` (this ADR) | yes (chronological) | yes (date+slug) | yes |
| ULID-based `F-01HQXR3VW9N-<slug>` | yes | yes | partial |
| `F-YYMMDD-NN-<slug>` (per-day counter) | yes | yes | yes |

**Decision:**
Replace the F023 `Ftmp-<8-char-hex>` form with `F-YYYY-MM-DD-<slug>`. The
date is the current UTC date at `/spec` time. The dir name IS the
feature_id — there is no separate `-<slug>` suffix segment as with the
F<NNN> form. On same-day same-slug collisions (operator types the same
slug twice on the same day), auto-suffix with `-2`, `-3`, ... up to a
99-attempt safety bound.

Implementation: `scripts/feature_id.py::allocate_temp` is rewritten in
place (the function name and CLI subcommand `allocate-temp` are
preserved for source-compat with existing skill bodies; only the format
of the returned `feature_id` changes). The legacy `Ftmp-<hex>` regex
patterns (`_TEMP_ID_PATTERN`, `_TEMP_DIR_PATTERN`, `_ADR_TEMP_PATTERN`)
remain as backward-compat readers for any in-flight F021-F026 era dirs;
no new feature is produced in that form. `resolve_final_id` becomes a
no-op for date-based IDs — there is no rename step.

**Consequences:**

*Easier:*
- Chronological sort comes for free; `ls features/active/` shows
  features in creation order.
- The dir name is human-readable at a glance; no need to grep `state.yaml`
  to recover the slug from a hex prefix.
- `/build` Step 7c.0 (resolve-final-id) becomes a no-op for new features;
  no rename plumbing executes; the `etc/feature/<id>/build/phase-N/*`
  tags retain their original form through release tag and active→shipped
  move.
- ADR file naming follows the same `<feature_id>-NNN-<slug>.md` shape as
  before, just with the new feature_id form (this ADR itself dogfoots).
- Cross-machine collision-safety preserved: two operators producing
  features on different machines pick different slugs near-trivially;
  the date+slug combo is near-unique.

*Harder:*
- Backward-compat readers must be maintained for the lifetime of any
  surviving Ftmp-<hex> dir (F021-F026 era — these are all in shipped/
  or were never produced in temp form). Removable when the operator
  decides to rename the legacy dirs (forward-only per F023's own
  discipline; not required).
- The dated form is longer (~35 chars vs ~22 for `Ftmp-<hex>-<slug>`)
  but still well under the filesystem path-component limit (typically
  255 chars on Linux/macOS, 260 on Windows).
- Same-day same-slug collisions require the operator to either pick a
  better slug or accept the auto-suffix. In practice, `-2`/`-3`
  suffixes are an audit-trail signal that two related features shipped
  the same day, which is itself useful.

*Deferred:*
- Per-day counter format (`F-YYMMDD-NN-<slug>`) reconsidered if
  same-day collisions become common (unlikely).
- ULID-based form reconsidered if sub-second uniqueness ever becomes a
  requirement (high-throughput automation that etc does not currently
  target).
- Retroactive rename of F021-F026 to the dated form is NOT performed.
  Forward-only per F023's discipline; legacy F<NNN> names stay as-is
  in `shipped/`.

**Related ADRs:**
- Supersedes ADR-F023-001 (`docs/adrs/F023-001-temp-id-format.md`).
- ADR-F023-002 (rename-at-step-7c) is also superseded — there is no
  rename step for the new format.
- ADR-F023-003 (adrs-renamed-via-git-mv) is partially superseded — the
  ADR rename machinery is preserved for any in-flight Ftmp-<hex> dirs
  but does not fire for new features.
- ADR-F023-004 (phase-tags-preserved-in-temp-form) becomes trivially
  satisfied — phase tags are written under the dated form which IS
  the final form, so no preservation logic needed.
