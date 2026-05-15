# Codebase Navigation — LSP first, grep second

When navigating an unfamiliar codebase, use LSP (Language Server Protocol)
operations as the FIRST choice for any symbol-anchored question. Fall back
to grep/find/Read only when LSP doesn't apply (textual search, glob
patterns, non-symbol queries).

LSP returns only the references that point to the same symbol — false-
positive filtering happens before you read anything. Grep across 4,000
files for the substring `foo` returns variable names, comments, string
literals, irrelevant matches in unrelated languages. LSP for the symbol
`foo` returns exactly the call sites of that symbol.

Source: Anthropic's *How Claude Code Works in Large Codebases* (2026):
> *"LSP returns only the references that point to the same symbol, so
> the filtering happens before Claude reads anything."*

## When to use LSP

| Question | LSP operation |
|---|---|
| Where is this function/class/variable defined? | `goToDefinition` |
| Who calls this function? Who uses this symbol? | `findReferences` |
| What does this function call? | `outgoingCalls` (after `prepareCallHierarchy`) |
| Who calls this function? (semantic, not textual) | `incomingCalls` (after `prepareCallHierarchy`) |
| Who implements this interface / abstract method? | `goToImplementation` |
| What type / docstring does this symbol have? | `hover` |
| What are all the symbols defined in this file? | `documentSymbol` |
| Find a symbol by name across the entire project | `workspaceSymbol` |

All LSP operations require: `filePath`, `line` (1-based), `character` (1-based).

## When to use grep / find / Read instead

LSP doesn't help for:

- **Textual patterns** — error messages, log strings, version numbers, magic constants. Use `grep`.
- **Glob-based file discovery** — find every `*.yaml` under `.etc_sdlc/features/`. Use `find` or `Glob`.
- **Non-code files** — Markdown, YAML, JSON, plain text. LSP doesn't index these. Use `grep` or `Read`.
- **Cross-language search** — LSP servers are typically per-language; searching across Python + Bash + Markdown wants `grep`.
- **Comments + docstrings** — LSP returns symbol references, not text inside comments. Use `grep` if the target is in prose.
- **You already know the file path and want the full content** — just `Read` it.

## Fallback chain

1. **Question references a symbol?** (function, class, variable, type)
   → Try LSP first. Use `workspaceSymbol` to locate the symbol if you
   don't know which file. Use `findReferences` / `goToDefinition` /
   `hover` from there.

2. **LSP returns no server / no results / the file isn't covered by
   any configured LSP?** → Fall back to `grep` with the symbol's
   textual form as the search pattern.

3. **Question is textual, not symbolic?** → Skip LSP. Go directly to
   `grep` / `Read` / `Glob`.

## Cross-project / cross-repo navigation

For navigation across multiple repositories (e.g., HCE customer
engagements where an operator works on several codebases in one
session), the **Serena MCP server** is a relevant alternative. Serena
provides LSP-backed semantic search across multiple repos with
embeddings-based similarity ("find a function with this shape across
all my projects"). Serena is operator-configured and not always
available; check before relying on it.

Built-in LSP is sufficient for single-repo navigation (which is the
common case for etc-driven work).

## Why this matters

Symbol-anchored navigation:

- **Reduces context waste.** A `grep` for `process_payment` might return
  60 matches across documentation, comments, test fixtures, and three
  unrelated functions named similarly. LSP `findReferences` returns
  exactly the 12 call sites of the actual symbol.

- **Eliminates a class of false-positive bugs.** Textual matching across
  shared names ("`Order` model" vs "`Order` enum value" vs "`order_by`
  parameter") often surfaces the wrong site. LSP knows which `Order`
  you meant.

- **Scales to large codebases.** Anthropic's article specifically names
  LSP as part of how Claude Code works on large codebases. The
  efficiency gain compounds with codebase size — at 100 files, grep is
  fine; at 10,000 files, LSP is the only viable approach.

## Anti-pattern

Don't preemptively grep when you have a symbol name and a probable
file. The pattern `grep -r "function_name" .` across a project is
*always* worse than `LSP workspaceSymbol function_name` if the file
type has an LSP server. The exception is when you genuinely don't know
whether the target is a symbol or a string (e.g., investigating a log
message that might also be a function name) — in that case, try LSP
first; if it returns nothing, grep covers both cases.

## Required reading

Agents that do code investigation (researcher, code-reviewer, architect,
architect-reviewer, code-simplifier, spec-enforcer) should treat this
document as required reading before any non-trivial codebase navigation
task.
