# ADR-003: Client-Side Polling Instead of WebSockets

## Status: Accepted
## Date: 2026-02-25

## Context
The dashboard needs to reflect changes to the underlying JSON files. Options: WebSockets for push updates, Server-Sent Events, or client-side polling.

## Decision
Use client-side polling via `setInterval` every 5 seconds. The JavaScript fetches `/api/state` and `/api/tasks` and re-renders the DOM.

## Consequences
- **Pro:** Simplest implementation — no WebSocket library, no connection management
- **Pro:** PRD explicitly states "polling every 5s is fine"
- **Pro:** Resilient — if server restarts, next poll picks up automatically
- **Con:** Up to 5s delay before changes appear
- **Accepted risk:** 5s latency is acceptable for a development monitoring tool
