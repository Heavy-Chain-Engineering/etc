# Stakeholder Meeting Guide: Requirements Intake

A structured guide for extracting system specifications from PMs and SMEs. Designed to produce complete, testable, unambiguous inputs for any engineering process — human or AI-assisted.

## Your Role

You're extracting what's in people's heads and turning it into something an engineering team can build from. PMs know the problem and priorities. SMEs know the domain and edge cases. Neither will volunteer everything unprompted. Your job is to ask the right questions in the right order.

## Phase 1: Project Classification (5 min)

Get this nailed down first — it changes everything downstream.

**Ask:**
- "Is this greenfield, brownfield, re-engineering, lift-and-shift, or consolidation?"
- "What exists today? Code? Spreadsheets? PDFs? Tribal knowledge?"
- "What's the desired end state in one sentence?"

**Why it matters:** A greenfield project needs architecture decisions. A re-engineering project needs anti-pattern guards. A lift-and-shift needs compatibility constraints. Classification determines what questions matter next.

## Phase 2: Source Material Inventory (10 min)

Before anyone can build, they need to know what reference material exists and how to read it.

**For each document/system/artifact, capture:**

| Field | Ask This |
|-------|----------|
| **Name** | "What do you call this?" |
| **Type** | pdf / code / export / spreadsheet / document / API? |
| **Classification** | Business operations? Requirements? Implementation artifact? Domain truth? |
| **Priority** | Is this the primary source of truth, or supporting context? |
| **Reading instructions** | "How should someone unfamiliar interpret this? What's misleading or outdated in it?" |

**The killer question:** *"If an engineer misread this document, what's the most expensive mistake they'd make?"* — this surfaces the reading instructions the SME carries in their head but never writes down.

## Phase 3: Domain Language (10 min)

Every miscommunication between business and engineering starts with terminology. Fix it here.

**Ask the SME:**
- "What are the 5-10 key entities in this domain?" (e.g., Vendor, Policy, Claim, Endorsement)
- "Which terms do people confuse or use interchangeably but shouldn't?"
- "Are there terms that mean different things in different contexts?" (bounded context boundaries)
- "What are the relationships that matter?" (A Vendor *has many* Policies, a Policy *covers* one or more Locations)

**Ask for the axioms** — things that are ALWAYS true:
- "What business rules are non-negotiable? The ones that if violated mean the system is wrong?"
- Example: *"A policy can never have a negative premium"* or *"Every vendor must have at least one active license"*

**Why it matters:** Axioms are your cheapest quality gate. They're binary — either the system respects them or it's wrong. Every axiom you capture here is a bug you'll never ship.

## Phase 4: Problem Statement + Success Criteria (10 min)

Extract the problem, not the solution. PMs and SMEs will naturally jump to solutions — your job is to pull them back.

**Ask the PM:**
- "What user problem does this solve? Who experiences it and how often?"
- "What happens today without this? What's the cost of doing nothing?"
- "How will we know this succeeded? What metric moves?"
- "What's the simplest version that solves the core problem?"

**Ask the SME:**
- "What are the error states? When does this process fail today?"
- "What are the edge cases that always bite you?"
- "What's the data volume? How many records, how often, peak load?"

**Red flags to push back on:**
- "We need it to be fast" -> *"What does fast mean? Sub-second? Sub-minute?"*
- "It should be user-friendly" -> *"What specific task should take fewer than N clicks?"*
- "Handle all the cases" -> *"List the top 5 cases. We'll scope from there."*

Adjectives are not requirements. Numbers are requirements.

## Phase 5: Acceptance Criteria Seeds (10 min)

You won't write final acceptance criteria in the meeting, but you need seeds — concrete scenarios that anchor the spec.

**For each major capability, ask:**
- "Given [starting state], when the user does [action], what should happen?"
- "What should definitely NOT happen?" (negative requirements)
- "What's the rollback plan if this goes wrong?"

**Template to fill in the meeting:**
```
AC-1: [Happy path]
  Given ________
  When ________
  Then ________

AC-2: [Error state]
  Given ________ fails
  When ________
  Then ________

AC-3: [Edge case]
  Given ________ (boundary condition)
  When ________
  Then ________
```

Get at least 3 per major capability. One happy path, one error, one edge case. These become the test oracle — if you can't write the acceptance criteria, the requirement isn't understood yet.

## Phase 6: Constraints + Non-Negotiables (5 min)

**Ask both:**
- "What can we absolutely NOT change?" (regulatory, contractual, technical)
- "What systems does this integrate with? What are their limitations?"
- "Are there security/compliance requirements?" (PII, audit trails, SOC2, HIPAA)
- "What's the timeline? Is there a hard deadline or external dependency?"

Constraints are more valuable than features. A feature can be descoped. A constraint that's discovered late blows up the architecture.

## Checklist: Leave the Meeting With

- [ ] Project classification (greenfield/brownfield/re-engineering/etc.)
- [ ] Source material inventory (name, type, classification, priority, reading instructions)
- [ ] Domain glossary (entities, relationships, synonyms to avoid)
- [ ] Domain axioms (invariants — things that are ALWAYS true)
- [ ] Problem statement (who, what problem, frequency, cost of inaction)
- [ ] Success metrics (measurable numbers, not adjectives)
- [ ] 3+ acceptance criteria seeds per capability (happy path, error, edge case)
- [ ] Constraints (regulatory, integration, security, timeline)
- [ ] Error states and edge cases the SME knows about
- [ ] Performance requirements (with numbers)

If you're missing any of these, you'll be guessing during implementation. Better to schedule a 15-minute follow-up than to build on assumptions.

## After the Meeting

Capture raw notes immediately — don't wait. Structure them into:

1. **Project brief** — classification, one-sentence end state, constraints
2. **Source material index** — inventory table with reading instructions
3. **Domain model draft** — glossary, entity relationships, axioms
4. **Problem + success criteria** — problem statement, metrics, acceptance criteria seeds

This raw capture is the input to your spec process — whether that's a PM writing a PRD, a team writing user stories, or an AI agent generating structured specifications.

## What Matters Most

The most valuable things to extract are **reading instructions** and **domain axioms**.

Reading instructions prevent the most expensive class of mistake: misinterpreting source material. When an SME says "ignore columns F through J, those are legacy" — that's worth more than any feature description.

Axioms are your cheapest quality gate. They're binary, testable, and domain-permanent. Everything else can be refined iteratively, but wrong axioms or misread sources compound through every phase of development.
