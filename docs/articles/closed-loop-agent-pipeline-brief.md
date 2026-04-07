# Blog Article Brief: The Closed-Loop Agent Pipeline

## What Happened (Anonymized)

An engineering team building an SDLC-as-Code platform — a system where software
development lifecycle rules are expressed as declarative YAML, compiled into
deterministic hooks, governance gates, and agent orchestration harnesses — made
an unexpected connection.

The team had separately:

1. **Built an SDLC harness** that enforces specification quality before allowing
   implementation. If a ticket doesn't meet "Definition of Ready" (clear
   acceptance criteria, bounded scope, no ambiguity that would force the agent to
   guess), the harness rejects it. The harness includes deterministic pre-commit
   hooks, invariant registries, mandatory test coverage gates, and agent role
   declarations that constrain what each agent can and cannot do.

2. **Connected a task tracker (Linear) to their AI coding agent (Claude Code)
   via MCP** (Model Context Protocol) — giving the agent direct read/write
   access to the project's issue tracker.

3. **Had subject matter experts (SMEs) filing tickets** in that same tracker —
   people who understand the domain but aren't engineers.

The realization: **these three things close a loop that removes the engineering
team as an intermediary.**

## The Architecture

```
SME files ticket in Linear
        |
        v
Claude pulls ticket via MCP
        |
        v
SDLC harness evaluates Definition of Ready
        |
        +--- PASSES --> Decompose, implement, test, deploy
        |
        +--- FAILS  --> Reject BACK TO SOURCE
                        |
                        v
                Update Linear ticket with specific questions
                Move status to "Needs Clarification"
                SME sees questions, refines, resubmits
```

**The key insight is source-aware rejection.** The harness already had rejection
logic ("this isn't well-specified enough to build"), but it only reported inline
to the engineer in the conversation. The new capability routes rejections back
through the originating channel:

- **Source = direct conversation:** Tell the human inline
- **Source = Linear ticket:** Comment on the ticket with specific questions,
  move it to "Needs Clarification" status
- **Source = [future: Slack, GitHub Issues, email]:** Same pattern, different
  transport

## Why This Matters

### The Translation Layer Problem

In traditional software teams, engineers act as a **translation layer** between
domain experts and code:

1. SME describes what they need (often vaguely)
2. Engineer asks clarifying questions (days of back-and-forth)
3. Engineer writes a spec (internal translation)
4. Engineer implements (finally, code)
5. SME reviews and says "that's not what I meant" (cycle repeats)

Steps 2-3 are pure intermediation. If the system receiving the work can ask its
own clarifying questions — through the same channel the SME already uses — the
human engineer's role as translator evaporates.

### What Makes This Work (Not Just Hype)

This isn't "just connect an LLM to Jira." Three specific things make it viable:

1. **Deterministic governance, not vibes.** The SDLC harness isn't "try your
   best." It's compiled YAML that produces shell-executable hooks. A pre-commit
   hook that checks for test coverage doesn't hallucinate. An invariant registry
   that enforces consistent terminology across bounded contexts doesn't drift.
   The deterministic scaffolding constrains the non-deterministic agent.

2. **Definition of Ready as a first-class gate.** The harness has an explicit,
   mechanically-evaluated quality bar for incoming work. Vague tickets don't
   silently produce vague implementations — they bounce back with specific
   questions. This is the difference between an agent that guesses and an agent
   that asks.

3. **Bidirectional MCP connection.** The agent doesn't just read tickets — it
   writes back to them. Comments, status changes, clarifying questions. The SME
   never leaves their natural habitat (the task tracker). The feedback loop is
   native to their existing workflow.

### The Shift-Left Insight

Once you have source-aware rejection, the next obvious move is **preventing bad
tickets at the source.** The team created:

- **Structured ticket templates** that front-load the information the harness
  needs (current behavior, desired behavior, acceptance criteria)
- **A ticket writing guide** written for domain experts, not engineers
- **Workflow states** that make the feedback loop visible ("Needs Clarification"
  as a first-class status)

This is the same principle as input validation at the UI layer vs. catching
errors in business logic — it's cheaper to prevent bad input than to reject it.

## The Implications

### For Engineering Teams
The role shifts from "translate requirements and write code" to "build and
maintain the harness that enables autonomous implementation." You're not
writing features — you're writing the system that writes features.

### For Domain Experts / SMEs
They get faster feedback, in their own tool, in their own language. No more
"I filed this three weeks ago and haven't heard anything." The system either
builds it or asks specific questions within minutes.

### For the SDLC-as-Code Movement
This is the forcing function for rigorous SDLC specification. If your lifecycle
rules are informal ("we usually do code review"), they can't be compiled into
agent constraints. If they're formal and deterministic, they become the
guardrails that make autonomous implementation safe.

### The Paradox
**More governance enables more autonomy.** The stricter the harness, the less
human oversight each individual ticket needs. The engineering team's discipline
in specifying their own process is what allows them to step back from
ticket-by-ticket implementation.

## Key Concepts for the Article

- **Closed-loop ticket pipeline** — SME to agent to code to deployment, with
  rejection routing back to the source
- **Source-aware rejection** — the agent knows where work came from and rejects
  through that channel
- **SDLC-as-Code** — lifecycle rules as compiled, deterministic artifacts (not
  suggestions)
- **Deterministic scaffolding for non-deterministic agents** — hooks don't
  hallucinate, invariants don't drift
- **Disintermediation of the translation layer** — engineers stop translating
  between domain experts and code
- **Shift-left ticket quality** — templates and guides that prevent rejection
  before it happens
- **The governance-autonomy paradox** — more process rigor = less human
  oversight needed per ticket

---

## Prompt for AI to Write the Blog Article

```
Write a compelling, technically credible blog article (1500-2000 words) based on
the brief below. The audience is senior engineering leaders and technical
founders who are experimenting with AI-assisted development but haven't yet
achieved autonomous implementation pipelines.

Tone: Confident and opinionated, but grounded in real architecture — not hype.
Think "staff engineer writing on their personal blog," not "marketing team
writing a product announcement." Use concrete examples, not abstract promises.
Show the architecture, not just the vision.

Structure:
1. Open with the "aha moment" — the realization that three separately-built
   capabilities (SDLC harness, MCP connection to task tracker, SMEs filing
   tickets) accidentally close a loop that removes engineers as intermediaries
2. Explain the architecture with the flow diagram
3. Deep-dive on WHY this works — the three prerequisites (deterministic
   governance, Definition of Ready gate, bidirectional MCP)
4. Address the "isn't this just connecting an LLM to Jira?" objection head-on
5. The shift-left insight (preventing bad tickets > rejecting bad tickets)
6. The governance-autonomy paradox (more process rigor = more agent autonomy)
7. Implications for engineering teams, SMEs, and the SDLC-as-Code movement
8. Close with: what the engineering team's role becomes (building the harness,
   not building features)

Do NOT:
- Use the phrase "game changer" or "paradigm shift"
- Promise that this eliminates engineers entirely — it changes what they do
- Use generic AI hype language ("revolutionary", "transformative", "unleash")
- Reference specific vendor names for the task tracker or AI tool — keep it
  pattern-focused

DO:
- Include the ASCII flow diagram from the brief
- Use the "Translation Layer Problem" framing
- Emphasize that deterministic hooks are what make non-deterministic agents safe
- Include the paradox framing: "More governance enables more autonomy"
- Make it clear this is a real architecture someone built, not a thought
  experiment

[BRIEF]:
{paste the full brief above}
```
