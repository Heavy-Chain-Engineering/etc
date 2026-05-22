# /build --extend — Post-Ship Refinement Lane

`/build --extend "<problem>"` is the harness's only sanctioned re-entry point for a feature
that has already shipped. It reopens the shipped directory, runs rule-based triage, dispatches
work with the original `spec.md`, `design.md`, ADRs, and `value-hypothesis.yaml` as substrate,
and re-closes with a versioned release tag. This standard defines the triage rubric, the
shipped↔active lifecycle, the extension ID format, the audit-log payload, and the endpoint
discipline that prevents zombie extensions.

## Status: MANDATORY

## Applies to: skills (/build), scripts/extend_resolver.py, scripts/release_notes.py, /metrics

Applies to extensions invoked after the F025 release tag lands. Legacy shipped features
(F001–F028) become extendable post-F025; see Forward-Only.

## Triage Rubric

`scripts/extend_resolver.py classify` reads the operator's `<problem>` string plus the target
feature's context-pack and emits exactly one of `light`, `medium`, `heavy`. The rubric is
rule-based and deterministic — no LLM call, no PyPI dependency. Operators override the
auto-classification with explicit `--triage light|medium|heavy`.

**Light.** Problem text names ≤3 specific file paths (regex: paths ending in
`.py|.ts|.tsx|.md|.sh|.yaml|.yml`) AND contains no architectural keywords (`redesign`,
`rearchitect`, `swap framework`, `migrate to`, `replace with`, `restructure`).

**Heavy.** Problem text contains ≥1 architectural keyword OR explicit ADR-amendment
language (`amend ADR`, `revise ADR`, `change the architecture`).

**Medium.** Everything else.

Per ADR-F025-001 (`docs/adrs/F025-001-triage-rubric.md`), the rubric is auditable and
operator-overridable. LLM-based classification was rejected (cost + non-determinism).

**Heavy refusal.** When triage = Heavy AND no operator override, the skill MUST refuse with
the literal substring `"scope creep, not a refinement"` to stderr, exit non-zero, and make
NO state changes (no dir move, no `state.yaml` append, no tag write). The skill MUST NOT
silently degrade to Medium or attempt the work. The refusal redirects the operator to
`/spec '<your problem>'` to file a fresh feature with proper Socratic refinement.

If the operator believes the problem IS refinement (not scope creep), re-invocation with
`/build --extend --triage medium '<problem>'` overrides the rubric.

## Lifecycle Semantics

`shipped/` is a **state, not a one-way door.** Per ADR-F025-002
(`docs/adrs/F025-002-lifecycle-reopen.md`), a shipped feature MAY transition back to
`active/` for the duration of an extension, then forward again to `shipped/` on re-close.
Both transitions are preserved in the audit trail.

**Shipped → active (reopen).** For Light or Medium triage outcomes,
`scripts/extend_resolver.py reopen` moves the feature directory from
`.etc_sdlc/features/shipped/F<NNN>-<slug>/` to `.etc_sdlc/features/active/F<NNN>-<slug>/`
via `shutil.move` (F022 gitignored-fallback inherited). The move is path-traversal-safe and
rejects symlinks outside the repo.

State persists across the reopen: the original `spec.md`, `design.md`,
`gray-areas-{spec,architect}.md`, all ADRs, `value-hypothesis.yaml`, `verification.md`,
every task YAML, and `release-notes.md` remain unchanged in the directory. The extension
augments rather than replaces.

**Active → shipped (re-close).** A reopened extension MUST eventually re-close. The
existing `/build` Step 7c.1 active→shipped move applies verbatim;
`scripts/extend_resolver.py close` invokes the same path. `state.yaml.extends[N].completed_at`
is set on close.

**Failure mode.** Failed extends leave the feature in `active/` (no auto-move back to
`shipped/`). Operator remediates manually via `/build --resume`. On eventual re-close,
`completed_at` is set. This matches F022's three-branch failure-semantics shape
(partial-state acceptable; operator-remediable).

**Concurrent extends on the same feature from different machines.** F023's POSIX-atomic
allocate-next handles the original-release-tag write; the extension IDs are UUID7-derived
(collision-free across machines). One operator's `shutil.move(shipped → active)` wins; the
other gets `shutil.Error` (dest exists). This is documented as expected behavior — the
second operator retries after the first completes.

## Extension ID Format

`scripts/extend_resolver.py generate-id` returns an 8-char lowercase hex string matching
`^[0-9a-f]{8}$`. The construction is stdlib-only:

```python
def generate_extend_id() -> str:
    timestamp_ms = time.time_ns() // 1_000_000   # 6 bytes
    randomness = os.urandom(2)                   # 2 bytes
    raw = timestamp_ms.to_bytes(6, 'big') + randomness
    return hashlib.sha256(raw).hexdigest()[:8]
```

Time-ordered via the millisecond-timestamp prefix; the sha256 truncation provides
randomness in the trailing hex characters. Strings sort chronologically by lexical
comparison (modulo timestamp collisions within the same millisecond on the same machine).

**Collision space.** Approximately a 50-day timestamp window before two extends in the
same millisecond on the same feature would collide. Operationally collision-free.

**Stylistic alignment.** The 8-hex shape rhymes with F023's `Ftmp-<8-hex>` temp-ID format.
The extension ID stands alone (no prefix) because it always appears as a path suffix on a
resolved `F<NNN>` (e.g., `etc/feature/F042/release_01b5a3c7`).

Per ADR-F025-003 (`docs/adrs/F025-003-extension-id-format.md`), the rejected alternatives
were: pure UUID4 (not time-ordered), sequential `/N` (re-introduces F023 cross-machine
collision class), and the `uuid7` PyPI package (no-new-deps policy).

## Release-Tag Versioning

Each successful extend cuts `etc/feature/F<NNN>/release_<extend_id>` at the post-close HEAD
via `scripts/git_tags.py::write_tag`. Example:

```
etc/feature/F042/release             ← original release tag (preserved, unchanged)
etc/feature/F042/release_01b5a3c7    ← first extend's release tag
etc/feature/F042/release/02c1d4f9    ← second extend's release tag
```

The original `etc/feature/F<NNN>/release` tag is NEVER deleted, retagged, or force-updated.
F021 BR-008 append-only tag discipline is inherited verbatim. The original tag continues to
point at the original release commit; the extension tags point at their respective
post-close HEADs.

The shipped feature's `release-notes.md` gains an append-only `## Extensions` section.
Each extend appends a sub-section:

```markdown
## Extensions

### Extension 01b5a3c7 — light triage — 2026-06-15

Problem: the SettingsPage uses shadcn but the rest uses radix; swap it.

Dispatched: frontend-developer (1 task).
Result: COMPLIANT. shadcn imports removed; radix equivalents in place; visual parity verified.
Release tag: etc/feature/F042/release_01b5a3c7
```

`scripts/release_notes.py` reads `state.yaml.extends` and emits the section when the array
is non-empty.

## Audit-Log Emission

Each `/build --extend` invocation emits exactly one row to
`.etc_sdlc/efficiency/turn-events.jsonl` (the F019 audit-log surface) with
`event_type: "extend_dispatch"`. The payload schema has 8 fields:

```json
{"ts": "2026-06-15T14:00:00Z",
 "event_type": "extend_dispatch",
 "feature_id": "F042",
 "extend_id": "01b5a3c7",
 "triage": "light",
 "problem_truncated_80": "the SettingsPage uses shadcn but the rest of the app uses radix;",
 "dispatched_agents": ["frontend-developer"],
 "started_at": "2026-06-15T14:00:00Z"}
```

| Field | Type | Notes |
|---|---|---|
| `ts` | ISO-8601 UTC string | Emission timestamp |
| `event_type` | string literal | Always `"extend_dispatch"` |
| `feature_id` | string | Final form `F<NNN>` |
| `extend_id` | string | 8-char hex |
| `triage` | enum | `light \| medium \| heavy` |
| `problem_truncated_80` | string | First 80 chars of operator's problem text |
| `dispatched_agents` | list[string] | Role names only — no role manifests, no payloads |
| `started_at` | ISO-8601 UTC string | Extend invocation start |

Write failures degrade silently per F019 best-effort conventions. The extend itself
succeeds; the operator sees the row missing from `/metrics` later. This is not a hard
error.

**Heavy refusals are NOT logged.** No state changes occur on Heavy refusal; no audit row
is written. Only Light and Medium triage outcomes that proceed to dispatch emit the row.

**Payload privacy.** The problem text is truncated to 80 characters. Agent role names
only — no role manifests, no system prompts, no secrets. Best-effort append.

## Endpoint Discipline

A reopened extension MUST eventually re-close. Once a feature enters `active/` via
`/build --extend`, the only sanctioned exit is the active→shipped re-close move with
`completed_at` set on the corresponding `state.yaml.extends` entry. There is no
"abandon extend" path. Extensions that fail mid-build stay in `active/` until the
operator either completes them (`/build --resume`) or explicitly remediates the
`state.yaml` (in which case the remediation MUST be recorded as a comment).

**Why this matters.** The whole point of `/build --extend` is contextual continuity. A
shipped feature whose state.yaml lists three half-finished extensions is no longer a
trustworthy substrate — the next refinement cannot tell which constraints from the
original spec still hold and which have been silently mutated by an in-flight extension.
Endpoint discipline prevents this rot.

**`/metrics` reporting.** `/metrics` MAY surface unclosed extends (entries where
`completed_at` is null) as "in-flight extensions" to nudge operators. Surfacing is a
future PRD; the audit data is captured today. The discipline obtains regardless of
whether the report exists yet.

## Forward-Only

This convention applies to extensions invoked after the F025 release tag lands. Pre-F025
shipped features (F001–F028) MAY be extended post-F025; their `state.yaml` files do not
carry an `extends:` field until the first `--extend` call creates it. The append on
first-extend leaves pre-existing `state.yaml` content (`id_history`, `spec_phase`,
`architect_phase`, `build`) byte-equivalent. Pre-F025 dispatches are not retroactively
audited.

The `extends:` field is append-only. Existing entries are never mutated by F025 code.

## ADR citations

- **ADR-F025-001 — Triage rubric (rule-based, deterministic)**
  (`docs/adrs/F025-001-triage-rubric.md`): Light/Medium/Heavy gating via file-path
  detection + architectural-keyword scan. Rejected alternative: LLM-based classification
  (cost + non-determinism).

- **ADR-F025-002 — Lifecycle reopen: `shipped/` is a state, not a door**
  (`docs/adrs/F025-002-lifecycle-reopen.md`): Feature dir moves shipped→active for the
  extend duration. Rejected alternative: append-only sub-feature dir under
  `features/shipped/F<NNN>-<slug>/extensions/<extend_id>/` (fragments the audit trail).

- **ADR-F025-003 — Extension ID: 8-char hex, time-ordered, stdlib-only**
  (`docs/adrs/F025-003-extension-id-format.md`): UUID7-like construction via
  `time.time_ns()` + `os.urandom(2)` + sha256 truncate. Rejected alternatives: pure UUID4
  (not time-ordered), sequential `/N` (cross-machine collision class), `uuid7` PyPI
  dependency (no-new-deps policy).

## Anti-patterns

**Silently degrading Heavy triage to Medium.** Heavy refusal exists because architectural-
impact work belongs in `/spec`, not in a refinement lane. An operator who overrides Heavy
to Medium with explicit `--triage medium` accepts the override on their own audit trail.
A skill that silently degrades is a defect.

**Mutating existing `state.yaml.extends` entries.** The list is append-only. Existing
entries record what happened; mutating them corrupts the audit trail. To repair a
corrupted entry, append a comment to `state.yaml` documenting the remediation; never
overwrite.

**Force-updating the original release tag.** Each extend cuts a NEW tag at
`etc/feature/F<NNN>/release_<extend_id>`. The original `etc/feature/F<NNN>/release`
remains. Force-updating the original (e.g., to point at the most recent extend's HEAD)
breaks F021 BR-008 and corrupts the audit record of what the original release shipped.

**Leaving extensions in-flight indefinitely.** Endpoint discipline is non-negotiable. An
extension left in `active/` for weeks while the operator moves on is a zombie ticket; the
shipped feature it reopened is no longer trustworthy substrate. Either complete the
extend or remediate the `state.yaml` manually with a recorded comment.

**Running `/build --extend` on a feature still in `active/`.** `/build --extend` operates
on shipped features only. To continue building an in-flight feature, use `/build --resume`.
The skill rejects this case explicitly.

**Cross-feature extends.** `/build --extend` operates on ONE feature at a time. Refinements
that span multiple shipped features should be `/spec`'d as new features.
