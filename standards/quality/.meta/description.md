# standards/quality/

**Purpose:** 1 quality standard that defines the metrics tracked by the process-evaluator agent for measuring engineering health, process efficiency, and team velocity across projects.

## Key Components
- `metrics.md` -- (Status: REFERENCE) Defines three metric categories. Code Quality: test coverage percentage (98% threshold), coverage trend, mypy error count (0 threshold), ruff violation count (0 threshold), cyclomatic complexity (average and max per module). Process Quality: spec-to-implementation fidelity, defect rate (review bugs vs. production bugs), regression frequency, TDD compliance (PreToolUse hook hit rate). Velocity: tasks completed per sprint, time from spec to implementation, review cycle time (PR open to merge). Reporting: periodic reports comparing current vs. baseline vs. previous period, with trend direction as the primary signal.

## Dependencies
- Referenced by `process-evaluator.md` agent definition
- Code quality metrics enforced by `hooks/verify-green.sh` (coverage, mypy, ruff)
- In the v2 platform, metrics are computed by `platform/src/etc_platform/metrics.py` (token usage, agent velocity, phase durations, guardrail stats)

## Patterns
- **Trend over absolute:** The standard emphasizes "Are we getting better?" -- trend direction matters more than absolute numbers at any point in time.
- **Multi-dimensional health:** Quality is measured across three axes (code, process, velocity) to prevent optimizing one at the expense of others.

## Constraints
- This is the only REFERENCE (not MANDATORY) standard in the quality category -- it defines what to measure, not hard thresholds to enforce.
- Coverage, type safety, and lint thresholds are enforced elsewhere (testing standards, typing standards, hooks) -- this standard defines the metrics framework for tracking and reporting.
