# ETC System Engineering — Project Orientation

**What this is:** The source repository for the ETC harness. Contains the
SDLC specification, hooks, agents, skills, standards, compile pipeline, and
installation tooling.

**Read order for new agents:**

1. `DOMAIN.md` — what ETC is and why it exists (business + core principles)
2. This file — where to find things in the repo
3. `spec/etc_sdlc.yaml` — the single source of truth for gates, agents,
   skills, standards, phases
4. `README.md` — quick start and lifecycle summary
5. The PRD for your task, if any, at `spec/prd-*.md` or
   `.etc_sdlc/features/<slug>/spec.md`

---

## Current Phase

v1.3 — harness evolution. Active work includes:

- `/init-project` skill (this session's rigor pass)
- Closed-loop ticket pipeline (`spec/closed-loop-ticket-pipeline.md`)
- Discovery protocol runtime (design: `spec/discovery-protocol.md`)
- v1.3 feature decomposition (`spec/prd-v1.3-features-tasks-scaling.md`)

---

## Where Things Live

| What you need | Where to find it |
|---|---|
| What ETC is and why | `DOMAIN.md` |
| This orientation doc | `PROJECT.md` |
| Agent working rules + pointers | `CLAUDE.md` (if present; otherwise baseline rules apply) |
| SDLC spec (single source of truth) | `spec/etc_sdlc.yaml` |
| PRDs for harness features | `spec/prd-v1.*.md`, `spec/*.md` |
| Per-feature work | `.etc_sdlc/features/<slug>/` (gitignored — per-session state) |
| Hand-authored skills | `skills/<name>/SKILL.md` + optional `templates/` |
| Agent definitions | `agents/<name>.md` |
| Hook scripts | `hooks/*.sh` |
| Engineering standards | `standards/<category>/*.md` |
| Test suite | `tests/test_*.py` |
| Compile pipeline | `compile-sdlc.py` (reads spec/ → writes dist/) |
| Install pipeline | `install.sh` (reads dist/ → writes ~/.claude/) |
| Utility scripts | `scripts/*.py` |
| Design notes and articles | `docs/articles/` (informal, not authoritative) |
| Process documentation | `docs/process/` |
| Compiled artifacts (gitignored) | `dist/` |

---

## Tech Stack Anchors

- **Language:** Python 3.11+ (compile pipeline, tests, utility scripts)
- **Shell:** Bash for hooks (portable; runs inside `~/.claude/hooks/`)
- **Config:** YAML (`spec/etc_sdlc.yaml`) + JSON (compiled
  `settings-hooks.json`)
- **Test runner:** pytest with parametrized cases; fixtures in
  `tests/conftest.py`
- **Type checker:** Pyright (run via `pyright <file>.py`)
- **Linter/formatter:** Ruff (`[tool.ruff]` in `pyproject.toml`)
- **No runtime service** — ETC is a compile-and-install pipeline, not a
  long-running process
- **No ORM, no database** — per-session state lives as YAML/JSON files
  under `.etc_sdlc/features/<slug>/`

---

## Install Lifecycle

```
spec/etc_sdlc.yaml              # edit the source of truth
    ↓
python3 compile-sdlc.py spec/etc_sdlc.yaml
    ↓
dist/                           # compiled artifacts (gitignored)
    ├── settings-hooks.json
    ├── agents/*.md
    ├── skills/*/
    ├── standards/**/*.md
    ├── hooks/*.sh
    ├── sdlc/
    └── templates/
    ↓
./install.sh                    # deploy to ~/.claude/ or ~/.gemini/antigravity/
    ↓
~/.claude/                      # harness is live in Claude Code
```

Running `install.sh` is always safe to re-run — it overwrites the installed
artifacts with whatever is currently in `dist/`. Edit spec, recompile,
reinstall.

---

## Running Tests

```bash
python3 -m pytest tests/ -q
```

The test suite is sandbox-clean — `pyproject.toml` excludes `.env*` from
pytest collection so runs don't need sandbox bypass flags.

---

## Role Manifests (roles/)

The `roles/` directory is where projects declare their context projections.
Starter role manifests are produced by `/init-project` Phase 4. The ETC repo
itself has not yet been dogfooded through `/init-project`, so there are no
manifests for this repo specifically; the SDLC spec and skill files
implicitly define what each built-in agent sees.

**TODO:** run `/init-project --phase=roles` against this repo to generate
proper role manifests for the ETC harness itself. (Meta-consistency:
ETC's own development should use ETC's own role projections.)

---

**Note on authorship.** This PROJECT.md was drafted during the rigor pass on
`/init-project` (2026-04-13) to unblock `tier-0-preflight` so the harness
could be modified from inside itself. The canonical flow for producing
PROJECT.md is `/init-project` Phase 2, which should be run against the ETC
repo at some point to refine this draft.
