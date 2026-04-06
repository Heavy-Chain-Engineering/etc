# Release Notes

## 2026-04-06 — etc v1.3: The Full Pipeline

**etc** (Engineering Team, Codified) is a harness for Claude Code that enforces
software engineering best practices through deterministic hooks, LLM-based
judgment gates, and a declarative SDLC specification. Instead of relying on the
AI to follow standards, the harness makes it mechanically impossible to skip them.

**Repo:** https://github.com/Heavy-Chain-Engineering/etc

### What It Does

You type `/spec "what you want to build"` — the harness runs a Socratic loop,
researches your codebase and the web, surfaces ambiguous decisions (gray areas),
and generates an implementation-ready PRD.

Then you type `/build` — the harness validates the spec, recursively decomposes
it into right-sized tasks (arbitrary depth), plans execution waves, dispatches
subagents wave-by-wave, verifies after each wave, and reports results. Every
step is checkpointed and resumable.

Every file edit is gated by deterministic hooks: TDD enforcement (test must exist
before source), architectural invariants, required reading checks, phase-aware
file gating, dangerous command blocking. The agent can't skip steps because the
hooks fire whether it wants them to or not.

### By the Numbers

- **14** enforcement gates across 10 Claude Code hook events
- **9** hook scripts (deterministic bash, <1s each)
- **7** skills: `/spec`, `/build`, `/decompose`, `/implement`, `/tasks`, `/postmortem`, `/checkpoint`
- **4** artifact templates (ADR, agent, task, invariant)
- **148** tests, all passing in ~4 seconds
- **1** declarative YAML spec (`etc_sdlc.yaml`) that compiles to everything

### The Pipeline

```
/spec "add user authentication"
  → Socratic questions → codebase research → web research
  → gray area resolution → PRD section-by-section → Definition of Ready check
  → "This PRD is solid. Shall I /build it?"

/build .etc_sdlc/features/auth/spec.md
  → validate → decompose → score (any task > 7? decompose further)
  → plan waves → execute wave 0 → verify → execute wave 1 → verify → ...
  → final CI → verification report
  → "Build complete. 47 tests pass, 98% coverage. Ready to commit."
```

### Key Capabilities

**SDLC-as-Code.** The entire harness is defined in a single YAML file
(`spec/etc_sdlc.yaml`). A compiler reads it and emits Claude Code hooks,
agent definitions, skill files, standards, and templates. Change the YAML,
recompile, reinstall. One source of truth.

**Hierarchical decomposition.** Tasks too complex for a single agent session
get recursively broken into subtasks (001 → 001.001 → 001.001.001). The system
keeps decomposing until every leaf scores ≤ 7 on the complexity scale. This is
how you build arbitrarily large systems with AI agents.

**Wave-based execution.** Tasks are grouped into parallel execution waves by
dependency analysis. Within a wave, tasks run in parallel (file-set isolated).
Between waves, verification runs to catch regressions early. A failure stops
the pipeline — fail early and loud.

**Adversarial review.** A fresh agent with no implementation context reviews
every subagent's output with hostile intent — looking for what's wrong, not
confirming what's right. Never let an agent grade its own work.

**Antipatterns learning loop.** When bugs escape, `/postmortem` traces them to
root cause and appends prevention rules to `.etc_sdlc/antipatterns.md`. Every
future spec and subagent reads this file. The system gets smarter over time.

**Three-layer enforcement:**
- Command hooks (deterministic, <1s) — TDD, invariants, dangerous commands
- Prompt hooks (Sonnet, ~5s) — Definition of Ready, task readiness
- Agent hooks (Sonnet + tools, ~60s) — CI pipeline, adversarial review

### Quick Start

```bash
git clone https://github.com/Heavy-Chain-Engineering/etc.git
cd etc
python3 compile-sdlc.py spec/etc_sdlc.yaml
./install.sh   # Choose Claude Code
# Restart Claude Code
/spec "your feature idea"
```

### Inspired By

Built on ideas from [Correctless](https://github.com/joshft/correctless) (adversarial
review, antipatterns loop), [Armature](https://github.com/dsmedeiros/armature-public)
(templates, governance journal, checkpoint protocol), [GSD](https://github.com/itsjwill/gsd-pro)
(wave execution, context engineering), and [Spec Kitty](https://github.com/Priivacy-ai/spec-kitty)
(per-feature artifact directories).

### Philosophy

AI coding assistants are smart enough to do good work, but they skip steps.
In a real engineering team, you don't rely on individual discipline — you build
systems. This harness applies the same principle: CI pipelines that block red
builds, code review that requires approval, sprint planning that rejects vague
tickets. The discipline is in the process, not the person.

We never swallow errors. We never lower the bar on the second attempt. We fail
early and loud.

MIT License.
