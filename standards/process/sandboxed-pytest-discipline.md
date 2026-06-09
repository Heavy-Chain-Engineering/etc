# Sandboxed-pytest discipline

**A red test result from inside the agent command-sandbox is not, by itself, a
failure signal.** The sandbox can make a perfectly correct test fail for reasons
that have nothing to do with the code under test.

## Why this matters

Agent shell commands run inside a command-sandbox that denies network egress to
non-allowlisted hosts, blocks reads of protected paths (`~/.ssh`, credential
files), and restricts writes outside the project tree. A test that opens a
socket, resolves a host, reads `~/.ssh/known_hosts`, talks to a Unix socket, or
writes outside the sandbox's allowed roots will raise — **because the sandbox
refused the operation, not because the test found a bug.** Treating that red as
a genuine failure leads to two equal-and-opposite errors:

- **False alarm** — "fixing" code that was never broken, churning a correct
  implementation to satisfy a constraint the sandbox imposed.
- **Masked regression** — assuming every red is sandbox noise and waving real
  failures through. (This is the failure mode
  [`diagnostic-discipline.md`](diagnostic-discipline.md) guards against; the two
  disciplines are symmetric — never dismiss a real failure, and never trust a
  sandbox-induced one without re-running.)

## The rule

When a pytest run inside the sandbox goes red:

1. **Read the error before judging it.** Decide whether the failure is
   *sandbox-caused* or *code-caused* using the evidence markers below.
2. **If the failure is sandbox-caused, the run is inconclusive — not a failure.**
   Re-run the failing test(s) **without** the sandbox
   (`dangerouslyDisableSandbox: true`, scoped to the smallest command that
   reproduces) to obtain the true red/green verdict. Only the unsandboxed result
   is authoritative.
3. **If the failure is code-caused, it is a real failure.** Fix the code; do not
   reach for the sandbox bypass to make it "pass."
4. **Never report green from a run you know was sandbox-degraded.** "Tests pass
   except the sandbox-blocked ones" is not green — it is *unknown*. Re-run the
   blocked ones unsandboxed and report the real number.

## Evidence markers — sandbox-caused, not code-caused

A failure is sandbox-caused (inconclusive, re-run unsandboxed) when its
traceback shows one of:

- `Operation not permitted` on a file/socket operation (notably reads of
  `~/.ssh`, `~/.gnupg`, `~/.aws/credentials`, `.env*`, or other denied paths).
- A connection error to a host that is not on the network allowlist
  (`Connection refused`, `Could not resolve host`, TLS/`x509` certificate
  failures against an otherwise-reachable host, `Host key verification failed`).
- A Unix-socket connect error for a service the test would normally reach
  (Docker daemon, a local Postgres socket, etc.).
- A write rejected outside the sandbox's allowed roots (`Read-only file system`
  / `Permission denied` on a path the test legitimately owns).

Absent these markers, treat the failure as **code-caused** and fix it — do not
hide behind the sandbox.

## What this is NOT

This is not a licence to bypass the sandbox by default. Per the operator's
standing sandbox-bypass discipline, you disable the sandbox only with concrete
evidence (one of the markers above) that the sandbox is the cause — never
pre-emptively "to save time." The bypass is the *diagnostic confirmation step
for a specific failing test*, not the way you run the suite.

## See also

- [`diagnostic-discipline.md`](diagnostic-discipline.md) — the symmetric rule:
  never dismiss a real diagnostic. Sandbox noise is the one case where a red is
  legitimately inconclusive — but only after the evidence-marker check, and only
  re-run unsandboxed, never waved through.
- [`../testing/test-isolation.md`](../testing/test-isolation.md) — hermetic
  tests that avoid network/filesystem dependencies are also immune to sandbox
  noise; prefer them where practical.
