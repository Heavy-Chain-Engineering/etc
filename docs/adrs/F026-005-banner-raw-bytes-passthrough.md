# ADR-005: Banner via raw-bytes passthrough, bypassing rich.Console

**Date:** 2026-05-22
**Status:** Accepted

**Context:** `assets/etsy-logo.ascii` is the pre-rendered jp2a ANSI-truecolor output of the etc logo (67 lines, ~49KB of `\x1b[38;2;R;G;Bm<char>\x1b[0m` per-pixel sequences). The banner step at the top of `install` must print these bytes faithfully.

Rich's `Console.print(...)` does NOT pass arbitrary ANSI escapes through. It expects rich-markup syntax (`[bold red]text[/]`) and re-renders escapes against its own color-system model. Feeding raw jp2a bytes into Console.print produces visible escape-code text and color rendering noise.

Three candidates:

- (a) `sys.stdout.buffer.write(banner_bytes)` — raw bytes to the underlying file descriptor. No re-interpretation possible.
- (b) `Console(highlight=False, markup=False, soft_wrap=True).print(banner_str)` — rich Console with all interpretation flags off.
- (c) Pre-process the jp2a output into rich-markup syntax — translate every `\x1b[38;2;R;G;Bm` sequence into `[rgb(R,G,B)]...[/]` markup, then `Console.print`.

**Decision:** Option (a). `etc_installer/banner.py` reads `assets/etsy-logo.ascii` with `Path.read_bytes()` and writes via `sys.stdout.buffer.write(banner_bytes)`, gated by `sys.stdout.isatty()`. All other installer output (status lines, prompts, errors) routes through rich.Console normally.

**Consequences:**
- *Easier*: The banner renders byte-identical to what jp2a emits, on every terminal that handles ANSI truecolor. No translation layer, no risk of rich re-interpretation. The banner module is ~20 lines.
- *Harder*: On terminals that don't handle ANSI truecolor (e.g., `TERM=dumb`, rendering through `less`), the operator sees raw escape sequences. Documented in spec Edge Case 9 as a known limitation; out-of-scope to fall back to a plain-text logo for v1.
- *Deferred*: Plain-text logo fallback for non-truecolor terminals. Operator opt-out via env var (TTY-gating is sufficient for v1; persistent off-switch is a follow-up).
- *Cannot defer*: TTY-gating MUST be honest. `sys.stdout.isatty()` is the canonical check; rich.Console.is_terminal is a wrapper that delegates to the same. CI runs, pipes, and redirects produce isatty() == False and the banner is skipped.

**Related ADRs:** ADR-002 (typer + rich — rich.Console is the canonical output channel for everything BUT the banner).
