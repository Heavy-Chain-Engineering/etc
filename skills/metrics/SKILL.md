---
name: metrics
description: Non-interactive three-layer metrics report. Reads git tags (process), value-hypothesis.yaml files (outcome), and .etc_sdlc/telemetry.db (cost), then emits a markdown report to stdout with the headline "% hypothesis-validated" broken down by author role.
---

# /metrics — Three-Layer Outcome Report

You are the metrics reporter. Your job is to produce a single markdown
report that unifies three independent data sources — process, outcome,
cost — into a labeled summary the operator can paste into a weekly
review. You do this deterministically, with no questions and no
follow-ups: every input is on disk under the project working tree, and
every output is a markdown document written to stdout.

You are non-interactive. You do NOT call `AskUserQuestion`. You do NOT
render Pattern B visual markers. You do NOT prompt the user for
clarification. If a data source is missing or malformed, you log the
condition inside the report itself and continue with the remaining
layers.

## Response Format (Verbosity)

Terse and structured. Output is a single markdown report with three
labeled sections (`## Process`, `## Outcome`, `## Cost`) plus a header
naming the project and the report timestamp. Use tables for per-role
breakdowns and per-event-type rollups, fenced code blocks for any raw
commit/tag references, and bullet lists for deferred items. Prose is
limited to: (a) a one-line preamble naming the report, (b) per-section
notes when a layer is empty or degraded (e.g. "no `etc/feature/*` tags
found", "telemetry.db absent"). No preamble ("I'll...", "Here is...").
No narrative summary outside the report sections. No emoji. The report
itself MUST be self-contained — no embedded links to unread files, no
dangling references.

## Subagent Dispatch (Non-Applicable)

`/metrics` does not dispatch subagents. It is a deterministic
data-aggregation command that completes in one context. You MUST NOT
attempt to Agent-dispatch any layer of the report; every read happens
in your own context via Read/Glob/Bash and the helper modules listed
below.

Your allowed in-context actions are: (a) reading files via Read/Glob,
(b) invoking the Python helpers in `scripts/` via Bash (one short
inline `python3 -c ...` script that imports them and prints the
report), (c) writing the auto-transitioned `value-hypothesis.yaml`
files back to disk via the helpers' `dump` function (this is the only
write `/metrics` performs, and only for `pending → unmeasured`
transitions per AC-014). You MUST NOT call `Write`, `Edit`, or any
network-bound tool. You MUST NOT read or write outside the project
working tree (AC-017, BR-014).

## Before Starting (Non-Negotiable)

Read these files in order before any data-gathering action, using the
Read tool on each exact path. If a file does not exist, follow the
per-file guidance below — do NOT silently skip reads.

1. `standards/process/interactive-user-input.md` — referenced for
   convention awareness only. `/metrics` is non-interactive and
   neither Pattern A nor Pattern B fires from this skill, but the
   skill is part of the same harness and must not introduce a third
   prompting style by accident. If this file is missing, log a note
   inside the report's header and continue (the skill is still
   functional without it because it asks no questions).
2. `scripts/value_hypothesis.py` — confirms the `load`,
   `validate_schema`, `transition_status`, and `dump` surface and the
   `LEGAL_STATUSES` / `REQUIRED_FIELDS` constants. The reader
   contract is: `load(path)` returns `None` on a future
   `schema_version` (warn-and-skip per BR-006/AC-006), raises
   `ValueError` on malformed/missing required fields, and otherwise
   returns the parsed mapping.
3. `scripts/telemetry.py` — confirms the `connect(db_path)` shape
   (WAL mode, schema bootstrap) and the events-table column set
   (`event_id`, `feature_id`, `event_type`, `timestamp`, `payload`,
   `schema_version`). The cost layer reads from this table directly
   via `conn.execute("SELECT ...")`; no write API is invoked by
   `/metrics`.
4. `scripts/git_tags.py` — confirms `list_etc_tags()` returns
   `(name, sha, iso8601_date)` triples and degrades to `[]` on
   non-git or no-HEAD repos. The process layer is built entirely
   from this list.

If `scripts/value_hypothesis.py`, `scripts/telemetry.py`, or
`scripts/git_tags.py` is missing, STOP and report the missing path
inside the report header — these are the canonical readers and the
skill cannot fabricate substitutes.

## Usage

```
/metrics                                # weekly report to stdout
```

`/metrics` takes no arguments in v1. The window for the auto-transition
rule (AC-014) is read from each hypothesis's own
`predicted.window_days` field, not from a CLI flag.

## Data Sources (Authoritative Paths)

| Layer   | Source                                          | Reader                                |
|---------|-------------------------------------------------|---------------------------------------|
| Process | git tags under `refs/tags/etc/feature/...`      | `scripts/git_tags.py::list_etc_tags`  |
| Outcome | `.etc_sdlc/features/F<NNN>-<slug>/value-hypothesis.yaml` | `scripts/value_hypothesis.py::load`   |
| Cost    | `.etc_sdlc/telemetry.db`                        | `scripts/telemetry.py::connect` + SQL |

Per BR-010, the three layers do NOT cross-derive. Outcome counts are
never inferred from cost data, and vice versa. The report renders each
layer from its own source and never reaches across.

## Workflow

### Step 1: Auto-transition pending hypotheses past their window

Per AC-014, every `value-hypothesis.yaml` with `status: pending` whose
elapsed time since the corresponding `etc/feature/F<NNN>/release` tag
exceeds `predicted.window_days` MUST be auto-updated to
`status: unmeasured` BEFORE the report is computed. This is the only
write `/metrics` performs.

Helpers are invoked via their CLIs at `~/.claude/scripts/`. Import-style
invocation (`from scripts.X import …`) MUST NOT be used — it only
resolves inside this checkout, not in arbitrary user projects.

The procedure:

1. List the etc/* tags via the git_tags.py CLI:
   ```
   python3 ~/.claude/scripts/git_tags.py list-etc-tags
   ```
   Each line of stdout is `<tag_name>\t<sha>\t<iso8601_date>` (tab-
   separated). Build a map `feature_id → release_tag_iso_date` by
   selecting tags whose `name` ends with `/release` and matches
   `etc/feature/F<NNN>/release`. If the same feature has multiple
   release tags (it should not, by BR-008/AC-010), use the earliest
   one as the window anchor.
2. Glob `.etc_sdlc/features/F<NNN>-<slug>/value-hypothesis.yaml`.
   Use the F-ID regex `^F\d{3}-` to identify candidate directories;
   directories that do NOT match (the 9 grandfathered slug-only
   features per GA-002, plus any non-spec-produced directories) are
   skipped here AND in the outcome layer (AC-016, GA-003).
3. For each candidate file, invoke the value_hypothesis.py load CLI:
   ```
   python3 ~/.claude/scripts/value_hypothesis.py load <path>
   ```
   The CLI prints the parsed hypothesis as sorted-key JSON to stdout
   on exit code 0; parse with
   `python3 -c "import json, sys; d = json.load(sys.stdin); ..."` or
   the equivalent. Exit code 1 on stderr means the file failed schema
   validation OR declared a future schema_version (warn-and-skip);
   record the filename and stderr message in a deferred-items list
   and skip.
4. If the loaded hypothesis has `status == "pending"` and the
   feature has a `release` tag and
   `(now_utc - release_tag_iso_date) > timedelta(days=hypothesis["predicted"]["window_days"])`,
   invoke the value_hypothesis.py transition CLI to atomically rewrite
   the file:
   ```
   python3 ~/.claude/scripts/value_hypothesis.py transition <path> unmeasured
   ```
   The CLI handles load + BR-011 state-machine check + atomic dump in
   a single invocation. Exit code 0 on success; exit code 1 if the
   transition is rejected (e.g. status is no longer `pending` because
   another /metrics run already moved it). The `validation` block is
   left untouched (no measured value, no evidence — that is the entire
   point of `unmeasured`).
5. Re-invoke the load CLI on the same path after the transition so
   the in-memory copy used by Step 3's outcome aggregation reflects
   the new status.

`now_utc` is derived from `datetime.now(timezone.utc)` at skill entry,
not per-feature, so the report is internally consistent.

### Step 2: Process layer — git tags

Render `## Process` from the output of the git_tags.py list-etc-tags
CLI (already invoked in Step 1; reuse that result rather than
shelling out a second time):

```
python3 ~/.claude/scripts/git_tags.py list-etc-tags
```

Each line is `<tag_name>\t<sha>\t<iso8601_date>` (tab-separated).
Categorize each tag and roll up:

- Total `etc/feature/*` tags by category: `spec`, `build/phase-*/start`,
  `build/phase-*/done`, `release`, `hotfix/H*`. Counts only —
  no cross-reference to outcome or cost.
- Features that have a `spec` tag but no `release` tag are listed
  under "In flight" with their feature_id.
- Features that have any `hotfix/H*` tag are listed under
  "Hotfixes since release" with the count per feature.
- If the CLI prints no lines (empty stdout), render the section with
  the literal note "No `etc/feature/*` tags found (non-git directory,
  no HEAD commit, or no tagged features yet)." and proceed.

### Step 3: Outcome layer — value-hypothesis.yaml

Render `## Outcome` from the per-feature hypothesis dicts loaded in
Step 1 via the value_hypothesis.py load CLI (`python3
~/.claude/scripts/value_hypothesis.py load <path>` — JSON on stdout).
Apply the grandfather skip BEFORE counting (AC-016, GA-003):
features whose directory does NOT match `^F\d{3}-` OR which lack a
`value-hypothesis.yaml` are excluded from every outcome-layer count.

The headline metric (AC-015) is **% hypothesis-validated**, defined
as `validated_count / (validated_count + invalidated_count + unmeasured_count)`
expressed as a percentage. `pending` hypotheses (those still inside
their window) are NOT in the denominator — they are reported in a
separate "still pending" line and excluded from the rate.

Render this as a single table with one row per `author_role` plus a
final `Total` row, exactly these columns (counts on the left,
percentages on the right):

| Role | Validated | Invalidated | Unmeasured | Pending | Total tracked | % Validated |
|------|-----------|-------------|------------|---------|---------------|-------------|

Notes:

- `Total tracked` excludes `Pending`. The `% Validated` column divides
  `Validated` by `Total tracked`. If `Total tracked` is zero for a
  role, render `% Validated` as `n/a` rather than dividing by zero.
- `author_role` values "SME", "Engineer", "PM", "Designer" each get
  their own row. Any value not in this set is bucketed under `Other`
  per edge case 7. The distinct custom values that fell into `Other`
  are listed as a footnote under the table.
- The `Total` row sums every column across all roles.

After the table, render:

- **Excluded from outcome layer:** count of feature directories that
  were skipped because they did not match `^F\d{3}-` or lacked a
  `value-hypothesis.yaml`. Name the directories on a single line
  (or "(none)" if the count is zero). This is informational —
  these features may still appear in process and cost.
- **Malformed hypotheses:** count and filenames of files where
  `load` raised `ValueError`. These are also excluded from the
  counts but flagged so the operator can fix them.

### Step 4: Cost layer — telemetry.db

Render `## Cost` from the `telemetry.py aggregate` CLI. The DB path
is `.etc_sdlc/telemetry.db` resolved relative to the current working
directory. If the file does not exist, render the section with the
literal note "No telemetry data: `.etc_sdlc/telemetry.db` not found."
and proceed. The skill MUST guard with `Path.exists()` before invoking
`aggregate` so a missing DB is not silently created by the metrics
read path. Cost data is recorded by other skills, never by `/metrics`.

If the DB exists, invoke the aggregator (no filters = whole-DB
aggregation):

```
python3 ~/.claude/scripts/telemetry.py aggregate --db-path .etc_sdlc/telemetry.db
```

Stdout is JSON with stable key order. Parse it with
`python3 -c "import json,sys; d=json.load(sys.stdin); ..."` (or equivalent)
and render as markdown:

- Total events grouped by `event_type`, ordered by count descending.
- Total events grouped by `feature_id` (the JSON encodes the
  project-level NULL bucket as the key `"__null__"` — relabel as
  `(project-level)` in the markdown).
- Date range of events (the aggregate output exposes the timestamp
  range; if the operator needs finer time slicing, re-invoke with
  `--since <iso8601>`).

Render each aggregation as a small markdown table. Do NOT compute
synthetic metrics like "tokens per validated hypothesis" — that is
exactly the cross-derivation BR-010 forbids.

### Step 5: Emit the report

Print the assembled markdown to stdout. Layout:

```markdown
# /metrics report — {project_basename} — {now_utc_iso}

## Process
{process tables and notes}

## Outcome
{outcome table with role breakdown}
{excluded / malformed footers}

## Cost
{cost tables or "no telemetry" note}
```

Do NOT write the report to disk. Do NOT mirror it to `~/.claude/`. The
report is ephemeral — the operator pipes it where they want it.

## Constraints

- **Non-interactive.** No `AskUserQuestion`, no Pattern B markers, no
  prompts of any kind. The skill runs to completion or fails loudly.
- **Three layers, three sources, no cross-derivation.** Process from
  tags only; outcome from hypothesis YAML only; cost from telemetry
  DB only (BR-010, AC-012).
- **Auto-transition before counting.** Pending → unmeasured for any
  hypothesis past its `predicted.window_days` since the `release`
  tag, applied as a write to disk BEFORE the outcome counts run
  (AC-014).
- **Grandfather skip in outcome layer only.** Features lacking
  `value-hypothesis.yaml` or with non-`F<NNN>` directory names are
  excluded from outcome counts (validated/invalidated/unmeasured/
  pending/total tracked). They MAY appear in process metrics if they
  have `etc/feature/*` tags and in cost metrics if they have
  telemetry rows (AC-016, GA-003).
- **Headline metric is % hypothesis-validated, by role.** Counts and
  percentages, with an overall total (AC-015, BR-012).
- **Locality.** Reads only inside the project working tree
  (`.etc_sdlc/`, `.git/`, `scripts/`, `standards/`). No `~/.claude/`
  reads or writes. No network calls. No phone-home (AC-017, BR-014,
  security consideration 4).
- **Schema-version tolerance.** A `value-hypothesis.yaml` with
  `schema_version > 1` is skipped with a warning (the helper does
  this); not an error.
- **Append-only with respect to tags.** The skill never invokes
  `git tag -d`, `git tag -f`, or any tag-mutation command (BR-008,
  AC-010). It only reads.
- **No new dependencies.** Use only the helpers in `scripts/` and
  the Python stdlib (`sqlite3`, `datetime`, `pathlib`, `re`,
  `logging`). PyYAML is already a transitive dependency via
  `value_hypothesis`.

## Definition of Done

`/metrics` is done for a given invocation when ALL of the following
hold. There is no "rejected path" because the skill is non-interactive
and never refuses input.

1. The Before Starting reads (items 1–4) were executed via the Read
   tool before any data-gathering action.
2. Step 1's auto-transition pass ran to completion: every
   `value-hypothesis.yaml` under a directory matching `^F\d{3}-`
   that had `status: pending` AND had a `release` tag whose age
   exceeded `predicted.window_days` was rewritten on disk with
   `status: unmeasured`. Files that already had a non-pending
   status, files without a `release` tag, and files inside their
   window were left untouched.
3. The report emitted to stdout contains exactly three labeled
   sections in this order: `## Process`, `## Outcome`, `## Cost`.
   No section is omitted; missing data sources are surfaced as
   inline notes inside their section, not by deleting the section.
4. The Outcome section contains a per-role table with the columns
   defined in Step 3 and a final `Total` row. The headline
   `% Validated` value is shown both per-role and on the `Total`
   row (or `n/a` where the role had zero tracked features).
5. The Outcome section explicitly accounts for excluded
   (grandfathered or non-`F<NNN>`) features and for files that
   failed schema validation, by count and filename.
6. The skill made no writes outside the auto-transition pass in
   Step 2, made no reads or writes outside the project working
   tree, and made no network calls (AC-017).

If any item is not satisfied, `/metrics` is NOT done. Do not print a
"report complete" line; just print the report itself and let the
operator inspect the sections.

## Post-Completion Guidance

Per the non-interactive rule, `/metrics` does NOT render an
`AskUserQuestion` block at the end. The report itself is the entire
output. The operator decides what to do next based on what they read.
