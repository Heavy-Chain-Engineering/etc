# Quality Metrics

## Status: REFERENCE
## Applies to: Process Evaluator

## Tracked Metrics

### Code Quality
- **Test coverage:** Line and branch coverage percentage (threshold: 98%)
- **Coverage trend:** Is coverage increasing, stable, or decreasing over time?
- **Type safety:** mypy error count (threshold: 0)
- **Lint violations:** ruff error count (threshold: 0)
- **Cyclomatic complexity:** Average and max per module

### Process Quality
- **Spec-to-implementation fidelity:** Does the code match the PRD/acceptance criteria?
- **Defect rate:** Bugs found in review vs. bugs found in production
- **Regression frequency:** How often do previously-passing tests break?
- **TDD compliance:** Was the red/green cycle followed? (PreToolUse hook hit rate)

### Velocity
- **Tasks completed per sprint**
- **Time from spec to implementation**
- **Review cycle time** (time from PR open to merge)

## Reporting
- Process Evaluator produces periodic reports (weekly or per-sprint)
- Reports compare current metrics to baseline and previous period
- Trend direction matters more than absolute numbers
- "Are we getting better?" is the core question
