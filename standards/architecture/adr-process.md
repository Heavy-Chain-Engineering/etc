# Architecture Decision Record Process

## Status: MANDATORY
## Applies to: Architect

## When to Write an ADR
- Technology choice (framework, library, database)
- Architectural pattern decision (monolith vs services, sync vs async)
- Data model design choice
- Integration pattern selection
- Any decision that constrains future development

## ADR Template

```markdown
# ADR-NNN: [Title]

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Superseded by ADR-NNN
**Context:** [What is the situation? What forces are at play?]
**Decision:** [What did we decide? Be specific.]
**Consequences:** [What are the trade-offs? What becomes easier? Harder?]
```

## Rules
- ADRs live in `docs/adr/` and are numbered sequentially
- Accepted ADRs are immutable — don't edit them
- To change a decision, create a new ADR that supersedes the old one
- Reference the superseded ADR in the new one
- ADRs are short (1 page max). If it's longer, the decision is too complex — break it down.
