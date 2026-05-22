# ADR-002: typer + rich for CLI and terminal UX

**Date:** 2026-05-22
**Status:** Accepted

**Context:** The Python installer needs argv parsing (preserve the byte-for-byte `--client`, `--scope`, `--help` surface from install.sh per spec BR-004) and rich terminal UX (status lines with ✓/⚠/✗, interactive y/N prompts for status-line + sandbox-config, optional progress feedback). Three candidate stacks:

- (a) typer (FastAPI-style on click) + rich — type-hint-driven argv, first-class rich integration since typer 0.12 (auto-styled --help, panel rendering).
- (b) raw click + rich — manual wiring between click decorators and rich console output.
- (c) argparse (stdlib) + print — no third-party additions, but no rich UX.

**Decision:** typer >= 0.12, rich >= 13.7.

**Consequences:**
- *Easier*: Type hints drive argv parsing; the project's Python 3.11+ typing-everywhere convention extends naturally. typer's `--help` output is rich-styled by default. rich.Prompt.ask provides the y/N flow for BR-007 and BR-008 prompts.
- *Harder*: Two new runtime dependencies (typer, rich) beyond the existing pyyaml. Adds ~10MB to the uv-managed environment.
- *Deferred*: TUI wizard with multi-step screens (rich supports it via Live and Progress; out-of-scope per spec).
- *Cannot defer*: typer 0.12+ pin because earlier versions have weak rich integration. rich 13.7+ pin because Console.color_system property landed there.

**Related ADRs:** ADR-001 (uv bootstrap — these libraries live in the uv-managed environment, not pip-installed); ADR-005 (banner — uses rich.Console for non-banner output but bypasses it for the banner write).
