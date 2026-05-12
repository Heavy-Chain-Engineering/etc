# ADR-F011-002: File-watch JSON contract for browser-extension → /design handoff

**Date:** 2026-05-11
**Status:** Accepted

**Context:**
Impeccable's browser extension produces designer-iteration decisions (variant choices, token tweaks, component refinements) during live design work. /design needs to ingest those decisions and update its state.yaml. Four protocols were considered for the browser-extension → /design handoff: (a) file-watch on a known JSON path (impeccable's browser extension writes; /design polls or pull-triggers reads); (b) MCP server (impeccable browser extension exposes an MCP endpoint, /design queries via Model Context Protocol); (c) polling REST endpoint (impeccable browser extension runs a local HTTP server, /design polls); (d) manual sync (designer exports decisions, operator imports via /design CLI flag).

The deciding force is **simplicity vs feature richness**. MCP is standardized but requires upstream impeccable to build/maintain an MCP server (no commitment from pbakaus). Polling REST introduces port-conflict and firewall surface. Manual sync has the highest UX friction (designer must remember to export).

**Decision:**
File-watch on a known JSON path. Impeccable's browser extension writes designer-decision deltas to either `~/.impeccable/last-session.json` (cross-feature, default for most setups) or `<feature_path>/design-iteration.json` (per-feature; operator-selectable via `--sync-from <path>`). /design reads at Phase 5 entry AND on `/design --sync` operator command — **pull-triggered, NOT a continuous watcher daemon**.

The JSON schema is minimal (see ADR-F011-004): `{ session_id: str, decisions: [{ token_or_component: str, value: any, decided_at: ISO-8601 }] }`.

MCP server, polling REST, and manual sync are explicitly out of scope for F011.

**Consequences:**
- **Easier:** Cross-platform via filesystem (no port conflicts, no firewall surface); no daemon to manage; aligns with impeccable's likely existing local-persistence pattern; no upstream impeccable commitment required beyond writing the JSON file.
- **Harder:** Pull-triggered means designers can drift if they forget `/design --sync`; latency between browser-extension write and /design read; documented as Edge Case 6 in the F011 spec ("Designer iterates in browser extension but never invokes `/design --sync`").
- **Deferred:** Continuous filesystem watcher (`watchdog` library); MCP server integration; multi-designer concurrent sync.
- **Cannot defer:** The schema decision — locked in ADR-F011-004 to allow implementation to proceed.
- **Related ADRs:** ADR-F011-004 (minimal schema) governs the JSON shape. ADR-F011-005 (partial wrap) constrains what /design does with the synced decisions.
