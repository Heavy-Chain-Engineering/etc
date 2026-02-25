# etc — Engineering Team, Codified

An industrial-grade coding harness that establishes a synthetic engineering organization for AI-driven software development.

## What Is This?

A complete set of AI agents, engineering standards, enforcement hooks, and workflow conventions that replicate the discipline of a well-run human software team — applied to Claude Code.

**15 specialized agents** covering the full SDLC: product management, UX/UI design, architecture, domain modeling, backend/frontend development, code review, QA verification, security review, DevOps, technical writing, process evaluation, and brownfield bootstrapping.

**Engineering standards as files** — not buried in prompts. TDD workflow, clean code, testing standards, security checklists, architecture rules — each independently maintainable and versionable.

**Mechanical enforcement** via hooks and CI — not just documentation. Tests must pass, coverage must meet threshold, standards must be followed. The system self-corrects.

## Architecture

Two-layer platform:

- **User-level (`~/.claude/`)** — Agents, standards, hooks. Reusable across all projects. Improvements propagate everywhere.
- **Project-level (`.claude/`, root files)** — Domain standards, CI pipeline, project config. Per-repo, checked into version control.

## Connection to ISS

This harness is the first practical instantiation of [Industrialized System Synthesis](docs/plans/2026-02-25-coding-harness-design.md#connection-to-industrialized-system-synthesis) — a declarative approach where specs act as genotype and agent swarms express them into running systems (phenotype).

## Status

Design complete. Implementation pending.

- [Full Design Document](docs/plans/2026-02-25-coding-harness-design.md)
- [Design Notes](docs/plans/harness-design-notes.md)

## First Deployment Target

[Bald Eagle](https://github.com/inchoate/bald-eagle) — NovaSterilis regulatory compliance platform.
