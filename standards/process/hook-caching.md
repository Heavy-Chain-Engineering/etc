# Hook Caching — Per-Subagent Marker-File Pattern

Hook caching is a technique for amortizing the cost of a repeatedly-fired
`PreToolUse` hook across a single subagent session. A hook writes a
zero-byte marker file after a successful verification, and subsequent
invocations within the same subagent session early-exit on the marker
with a sub-millisecond `test -f` check instead of re-running the full
verification body. The harness needs this pattern because several of
its `PreToolUse Edit|Write` hooks verify state that rarely changes
within a subagent session, so running them on every Edit is pure waste.

## The Rule

When a hook's verification state rarely changes within a subagent
session, cache the successful result with a marker file keyed by
`sha256(transcript_path)`. The marker lives at
`.etc_sdlc/.hook-markers/{key}-{hook-name}` where `{key}` is the first
16 hex characters of the SHA-256 of the subagent's `transcript_path`
field from stdin. On the next Edit in the same session, the hook
checks for the marker as its very first action after reading stdin;
if present and still valid, the hook exits 0 immediately.

Invalidate the marker when the check's dependency file (the file the
verification reads) is newer than the marker, using the bash `-nt`
comparison: `[ "$DEP_FILE" -nt "$MARKER" ]`. If the dependency file is
newer, the marker is stale and the hook falls through to the full
verification path. The `-nt` idiom is the standard bash mtime compare
and is the extent of this PRD's invalidation strategy — no content
hashing, no inode tracking, no cache-invalidation rabbit hole.

The marker MUST only be written after a *successful* verification.
Failed checks (exit 2 on block) MUST NOT write markers. A failing check
must not poison the cache: the next Edit must re-run the full
verification, giving the agent a chance to have fixed the underlying
issue in between (one common example: reading the missing required
file). A hook that writes its marker before checking its exit code
is broken.

## Why This Rule Exists

Each `PreToolUse` hook fires on every Edit and Write tool call. On a
parallel `/build` wave with N subagents each issuing roughly 10 edits,
that's 20N invocations of the same verification, most of which check
state that hasn't changed since the subagent started. The verification
body is the same body, run over the same inputs, producing the same
answer. The work is repeated not because the state changed but because
the harness has no memory between tool calls.

bash startup cost on macOS is roughly 30–80ms per invocation before
the script does any useful work — loading the shell, parsing the
script, reading stdin, dispatching `jq`. The verification body itself
(file globs, YAML parsing, dependency reads) adds more on top. For
hooks whose dependency files barely move within a session, nearly all
of that cost is wasted. At 20N invocations per wave, the wasted cost
is the dominant contributor to per-wave hook overhead and blocks
release readiness on parallel-wave feature work.

Marker-file caching amortizes the verification cost across the
subagent session. The first Edit pays the full verification cost and
writes the marker; every subsequent Edit in that session pays only the
cost of a `test -f` and a `-nt` compare, which is sub-millisecond. The
origin analysis for this pattern is `spec/hook-cost-reduction-brief.md`
(the brief that surveyed three optimization options) and the PRD that
promoted it to an approved path is
`.etc_sdlc/features/hook-cost-reduction/spec.md`.

## When to Cache and When Not To

Hook caching is not universally safe. It only works when the
verification is a pure function of state that is stable within a
subagent session. Applying the pattern to a hook whose verification
depends on per-Edit state will silently miss violations.

**DO cache** when all of the following hold:

- The verification result is stable within a subagent session — it
  depends only on files and state that don't change as a side effect
  of the edits being verified.
- The dependency file the verification reads changes infrequently, and
  when it does change its mtime reliably advances.
- The hook has a clean failure mode: on a blocking result (exit 2) the
  hook has no side effects beyond writing to stderr. This means a
  failed check leaves no partial state to repair.

**DO NOT cache** when any of the following hold:

- The verification depends on per-Edit state like `tool_input.file_path`
  — each Edit has a different file path and the verification must run
  fresh against it.
- The dependency can change mid-subagent in a way the `-nt` check
  can't detect. Two illustrative modes (not exhaustive): an in-place
  edit that preserves the original mtime; a dependency spread across
  hundreds of files where the "newest mtime" query is itself expensive.
- The hook has side effects that must run on every Edit (metrics
  emission, audit logging, telemetry) — caching would suppress the
  side effect on every cached Edit.

Concretely: `check-required-reading.sh` and `check-phase-gate.sh` are
the two hooks this PRD makes cacheable. Their verification results
are stable within a session and their dependency files are well-defined
(`.etc_sdlc/tasks/*.yaml` and `.etc_sdlc/features/*/tasks/*.yaml` for
required-reading; `.sdlc/state.json` for phase-gate). The other three
`PreToolUse Edit|Write` hooks — `check-tier-0.sh`, `check-test-exists.sh`,
and `check-invariants.sh` — are candidates for future PRDs but are NOT
in this PRD's scope. Adding caching to them requires its own
per-hook analysis of dependency file, stability, and failure mode.

## The Marker File Format

Markers live under a single directory at the repo root:

```
.etc_sdlc/.hook-markers/{key}-{hook-name}
```

where `{key}` is derived as:

```
key = sha256(transcript_path) | cut -c1-16   # 16 hex chars
```

and `{hook-name}` is a short identifier chosen by the hook author.
The two hooks made cacheable by this standard use `required-reading`
and `phase-gate` as their identifiers. Example marker path:

```
.etc_sdlc/.hook-markers/a1b2c3d4e5f60718-required-reading
```

The marker is a zero-byte existence flag. Its contents are
irrelevant — only its existence and its mtime matter. Creation is
`touch` or equivalent; no data is written. The invalidation contract
is a single bash test:

```bash
[ "$DEP_FILE" -nt "$MARKER" ] && MARKER_STALE=1
```

If the dependency file is newer than the marker, the marker is
treated as stale and the hook runs the full verification path. The
16-hex-character key is path-traversal-proof by construction: SHA-256
output cannot contain `..`, `/`, or any shell metacharacter, so the
marker path is guaranteed to be inside `.etc_sdlc/.hook-markers/`.

The `.etc_sdlc/.hook-markers/` directory is gitignored — markers are
per-session runtime state, never artifacts. The directory is created
on first use via `mkdir -p` and is expected to accumulate a small
number of marker files per session.

## Graceful Degradation Requirements

A caching hook must degrade gracefully across four failure modes.
Each one represents a real situation the pattern will encounter in
production, and each one must be handled by running the full
verification, not by erroring.

**Missing transcript_path.** If the hook's stdin does not include a
`transcript_path` field, or the field is the empty string, the hook
MUST skip caching entirely and run the full verification body. No
marker is written, no marker is read. This is graceful degradation,
not a failure — the hook still does its job, it just does it the
slow way. Do not error, do not warn loudly, do not block. A hook
that errors on missing `transcript_path` will break any invocation
path that doesn't populate that field.

**Read-only filesystem or permission denied.** If the hook can't
create `.etc_sdlc/.hook-markers/` (directory creation fails) or can't
write the marker file (touch fails), the hook MUST log a warning to
stderr, skip the cache write, and return the verification result as
if caching were disabled. Graceful degradation: the verification has
already run and produced an answer, and the inability to persist a
marker does not invalidate that answer. Never let a marker-write
failure turn a passing verification into a blocking exit.

**Markers directory is a symlink.** If `.etc_sdlc/.hook-markers/`
exists as a symlink (detectable with `test -L`), the hook MUST refuse
to write through it. This is a defensive measure: an adversary with
write access to `.etc_sdlc/` could create a symlink pointing at
`/etc/` or another sensitive directory, so that hook marker writes
would land outside the repo. On detection, the hook logs a warning
to stderr, skips the cache write, and runs the full verification. Do
not `rm -rf` the symlink and do not follow it; just decline to use
it. This framing is defensive — the goal is remediation of the
symlink condition, not exploitation analysis.

**Clock skew.** If the system clock goes backwards — NTP adjustment,
VM snapshot restore, container time warp — a previously-valid marker
can suddenly look older than its dependency file even though nothing
changed. The `-nt` compare returns false, the cache miss triggers a
full verification, and the hook runs its slow path. This is a
performance regression, not a correctness bug: the verification still
runs and still produces the right answer. Accept the occasional
unnecessary re-verification rather than trying to paper over clock
skew with timestamp-normalization logic.

## Security Considerations

**Cache poisoning via marker pre-creation.** If an adversary with
write access to `.etc_sdlc/.hook-markers/` pre-creates a marker file
with a future mtime, the hook's cache-hit branch will early-exit
without verifying, allowing an Edit that should have been blocked.
Mitigation: none in v1.6. The `.etc_sdlc/` directory is under the
operator's own control — the threat model assumes single-operator
use, not a multi-tenant environment where a hostile actor has write
access to harness state. A future PRD can upgrade markers to signed
tokens (HMAC of a session-scoped secret keyed into each marker) if
multi-tenant etc usage becomes a requirement. Until then, the
assumption is documented here and the risk is accepted.

**Path traversal via transcript_path.** The `transcript_path` stdin
field is under Claude Code's control, not the user's, but defense in
depth is cheap: the cache key is the first 16 hex characters of
`sha256(transcript_path)`, which cannot contain `..`, `/`, or any
shell metacharacter. Path traversal through the cache key is
impossible by construction, and the resulting marker path is
provably inside `.etc_sdlc/.hook-markers/`. No `realpath` check is
needed.

**Stale marker missing a legitimate violation.** If a dependency file
is updated in place but its mtime isn't advanced — rare, but possible
with `touch -d`, restore-from-backup, or a filesystem that preserves
mtimes on replace — a stale marker could serve a cache hit and miss a
violation that a fresh verification would have caught. Mitigation: the
`-nt` compare is the standard bash idiom for mtime invalidation and
files are almost never touched to older mtimes in practice. This is
an accepted risk, documented here for auditability. A future PRD
could augment the check with a content-hash comparison, but the cost
of content hashing on every Edit would partially defeat the reason
caching exists.

## Origin

This standards doc was adopted on 2026-04-15 alongside the v1.6.1
hook cost reduction PRD. The pattern was first applied to
`check-required-reading.sh` and `check-phase-gate.sh` to reduce
per-Edit hook overhead during parallel `/build` waves. The broader
analysis that led to this pattern — a survey of three optimization
options (coalesce, rewrite, cache) and the reasoning for selecting
caching as the approved path — is in `spec/hook-cost-reduction-brief.md`,
and the PRD that promoted it to production is
`.etc_sdlc/features/hook-cost-reduction/spec.md`.
