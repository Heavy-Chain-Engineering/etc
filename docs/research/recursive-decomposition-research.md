# Recursive Decomposition (C4) — Research Report

**Date:** 2026-03-03
**Feature:** #10 (P1 — Recursive Decomposition)
**Status:** Research complete, ready for implementation planning
**Input files examined:**
- `platform/src/etc_platform/graph_engine.py`
- `platform/tests/test_graph_engine.py`
- `platform/src/etc_platform/orchestrator.py`
- `platform/src/etc_platform/topology.py`
- `platform/src/etc_platform/run_engine.py`
- `platform/src/etc_platform/events.py`
- `platform/sql/001_initial_schema.sql`
- `platform/tests/test_schema.py`
- `docs/vision/v2-orchestration-platform-prd.md` (sections C4, 6.2, 5)
- `platform/docs/vision/v2.1-roadmap.md` (Wave 2)
- `platform/HOW-IT-WORKS.md`

---

## 1. Current State Gap Analysis

### What `graph_engine.py` Already Supports

The graph engine has the structural primitives for recursion but none of the behavioral machinery:

**Structural support (present):**
- `add_node()` (line 49) accepts `parent_node_id: UUID | None` and `depth: int` — the columns exist and can be written.
- The `execution_nodes` table (schema line 94-112) has `parent_node_id UUID REFERENCES execution_nodes ON DELETE CASCADE` with an index (`idx_execution_nodes_parent`, line 116).
- Three node types are supported: `leaf`, `composite`, `reduce` (schema line 98 CHECK constraint).
- `test_schema.py` (line 185-204) proves that composite nodes with children can be inserted and queried via `parent_node_id`.
- `test_graph_engine.py` (line 74-81) proves `add_node` can create composite nodes.

**Behavioral gaps (missing):**

1. **`get_ready_nodes()` (line 98-142) ignores `parent_node_id` entirely.** The query selects all nodes in a graph where status is `ready` or where all dependencies are completed. It does not filter by parent, does not skip composite nodes (which should never be directly deployed), and does not restrict readiness to nodes whose parent composite is itself in the right state.

2. **`start_graph()` (line 205-224) promotes ALL no-dependency nodes to `ready`.** This includes composite nodes, which should not be "ready" in the deployable sense. It also means that deeply nested leaf nodes with no explicit dependencies would get promoted immediately, even if their parent composite hasn't been activated yet.

3. **`check_graph_complete()` (line 175-202) counts ALL nodes in the graph.** It does `COUNT(*) FROM execution_nodes WHERE graph_id = %s`. With recursion, this flat count is wrong — a composite node's completion should depend on its children, not be counted as an independent unit alongside them.

4. **`build_fanout_graph()` (line 249-298) is hardcoded for single-layer fan-out.** It creates leaf nodes at depth 0 and an optional reduce node at depth 1. No recursion, no composite nodes, no nesting.

5. **No composite lifecycle management.** There is no function to:
   - Activate a composite node (make its children eligible for scheduling)
   - Complete a composite node when all its children complete
   - Propagate failure from a child to its parent composite
   - Get the children of a composite node

6. **No status rollup.** Nothing watches for "all children of composite X completed" to then mark X as completed.

7. **`topology.py` `generate_graph()` (line 162-255) generates flat layer structures.** It creates leaf nodes per layer with inter-layer dependencies, but never creates composite nodes or uses `parent_node_id`. The topology plan model (`LayerSpec`, `TopologyPlan`) has no concept of nesting.

### Where Single-Layer Assumptions Are Baked In

| Location | Assumption | Impact |
|----------|-----------|--------|
| `graph_engine.py:get_ready_nodes()` L115-141 | Queries all nodes in graph by `graph_id` only | Composite nodes would appear as "ready" and get deployed |
| `graph_engine.py:start_graph()` L212-224 | Promotes all zero-dep nodes regardless of type | Nested leaf nodes become ready before their parent is activated |
| `graph_engine.py:check_graph_complete()` L180-202 | Flat count of all nodes | Composite + children double-counted; graph won't complete correctly |
| `topology.py:generate_graph()` L201-254 | Layers are flat; nodes are always `leaf` type | Cannot produce nested graphs |
| `topology.py:TopologyPlan` L43-48 | `layers: list[LayerSpec]` — flat list | No recursive nesting in the plan model |
| `run_engine.py:deploy_ready_nodes()` L139-190 | Deploys any node with status `ready` | Would try to deploy composite nodes (which have no agent_type) |
| `orchestrator.py:load_scoped_state()` L174-184 | Queries `en.status = 'ready'` across all graphs | Would surface composite nodes as deployable |
| `orchestrator.py:_build_user_prompt()` L618-622 | Lists ready nodes for SEM without type filtering | SEM would see composite nodes as actionable |

### Does `parent_node_id` Work End-to-End?

**No.** It can be written (INSERT) and queried (SELECT WHERE parent_node_id = X), but:
- Scheduling does not use it
- Completion does not roll up through it
- No code reads it after insertion
- The only test (`test_schema.py:185-204`) validates the FK constraint, not any behavioral logic

---

## 2. Scheduling Algorithm

### Node Readiness With Nested Graphs

The current readiness rule is:
> A node is READY when its status is `pending` AND all its dependencies (via `execution_node_dependencies`) are `completed`.

For recursion, the rule needs two additions:

**Rule 1: Parent activation gate.** A node is only eligible for scheduling if its parent composite node is in `running` status (or if it has no parent, i.e., it's a root-level node). This prevents deeply nested nodes from activating before their parent subtree is reached.

**Rule 2: Composite nodes are never directly deployed.** When a composite node becomes "ready" (all its dependencies satisfied), the engine should automatically transition it to `running` and make its children eligible. The SEM does not deploy an agent to a composite node — it is a structural container.

**Proposed readiness query:**
```sql
SELECT n.*
FROM execution_nodes n
WHERE n.graph_id = $1
  AND n.node_type != 'composite'          -- Never schedule composite nodes for deployment
  AND (
      n.status = 'ready'
      OR (
          n.status = 'pending'
          AND NOT EXISTS (
              SELECT 1
              FROM execution_node_dependencies d
              JOIN execution_nodes dep ON dep.id = d.depends_on_node_id
              WHERE d.node_id = n.id
                AND dep.status != 'completed'
          )
          AND (
              -- Either has explicit dependencies (existing logic)
              EXISTS (
                  SELECT 1
                  FROM execution_node_dependencies d
                  WHERE d.node_id = n.id
              )
              -- Or has no dependencies but is a root node (no parent) that was marked ready by start_graph
              -- This case is handled by the n.status = 'ready' branch above
          )
      )
  )
  AND (
      -- Parent gate: either no parent (root-level) or parent is running
      n.parent_node_id IS NULL
      OR EXISTS (
          SELECT 1
          FROM execution_nodes parent
          WHERE parent.id = n.parent_node_id
            AND parent.status = 'running'
      )
  )
ORDER BY n.depth, n.name
```

### Composite Node Completion: Auto-Complete vs. Reduce Step

**Two distinct patterns:**

1. **Composite with reduce child:** The composite contains N leaf children + 1 reduce child. The reduce child has dependencies on all leaf siblings. When the reduce child completes, the composite auto-completes. The reduce node IS the synthesis step.

2. **Composite without reduce child:** The composite contains N leaf children only (pure fan-out). When all leaf children complete, the composite auto-completes. No synthesis needed at this level.

**The auto-completion rule:** A composite node completes when ALL of its direct children (nodes where `parent_node_id = composite.id`) have status `completed`. This should be checked after every child completion, similar to how `check_graph_complete()` works at the graph level.

**New function needed:** `check_composite_complete(conn, composite_node_id) -> bool`
```python
def check_composite_complete(conn, node_id):
    row = conn.execute("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status = 'completed') AS done
        FROM execution_nodes
        WHERE parent_node_id = %s
    """, (node_id,)).fetchone()
    if row["total"] > 0 and row["done"] == row["total"]:
        mark_node_completed(conn, node_id)
        return True
    return False
```

### Cross-Branch Dependencies at Different Depths

This is the hardest scheduling problem. The PRD example:
```
Level 2: CX Engine design depends on Level 1 CX outputs AND Level 1 domain outputs
```

Here, a Level 2 node inside one composite branch depends on Level 1 nodes inside a DIFFERENT composite branch. This is a cross-branch, cross-depth dependency.

**The existing `execution_node_dependencies` table handles this perfectly.** Dependencies are between arbitrary node IDs — there is no constraint requiring them to be siblings or within the same parent. A Level 2 node can depend on any other node in the graph.

**The scheduling query already handles this** (the dependency check joins against `execution_nodes` by ID, not by parent). The only addition needed is the parent activation gate (Rule 1 above).

**Subtle issue:** If a Level 2 node depends on a Level 1 node in a different branch, the Level 2 node's parent composite must be running before the Level 2 node can activate. But the parent composite might not be running yet (it might be waiting for its own dependencies). The dependency resolution needs to work in two stages:

1. The cross-branch dependency resolves (the Level 1 node completes)
2. The parent composite activates (its own dependencies, if any, complete)
3. BOTH conditions must be true for the Level 2 node to be ready

The proposed query above handles this because it checks BOTH the dependency condition AND the parent activation gate with AND logic.

### Can Scheduling Be a Single SQL Query?

**Yes, for the common case.** The proposed query above is a single non-recursive SQL query. It does not need recursive CTEs because:

- The parent gate only checks ONE level up (direct parent). A node's grandparent being active is implied by its parent being active (because the parent wouldn't have been activated if ITS parent wasn't active — the chain is enforced mechanically).
- Dependencies are direct node-to-node relationships — no transitive closure needed.

**Recursive CTEs would only be needed for:**
- Reporting/visualization (show the full tree structure)
- Bulk status queries ("what percentage of this subtree is complete?")
- These are read-only operations and can be added as separate utility queries.

---

## 3. Status Rollup

### When All Children Complete

When all direct children of a composite node reach `completed` status, the composite node should be automatically marked `completed`. This triggers a cascade:

1. Child leaf/reduce node completes
2. Engine checks: are all siblings (same `parent_node_id`) completed?
3. If yes: mark parent composite as `completed`
4. This may satisfy dependencies of other nodes elsewhere in the graph
5. Repeat: check if the composite's parent (if any) is now complete
6. At the root level: check if the graph is complete

**This is a bottom-up cascade, not a recursive query.** Each completion event triggers at most one check per ancestor level. In practice, the cascade is bounded by tree depth (rarely more than 3-4 levels).

**Implementation approach — extend `mark_node_completed()`:**
```python
def mark_node_completed(conn, node_id, output_path=None):
    # 1. Mark the node itself
    conn.execute("UPDATE ... SET status = 'completed' ...")

    # 2. Check parent composite
    node = get_node(conn, node_id)
    if node["parent_node_id"] is not None:
        _check_and_complete_ancestors(conn, node["parent_node_id"])

def _check_and_complete_ancestors(conn, composite_id):
    """Walk up the tree, completing ancestors whose children are all done."""
    current = composite_id
    while current is not None:
        row = conn.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'completed') AS done
            FROM execution_nodes WHERE parent_node_id = %s
        """, (current,)).fetchone()

        if row["total"] > 0 and row["done"] == row["total"]:
            conn.execute("UPDATE execution_nodes SET status = 'completed', completed_at = now() WHERE id = %s", (current,))
            parent = conn.execute("SELECT parent_node_id FROM execution_nodes WHERE id = %s", (current,)).fetchone()
            current = parent["parent_node_id"] if parent else None
        else:
            break  # Not all children done, stop cascading
```

### Child Failure Propagation

**Recommended policy (configurable per composite):**

- **Default: Fail-fast.** If any child fails AND has exhausted retries, the composite is marked `failed`. This propagates upward — a failed composite fails its parent.
- **Alternative: Partial completion.** The composite waits. Other children continue. The composite is marked `partially_failed` (new status) only when all non-failed children complete. The SEM decides what to do.

**For MVP: fail-fast is simpler and correct.** The SEM can always retry a failed composite, which re-runs only the failed subtree.

**Status propagation:**
- Child fails -> check composite: if child exhausted retries, mark composite `failed`
- Composite fails -> check its parent (same logic, recursive)
- Composite fails -> any nodes that depend on it stay `pending` (blocked)

**New status value consideration:** The current CHECK constraint allows `pending|ready|running|completed|failed|retrying`. This is sufficient for MVP. `partially_failed` can be added later if needed.

### Retry Semantics for Nested Nodes

Three levels of retry granularity:

1. **Retry the leaf.** The existing retry mechanism (`retry.py`) works: re-run the agent on the same leaf node with violation context. `retry_count` is already tracked per node.

2. **Retry the composite (subtree retry).** Reset all children of the composite to `pending`, reset the composite to `running`. This replays the entire subtree. Use case: when the subtree's approach was fundamentally wrong, not just one agent's output.

3. **Retry from a specific node.** Reset the target node and all downstream dependents to `pending`. This is a selective replay.

**For MVP: support levels 1 and 2.** Level 1 already works. Level 2 needs a new function:

```python
def reset_subtree(conn, composite_node_id):
    """Reset a composite and all its descendants to pending."""
    conn.execute("""
        WITH RECURSIVE descendants AS (
            SELECT id FROM execution_nodes WHERE parent_node_id = %s
            UNION ALL
            SELECT n.id FROM execution_nodes n
            JOIN descendants d ON n.parent_node_id = d.id
        )
        UPDATE execution_nodes SET status = 'pending', started_at = NULL, completed_at = NULL
        WHERE id IN (SELECT id FROM descendants) OR id = %s
    """, (composite_node_id, composite_node_id))
```

This IS a case where a recursive CTE is needed (and appropriate — it's a write operation on a known subtree).

---

## 4. Topology Generation

### How `topology.py` Currently Generates Graphs

**Stage 1 — Assessment (`assess_topology()`, line 56-133):**
- Loads project info + source materials from Postgres
- Sends material inventory to an LLM with `_ASSESSMENT_PROMPT`
- Gets back a `TopologyPlan` with `layers: list[LayerSpec]`, `reduce_strategy`, `estimated_agents`
- Each `LayerSpec` has `name`, `dimension`, `nodes: list[NodeSpec]`
- This is a FLAT structure: layers are sequential, no nesting

**Stage 2 — Graph generation (`generate_graph()`, line 162-255):**
- Creates one `execution_graph`
- Iterates layers sequentially; for each layer, creates leaf nodes
- Wires inter-layer dependencies: each node in layer N depends on ALL nodes in layer N-1 (line 218-219)
- Adds reduce node(s) after the last layer based on `reduce_strategy`
- Calls `start_graph()` to promote zero-dep nodes

**The model is flat.** `TopologyPlan.layers` is `list[LayerSpec]`, where each layer is a parallel group. There is no way to represent "this node contains sub-nodes" or "this layer has a nested sub-graph."

### How It Should Generate Recursive/Nested Graphs

**New plan model:**

```python
class NodePlan(BaseModel):
    """A node in the topology plan. Can be leaf or composite."""
    name: str
    agent_type: str | None = None  # None for composite
    assignment: dict[str, Any] = {}
    children: list["NodePlan"] = []  # Non-empty = composite
    reduce: "NodePlan | None" = None  # Optional reduce step for this subtree
    depends_on: list[str] = []  # Names of other nodes this depends on (cross-branch)

class TopologyPlan(BaseModel):
    """Complete topology plan — a tree of NodePlans."""
    root_nodes: list[NodePlan]  # Top-level nodes (may be leaf or composite)
    estimated_agents: int = 0
    reasoning: str = ""
```

**Graph generation from tree plan:**

```python
def generate_recursive_graph(conn, project_id, phase_id, plan):
    graph_id = GraphEngine.create_graph(conn, project_id, phase_id, ...)

    # Track name -> node_id for dependency wiring
    name_to_id: dict[str, UUID] = {}

    def create_subtree(node_plan, parent_id=None, depth=0):
        if node_plan.children:
            # Composite node
            composite_id = GraphEngine.add_node(
                conn, graph_id, node_plan.name, "composite",
                parent_node_id=parent_id, depth=depth
            )
            name_to_id[node_plan.name] = composite_id

            child_ids = []
            for child in node_plan.children:
                child_id = create_subtree(child, parent_id=composite_id, depth=depth+1)
                child_ids.append(child_id)

            if node_plan.reduce:
                reduce_id = GraphEngine.add_node(
                    conn, graph_id, node_plan.reduce.name, "reduce",
                    agent_type=node_plan.reduce.agent_type,
                    assignment=node_plan.reduce.assignment,
                    parent_node_id=composite_id, depth=depth+1
                )
                for cid in child_ids:
                    GraphEngine.add_dependency(conn, reduce_id, cid)
                name_to_id[node_plan.reduce.name] = reduce_id

            return composite_id
        else:
            # Leaf node
            leaf_id = GraphEngine.add_node(
                conn, graph_id, node_plan.name, "leaf",
                agent_type=node_plan.agent_type,
                assignment=node_plan.assignment,
                parent_node_id=parent_id, depth=depth
            )
            name_to_id[node_plan.name] = leaf_id
            return leaf_id

    for root_node in plan.root_nodes:
        create_subtree(root_node)

    # Wire cross-branch dependencies
    for node_plan in _flatten_plan(plan):
        if node_plan.depends_on:
            node_id = name_to_id[node_plan.name]
            for dep_name in node_plan.depends_on:
                dep_id = name_to_id[dep_name]
                GraphEngine.add_dependency(conn, node_id, dep_id)

    GraphEngine.start_graph(conn, graph_id)
    return graph_id
```

### Eager vs. Lazy Decomposition

**Eager (plan the whole tree upfront):**
- LLM designs the full tree before any agent runs
- Human can review and approve the complete topology
- Dependencies are known upfront — scheduling is simple
- Risk: the LLM might misestimate scope at deeper levels

**Lazy (decompose at runtime when a node is "too big"):**
- Start with a shallow plan
- When a composite node activates, the SEM assesses whether its scope fits one agent
- If not, the SEM decomposes further — adding child nodes to the composite
- More accurate because decomposition uses outputs from completed nodes
- Risk: harder to estimate total cost/time; human can't see the full plan upfront

**Recommendation: Eager with runtime refinement.**

For MVP, the topology builder generates the full tree eagerly. The SEM presents it for human approval. This gives visibility and predictability.

For v2.1, add a `DECOMPOSE_FURTHER` SEM decision type. When the SEM encounters a composite node whose scope turned out to be larger than expected (based on actual agent outputs), it can add more children. This is lazy refinement on top of an eager base.

**Why this order:**
1. Eager is simpler to implement (one topology call, one graph build)
2. Eager enables human approval of the full plan
3. Lazy refinement can be layered on later without changing the core scheduling algorithm (just add nodes to an existing composite)
4. Adding nodes to a running graph requires careful handling of `start_graph()` semantics (which currently only runs once), but is tractable

---

## 5. SEM Integration

### New Decision Types Needed

| Decision Type | When | Effect |
|--------------|------|--------|
| `DECOMPOSE_FURTHER` (P1+) | SEM assesses a composite node's scope as too large at runtime | Calls topology builder scoped to the composite, adds child nodes |
| `ACTIVATE_COMPOSITE` | A composite node's dependencies are all satisfied | Transitions composite to `running`, making children eligible |

**However, `ACTIVATE_COMPOSITE` should arguably NOT be a SEM decision.** It is a mechanical action — when a composite's dependencies are met, its children should become eligible automatically. This keeps the SEM focused on judgment calls (deploy which agent? decompose further? retry?) and away from mechanical scheduling.

**Recommended approach:**
- **Mechanical (no SEM involved):** Composite activation and completion rollup happen in the graph engine automatically, triggered after every node status change.
- **SEM decision (new):** `DECOMPOSE_FURTHER` — only needed if we implement lazy decomposition (not MVP).

**For MVP, zero new SEM decision types are needed.** The graph engine handles composite lifecycle mechanically. The existing `DEPLOY_AGENT` works for leaf nodes. The existing `DESIGN_TOPOLOGY` works for initial topology generation.

### How the SEM Knows When to Decompose vs. Deploy

Currently, the SEM sees ready nodes in `load_scoped_state()` (orchestrator.py line 174-184) and decides `DEPLOY_AGENT`. With recursion:

1. The SEM should never see composite nodes as "ready" — the scheduling query filters them out
2. The SEM sees leaf and reduce nodes that are ready — same as today
3. For lazy decomposition (future): the SEM would see a special event indicating a composite node activated but has no children, and would decide `DECOMPOSE_FURTHER`

**For MVP: no changes to `load_scoped_state()` needed** beyond ensuring composite nodes don't appear in the ready nodes query. The existing filtering in the scheduling query handles this.

### Event Changes

**No new event types needed for MVP.** The existing events suffice:

- `AGENT_COMPLETED` — a leaf/reduce node's agent finished (existing)
- `NODE_READY` — a node's dependencies are satisfied (existing)
- `AGENT_STARTED` — SEM deployed an agent to a leaf node (existing)

**The composite lifecycle is internal to the graph engine** and does not need events. The SEM only cares about deployable nodes (leaf/reduce), not structural nodes (composite).

**For lazy decomposition (future):** Add `COMPOSITE_ACTIVATED` event type so the SEM can decide whether to decompose further.

---

## 6. Schema Changes

### Current Schema Assessment

The current schema (`001_initial_schema.sql`) **already supports full recursion**:

- `execution_nodes.parent_node_id UUID REFERENCES execution_nodes ON DELETE CASCADE` (line 97) — self-referential FK, supports arbitrary depth
- `execution_nodes.depth INTEGER NOT NULL DEFAULT 0` (line 109) — tracks depth in tree
- `execution_nodes.node_type CHECK (node_type IN ('leaf', 'composite', 'reduce'))` (line 98) — composite type exists
- `execution_node_dependencies` (line 118-122) — dependencies between arbitrary nodes, no parent constraint
- `idx_execution_nodes_parent` index exists (line 116) — supports child lookups

**No schema changes are needed for MVP recursive decomposition.**

### Missing Indexes for Recursive Queries

The existing indexes are sufficient for the proposed scheduling query:

- `idx_execution_nodes_graph` (line 114): `(graph_id)` — used in the main WHERE clause
- `idx_execution_nodes_status` (line 115): `(graph_id, status)` — used for status filtering
- `idx_execution_nodes_parent` (line 116): `(parent_node_id)` — used for parent gate and child lookups

**One index could help performance for status rollup:**

```sql
-- Composite covering index for child completion checks
CREATE INDEX idx_execution_nodes_parent_status
ON execution_nodes (parent_node_id, status)
WHERE parent_node_id IS NOT NULL;
```

This partial index would speed up the `check_composite_complete()` query, which filters on `parent_node_id = X` and aggregates on `status`. Not critical for MVP (tree depths are small), but good to add proactively.

### `reduce_inputs` Column

The `reduce_inputs JSONB` column (schema line 102) exists but is never used in `graph_engine.py`. Its intended purpose (from the PRD) was to store references to which nodes' outputs feed into a reduce node. However, this information is already captured in `execution_node_dependencies` — a reduce node's dependencies ARE its inputs.

**Recommendation:** Leave `reduce_inputs` in the schema but continue not using it. Dependencies are the canonical source of input relationships. If we later need reduce-specific metadata (e.g., "merge strategy"), `reduce_inputs` can serve that purpose.

---

## 7. Risk Assessment

### Blast Radius

**Core files that need changes:**

| File | Change Type | Risk |
|------|------------|------|
| `graph_engine.py` | Modify `get_ready_nodes()`, `start_graph()`, `check_graph_complete()`, `mark_node_completed()`. Add `activate_composite()`, `check_composite_complete()`, `_check_and_complete_ancestors()`, `reset_subtree()`. | **HIGH** — this is the scheduling core. All downstream consumers depend on it. |
| `topology.py` | New plan model (`NodePlan`), new `generate_recursive_graph()`. Keep existing `generate_graph()` for backward compat. | **MEDIUM** — additive change, existing function preserved. |
| `run_engine.py` | Modify `deploy_ready_nodes()` to skip composite nodes (or rely on updated `get_ready_nodes()`). Modify `check_graph_completions()` to trigger composite rollup. | **MEDIUM** — mechanical changes. |
| `orchestrator.py` | Modify `load_scoped_state()` to filter composite nodes from ready list. No new decision types for MVP. | **LOW** — small filtering change. |

**Files that should NOT change for MVP:**
- `events.py` — no new event types
- `sql/001_initial_schema.sql` — schema already supports recursion
- `phases.py` — no phase changes
- `agent_runtime.py` — agents don't know about tree structure
- `guardrails.py` — guardrails run per agent output, tree-agnostic

### Existing Tests That Might Break

| Test File | Test(s) at Risk | Why |
|-----------|----------------|-----|
| `test_graph_engine.py:TestGetReadyNodes` | `test_no_deps_node_is_ready_after_start` | If `start_graph()` changes to only promote root-level nodes, this test's assumptions about composite nodes might shift — but since these tests use leaf nodes, they should still pass |
| `test_graph_engine.py:TestGraphCompletion` | `test_graph_complete_all_done` | If `check_graph_complete()` changes to only count root-level nodes, this flat-graph test needs to still work |
| `test_graph_engine.py:TestBuildFanoutGraph` | All 5 tests | `build_fanout_graph()` should be preserved as-is (it's a convenience for flat graphs). Tests should not break. |
| `test_graph_engine.py:TestStartGraph` | `test_start_marks_no_dep_nodes_ready` | Need to ensure start_graph still promotes root-level leaf nodes with no deps |

**Key constraint: all existing tests must continue to pass.** The flat fan-out case is a special case of the recursive case (depth=0, no composite nodes, no parent_node_id). The refactored scheduling logic must handle this degenerate case identically to the current behavior.

### Minimal Change Set for Basic 2-Level Recursion

**Phase 1 — Graph engine recursion (smallest viable change):**

1. **Modify `get_ready_nodes()`** — Add `n.node_type != 'composite'` filter and parent activation gate. (~10 lines changed in the query)

2. **Add `activate_composite()`** — When a composite node's dependencies are met, set it to `running`. (~15 lines)

3. **Add `check_composite_complete()`** — When a child completes, check if parent composite should complete. (~20 lines)

4. **Modify `mark_node_completed()`** — After marking a node complete, call `_check_and_complete_ancestors()` for parent rollup. (~10 lines added)

5. **Modify `start_graph()`** — When promoting zero-dep nodes, treat zero-dep composites differently: set them to `running` (not `ready`), and promote their zero-dep leaf children to `ready`. (~15 lines changed)

6. **Modify `check_graph_complete()`** — Only count root-level nodes (WHERE parent_node_id IS NULL) OR keep current flat count but ensure composite nodes auto-complete when children do (so the flat count still works). The latter is simpler and backward-compatible. (~0 lines changed if composite auto-completion is reliable)

**Phase 2 — Topology builder recursion:**

7. **Add `NodePlan` model** to topology.py. (~20 lines)

8. **Add `generate_recursive_graph()`** function. (~60 lines)

9. **Modify `_ASSESSMENT_PROMPT`** to instruct the LLM to produce nested plans. (~20 lines of prompt)

**Phase 3 — Integration:**

10. **Modify `run_engine.py`** — Add composite activation + rollup calls in the run cycle. (~20 lines)

11. **Add tests** for 2-level recursion, cross-branch dependencies, composite completion, failure propagation. (~150 lines of tests)

**Total estimated change: ~340 lines of code + tests.** No schema migration. No new dependencies. No new event types.

---

## Summary of Recommendations

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Decomposition strategy | Eager (full tree upfront) for MVP | Simpler, human can review, no runtime graph mutation needed |
| Composite activation | Mechanical (graph engine), not SEM decision | Pure scheduling logic, no judgment required |
| Composite completion | Auto-complete when all children done, with ancestor cascade | Bottom-up rollup is natural and bounded by tree depth |
| Failure propagation | Fail-fast for MVP | Simpler; SEM can retry subtree if needed |
| Scheduling query | Single SQL query with parent gate | No recursive CTE needed for scheduling; only for subtree reset |
| Schema changes | None for MVP; optional `parent_status` partial index | Current schema already supports full recursion |
| New SEM decisions | None for MVP | Composite lifecycle is mechanical, not strategic |
| New events | None for MVP | Composite lifecycle is internal to graph engine |
| Backward compatibility | All existing flat-graph tests must pass unchanged | Flat fan-out is a degenerate case of recursion |
| `build_fanout_graph()` | Keep as-is | Convenience function for simple cases; not worth breaking |
| Retry granularity | Leaf retry (existing) + subtree retry (new) | Two levels cover practical use cases |
