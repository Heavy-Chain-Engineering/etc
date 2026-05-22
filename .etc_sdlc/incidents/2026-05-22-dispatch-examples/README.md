# Subagent Dispatch Examples — 2026-05-22

These files capture **exactly what a dispatched subagent receives** when /build invokes the Agent tool. Each example shows the four layers stacked in receive order:

1. **System overlay** — `hooks/inject-standards.sh` stdout. Same for every subagent.
2. **Role manifest** — `agents/<role>.md` body. Same for every dispatch of that role.
3. **Per-dispatch prompt** — what the orchestrator writes per task. Unique per invocation.
4. **`requires_reading`** — paths the agent then Reads via tool calls. The escape valve.

## Examples

| File | Role | Source dispatch | Why this example |
|---|---|---|---|
| `example-1-backend-developer-substantial.md` | backend-developer | F023 task 001 (scripts/feature_id.py extension) | Substantial implementation task; 4 ACs, 4 files in scope, TDD discipline applied, integration with existing harness scripts |
| `example-2-technical-writer-simple-adr.md` | technical-writer | F023 task 003 (ADR-F023-001 — temp-ID format) | Simple documentation task; 4 ACs, 1 file in scope, structured ADR template + alternative-analysis |

## What the property looks like in practice

The four layers are intended to be **orthogonal** (MECE / spanning):

- **System overlay** — invariant discipline (TDD, diagnostic discipline, sandbox, etc.). Not repeated in per-dispatch.
- **Role manifest** — role identity + tool budget + voice. Not repeated in per-dispatch.
- **Per-dispatch** — only the task-specific delta (scope, ACs, cross-task hazards, expected report shape).
- **`requires_reading`** — paths, not embedded content. The agent decides what to actually load.

A minor known impurity: the per-dispatch prompt sometimes restates "Dispatch hooks will enforce TDD, invariants, required reading, and phase gate — do not circumvent them." That's already in the system overlay. ~30 tokens of redundancy; non-load-bearing; flagged for future trim.

## Token rough-counts (approximate)

| Layer | Bytes | ~Tokens |
|---|---|---|
| System overlay | ~6.5 KB | ~1,600 |
| Role manifest (backend-developer) | ~8.5 KB | ~2,100 |
| Role manifest (technical-writer) | ~5.2 KB | ~1,300 |
| Per-dispatch prompt (example 1) | ~5.8 KB | ~1,400 |
| Per-dispatch prompt (example 2) | ~2.4 KB | ~600 |
| requires_reading | path-only; agent pulls on demand | varies |

A complex dispatch (backend-developer for F023 task 001) totals ~5,100 tokens of context BEFORE the agent reads any required files. A simple dispatch (technical-writer for an ADR) totals ~3,500 tokens.
