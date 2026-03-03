# agents/

**Purpose:** 23 Claude Code agent definitions that form a synthetic engineering team spanning the full SDLC. Each agent has a bounded responsibility, specific tools and model assignment, and explicit usage examples. Installed to `~/.claude/agents/` by `install.sh`.

## Key Components

### Orchestration
- `sem.md` -- Software Engineering Manager. The conductor: owns SDLC phase lifecycle, deploys agent teams, enforces Definition of Done between phases, runs quality watchdogs during Build. Model: opus, 200 max turns. Read-only (disallows Write/Edit). Uses Task tool for sub-agent delegation.

### Spec and Design
- `product-manager.md` -- Pragmatic PM. Translates business intent into structured PRDs via Socratic questioning, owns prioritization and scope. Model: opus.
- `product-owner.md` -- Stakeholder advocate. Validates PRDs for completeness, writes Given/When/Then acceptance criteria, identifies specification gaps. Model: opus.
- `researcher.md` -- Technical researcher. Deep-dives into source material (PDFs, regulations, codebases), synthesizes structured research reports with domain models and trade-off analysis. Model: opus.
- `architect.md` -- System architect. Designs boundaries, data flow, integration patterns, writes ADRs. Anti-over-engineering. Model: opus.
- `domain-modeler.md` -- Eric Evans disciple. Validates ubiquitous language, bounded context boundaries, aggregate design against the project domain model. Model: opus.
- `ux-designer.md` -- Interaction designer. Designs user flows, information architecture, interaction patterns. Accessibility-first. Model: opus.
- `ui-designer.md` -- Visual design system specialist. Translates UX wireframes into component specs with design tokens, responsive behavior, accessibility requirements. Model: opus.

### Build
- `backend-developer.md` -- Clean coder and TDD zealot. Idiomatic Python with strict typing, red/green/refactor. Model: opus, 50 max turns.
- `frontend-developer.md` -- Component thinker and accessibility zealot. TDD for accessible, performant interfaces. Model: opus, 50 max turns.
- `frontend-dashboard-refactorer.md` -- React/TypeScript dashboard refactoring specialist. Systematic, phased approach with continuous testing. Model: opus, 40 max turns.
- `devops-engineer.md` -- Infrastructure-as-code practitioner. Docker, CI/CD, monitoring, secrets management. Model: opus.
- `code-simplifier.md` -- Refactoring specialist. Transforms tangled code into maintainable solutions without changing functionality. Model: opus, 30 max turns.
- `project-bootstrapper.md` -- One-time onboarding agent. Brownfield: surveys existing code, derives `.meta/` description tree. Greenfield: scaffolds project structure, installs tooling. Model: opus, 40 max turns. Uses Task tool.

### Quality Gates
- `verifier.md` -- Mechanical quality gate. Runs tests, checks coverage, type-checks, lints. Reports pass/fail with exact numbers. Read-only (disallows Write/Edit). Model: sonnet, 15 max turns.
- `code-reviewer.md` -- Standards-driven reviewer. Mechanically checks changed files against heuristics for error handling, data integrity, code quality, and test coverage. Model: opus.
- `security-reviewer.md` -- OWASP-trained security reviewer. Reviews for injection, XSS, auth bypass, secrets, SSRF, dependency vulnerabilities. Model: opus.
- `architect-reviewer.md` -- Architectural analysis. Reviews code structure for architectural smells, coupling, cohesion, SOLID violations. Plans migration paths. Model: opus.
- `spec-enforcer.md` -- Adversarial spec compliance reviewer. Compares deliverables against PRD acceptance criteria. Assumes non-compliance until proven. Model: opus.

### Analysis
- `gemini-analyzer.md` -- Manages Gemini CLI for whole-codebase analysis exceeding Claude's context window. Leverages Gemini's 1M+ token context for sweeping pattern detection. Model: opus.
- `multi-tenant-auditor.md` -- SaaS/multi-tenant code auditor. Analyzes tenant isolation, RLS policies, data leakage risks. Model: opus.
- `process-evaluator.md` -- Data-driven process analyst. Collects metrics (coverage, defect rate, rework rate, velocity), produces retrospective reports. Model: opus.
- `technical-writer.md` -- Docs-as-code practitioner. Writes API docstrings, architecture overviews, setup guides, READMEs, `.meta/` descriptions. Model: opus.

## Dependencies
- Claude Code agent runtime with Agent Teams enabled
- Each agent reads standards from `~/.claude/standards/` before producing output
- SEM agent depends on `.sdlc/tracker.py` for phase state
- Build agents depend on TDD hooks in `~/.claude/hooks/`
- Several agents use spec-kit (`/specify`) or TaskMaster MCP server

## Patterns
- **YAML frontmatter + markdown body:** Every agent file has frontmatter (`name`, `description`, `model`, `tools`, `maxTurns`, optionally `disallowedTools`) followed by a markdown system prompt.
- **Usage examples in description:** Each description includes `<example>` blocks with `Context`, `user`, `assistant`, and `<commentary>` tags for Claude's routing.
- **Read-before-act:** Every agent's prompt begins with a "Before Starting (Non-Negotiable)" section listing files to read for context.
- **Review-only agents:** Quality gate agents (verifier, SEM) use `disallowedTools: [Write, Edit, NotebookEdit]` to prevent them from modifying code.
- **Model stratification:** Most agents use opus; lightweight agents (verifier) use sonnet to optimize cost.

## Constraints
- Agent names must be kebab-case and match the `name` field in frontmatter.
- Each agent has exactly one bounded responsibility -- agents must not overlap (e.g., code-reviewer does NOT do security review; security-reviewer does NOT do architecture review).
- No agent may bypass the SEM's phase transition authority.
- Build agents must follow TDD (red/green/refactor) -- the hooks enforce this mechanically.
- All agents must read applicable engineering standards before starting work.
