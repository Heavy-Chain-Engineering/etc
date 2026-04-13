# Role Manifests

Role manifests declare **what files an agent of a given role sees by
default**, and **what additional files that agent is allowed to request**
through the discovery protocol when its default projection is insufficient
mid-task.

Each manifest is a YAML file describing one role. The runtime uses it to
build a deterministic context projection from `(role, task)` before the
agent runs.

Manifests use the **soft-POLA** pattern: `default_consumes` (narrow starting
projection) plus `discovery.allowed_requests` (structured widening). There
is **no `forbids` key** — widening is logged, not blocked.

For the full request/response schema and grant lifecycle, see
`spec/discovery-protocol.md`.

## Standard roles

- `sem.yaml` — orchestrator, widest default, dispatches subagents
- `architect.yaml` — ADR and invariant steward, tier-2 focused
- `backend-dev.yaml` — leaf backend implementer, TDD-enforced
- `frontend-dev.yaml` — leaf frontend implementer
- `code-reviewer.yaml` — read-only cross-context reviewer
