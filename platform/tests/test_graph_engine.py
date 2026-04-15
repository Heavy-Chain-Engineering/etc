"""Tests for GraphEngine — execution graph scheduling with fan-out/reduce."""

from __future__ import annotations

from uuid import UUID

import psycopg

from etc_platform.graph_engine import GraphEngine, build_fanout_graph


def _create_project_and_phase(db: psycopg.Connection) -> tuple[UUID, UUID]:
    """Helper: insert a project + phase and return (project_id, phase_id)."""
    project = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('p', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert project is not None
    pid = project["id"]

    phase = db.execute(
        "INSERT INTO phases (project_id, name) VALUES (%s, 'Build') RETURNING id",
        (pid,),
    ).fetchone()
    assert phase is not None
    return pid, phase["id"]


class TestCreateGraph:
    def test_creates_graph(self, db: psycopg.Connection) -> None:
        """create_graph inserts a row into execution_graphs."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "test-graph")
        row = db.execute(
            "SELECT * FROM execution_graphs WHERE id = %s", (graph_id,)
        ).fetchone()
        assert row is not None
        assert row["name"] == "test-graph"
        assert row["project_id"] == pid
        assert row["phase_id"] == phase_id

    def test_returns_uuid(self, db: psycopg.Connection) -> None:
        """create_graph returns a UUID."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "test-graph")
        assert isinstance(graph_id, UUID)

    def test_default_status_pending(self, db: psycopg.Connection) -> None:
        """New graphs default to 'pending' status."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "test-graph")
        graph = GraphEngine.get_graph(db, graph_id)
        assert graph is not None
        assert graph["status"] == "pending"


class TestAddNode:
    def test_add_leaf_node(self, db: psycopg.Connection) -> None:
        """add_node creates a leaf node in the graph."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        node_id = GraphEngine.add_node(
            db, graph_id, "research-domain", "leaf", agent_type="researcher"
        )
        node = GraphEngine.get_node(db, node_id)
        assert node is not None
        assert node["name"] == "research-domain"
        assert node["node_type"] == "leaf"
        assert node["agent_type"] == "researcher"
        assert node["status"] == "pending"

    def test_add_composite_node(self, db: psycopg.Connection) -> None:
        """add_node creates a composite node."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        node_id = GraphEngine.add_node(db, graph_id, "parent", "composite")
        node = GraphEngine.get_node(db, node_id)
        assert node is not None
        assert node["node_type"] == "composite"

    def test_add_reduce_node(self, db: psycopg.Connection) -> None:
        """add_node creates a reduce node at depth 1."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        node_id = GraphEngine.add_node(
            db, graph_id, "synthesis", "reduce", agent_type="researcher", depth=1
        )
        node = GraphEngine.get_node(db, node_id)
        assert node is not None
        assert node["node_type"] == "reduce"
        assert node["depth"] == 1

    def test_node_with_assignment(self, db: psycopg.Connection) -> None:
        """add_node stores a JSONB assignment payload."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        assignment = {"prompt": "Analyze domain model", "sources": ["spec.md"]}
        node_id = GraphEngine.add_node(
            db, graph_id, "task-1", "leaf",
            agent_type="researcher", assignment=assignment,
        )
        node = GraphEngine.get_node(db, node_id)
        assert node is not None
        assert node["assignment"] == assignment


class TestAddDependency:
    def test_add_dependency(self, db: psycopg.Connection) -> None:
        """add_dependency creates a row in execution_node_dependencies."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        n2 = GraphEngine.add_node(db, graph_id, "reduce", "reduce", depth=1)
        GraphEngine.add_dependency(db, n2, n1)

        row = db.execute(
            "SELECT * FROM execution_node_dependencies "
            "WHERE node_id = %s AND depends_on_node_id = %s",
            (n2, n1),
        ).fetchone()
        assert row is not None


class TestGetReadyNodes:
    def test_no_deps_node_is_ready_after_start(self, db: psycopg.Connection) -> None:
        """A node with no dependencies becomes ready when the graph is started."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        GraphEngine.start_graph(db, graph_id)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        assert len(ready) == 1
        assert ready[0]["name"] == "leaf-1"

    def test_node_with_incomplete_dep_not_ready(self, db: psycopg.Connection) -> None:
        """A node whose dependency is still pending is NOT ready."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        n2 = GraphEngine.add_node(db, graph_id, "reduce", "reduce", depth=1)
        GraphEngine.add_dependency(db, n2, n1)
        GraphEngine.start_graph(db, graph_id)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        names = [r["name"] for r in ready]
        assert "reduce" not in names

    def test_node_with_completed_dep_is_ready(self, db: psycopg.Connection) -> None:
        """A node becomes ready once all its dependencies are completed."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        n2 = GraphEngine.add_node(db, graph_id, "reduce", "reduce", depth=1)
        GraphEngine.add_dependency(db, n2, n1)
        GraphEngine.start_graph(db, graph_id)

        # Complete the leaf
        GraphEngine.mark_node_running(db, n1)
        GraphEngine.mark_node_completed(db, n1)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        names = [r["name"] for r in ready]
        assert "reduce" in names

    def test_multiple_deps_all_must_complete(self, db: psycopg.Connection) -> None:
        """A node with multiple deps is NOT ready until ALL deps are completed."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        n2 = GraphEngine.add_node(db, graph_id, "leaf-2", "leaf")
        n3 = GraphEngine.add_node(db, graph_id, "reduce", "reduce", depth=1)
        GraphEngine.add_dependency(db, n3, n1)
        GraphEngine.add_dependency(db, n3, n2)
        GraphEngine.start_graph(db, graph_id)

        # Complete only one leaf
        GraphEngine.mark_node_running(db, n1)
        GraphEngine.mark_node_completed(db, n1)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        names = [r["name"] for r in ready]
        assert "reduce" not in names

        # Complete the second leaf
        GraphEngine.mark_node_running(db, n2)
        GraphEngine.mark_node_completed(db, n2)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        names = [r["name"] for r in ready]
        assert "reduce" in names

    def test_already_running_node_not_ready(self, db: psycopg.Connection) -> None:
        """A node that is already 'running' should NOT appear in ready nodes."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        GraphEngine.start_graph(db, graph_id)

        # Mark it running
        GraphEngine.mark_node_running(db, n1)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        assert len(ready) == 0


class TestNodeLifecycle:
    def test_mark_running(self, db: psycopg.Connection) -> None:
        """mark_node_running sets status to 'running' and records started_at."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        GraphEngine.mark_node_running(db, n1)

        node = GraphEngine.get_node(db, n1)
        assert node is not None
        assert node["status"] == "running"
        assert node["started_at"] is not None

    def test_mark_completed(self, db: psycopg.Connection) -> None:
        """mark_node_completed sets status to 'completed' with output_path and completed_at."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        GraphEngine.mark_node_running(db, n1)
        GraphEngine.mark_node_completed(db, n1, output_path="/out/result.md")

        node = GraphEngine.get_node(db, n1)
        assert node is not None
        assert node["status"] == "completed"
        assert node["output_path"] == "/out/result.md"
        assert node["completed_at"] is not None

    def test_mark_failed(self, db: psycopg.Connection) -> None:
        """mark_node_failed sets status to 'failed'."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        GraphEngine.mark_node_running(db, n1)
        GraphEngine.mark_node_failed(db, n1)

        node = GraphEngine.get_node(db, n1)
        assert node is not None
        assert node["status"] == "failed"


class TestGraphCompletion:
    def test_graph_not_complete_with_pending(self, db: psycopg.Connection) -> None:
        """check_graph_complete returns False when any node is not completed."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        n2 = GraphEngine.add_node(db, graph_id, "leaf-2", "leaf")
        GraphEngine.start_graph(db, graph_id)

        GraphEngine.mark_node_running(db, n1)
        GraphEngine.mark_node_completed(db, n1)

        assert GraphEngine.check_graph_complete(db, graph_id) is False

    def test_graph_complete_all_done(self, db: psycopg.Connection) -> None:
        """check_graph_complete returns True when all nodes are completed."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        n2 = GraphEngine.add_node(db, graph_id, "leaf-2", "leaf")
        GraphEngine.start_graph(db, graph_id)

        for nid in (n1, n2):
            GraphEngine.mark_node_running(db, nid)
            GraphEngine.mark_node_completed(db, nid)

        assert GraphEngine.check_graph_complete(db, graph_id) is True

    def test_graph_marked_completed(self, db: psycopg.Connection) -> None:
        """check_graph_complete marks the graph status as 'completed' when all done."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        GraphEngine.start_graph(db, graph_id)

        GraphEngine.mark_node_running(db, n1)
        GraphEngine.mark_node_completed(db, n1)
        GraphEngine.check_graph_complete(db, graph_id)

        graph = GraphEngine.get_graph(db, graph_id)
        assert graph is not None
        assert graph["status"] == "completed"
        assert graph["completed_at"] is not None


class TestStartGraph:
    def test_start_sets_running(self, db: psycopg.Connection) -> None:
        """start_graph sets the graph status to 'running'."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        GraphEngine.start_graph(db, graph_id)

        graph = GraphEngine.get_graph(db, graph_id)
        assert graph is not None
        assert graph["status"] == "running"

    def test_start_marks_no_dep_nodes_ready(self, db: psycopg.Connection) -> None:
        """start_graph marks nodes with zero dependencies as 'ready'."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        n2 = GraphEngine.add_node(db, graph_id, "leaf-2", "leaf")
        GraphEngine.start_graph(db, graph_id)

        for nid in (n1, n2):
            node = GraphEngine.get_node(db, nid)
            assert node is not None
            assert node["status"] == "ready"

    def test_start_leaves_dep_nodes_pending(self, db: psycopg.Connection) -> None:
        """start_graph does NOT mark nodes with dependencies as 'ready'."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        n1 = GraphEngine.add_node(db, graph_id, "leaf-1", "leaf")
        n2 = GraphEngine.add_node(db, graph_id, "reduce", "reduce", depth=1)
        GraphEngine.add_dependency(db, n2, n1)
        GraphEngine.start_graph(db, graph_id)

        node = GraphEngine.get_node(db, n2)
        assert node is not None
        assert node["status"] == "pending"


class TestBuildFanoutGraph:
    def test_creates_leaf_nodes(self, db: psycopg.Connection) -> None:
        """build_fanout_graph creates N leaf nodes from the agents list."""
        pid, phase_id = _create_project_and_phase(db)
        agents = [
            {"name": "R01-domain", "agent_type": "researcher", "assignment": {"prompt": "a"}},
            {"name": "R02-tech", "agent_type": "researcher", "assignment": {"prompt": "b"}},
        ]
        graph_id = build_fanout_graph(db, pid, phase_id, "fan", agents)

        nodes = GraphEngine.list_nodes(db, graph_id)
        leaf_nodes = [n for n in nodes if n["node_type"] == "leaf"]
        assert len(leaf_nodes) == 2
        names = {n["name"] for n in leaf_nodes}
        assert names == {"R01-domain", "R02-tech"}

    def test_creates_reduce_node(self, db: psycopg.Connection) -> None:
        """build_fanout_graph creates a reduce node when reduce_agent is provided."""
        pid, phase_id = _create_project_and_phase(db)
        agents = [
            {"name": "R01", "agent_type": "researcher", "assignment": {"prompt": "a"}},
        ]
        reduce = {"name": "synthesis", "agent_type": "researcher", "assignment": {"prompt": "synth"}}
        graph_id = build_fanout_graph(db, pid, phase_id, "fan", agents, reduce_agent=reduce)

        nodes = GraphEngine.list_nodes(db, graph_id)
        reduce_nodes = [n for n in nodes if n["node_type"] == "reduce"]
        assert len(reduce_nodes) == 1
        assert reduce_nodes[0]["name"] == "synthesis"
        assert reduce_nodes[0]["depth"] == 1

    def test_reduce_depends_on_all_leaves(self, db: psycopg.Connection) -> None:
        """The reduce node depends on every leaf node."""
        pid, phase_id = _create_project_and_phase(db)
        agents = [
            {"name": "R01", "agent_type": "researcher", "assignment": {"prompt": "a"}},
            {"name": "R02", "agent_type": "researcher", "assignment": {"prompt": "b"}},
            {"name": "R03", "agent_type": "researcher", "assignment": {"prompt": "c"}},
        ]
        reduce = {"name": "synthesis", "agent_type": "researcher", "assignment": {"prompt": "synth"}}
        graph_id = build_fanout_graph(db, pid, phase_id, "fan", agents, reduce_agent=reduce)

        nodes = GraphEngine.list_nodes(db, graph_id)
        reduce_node = [n for n in nodes if n["node_type"] == "reduce"][0]

        deps = db.execute(
            "SELECT depends_on_node_id FROM execution_node_dependencies WHERE node_id = %s",
            (reduce_node["id"],),
        ).fetchall()
        dep_ids = {d["depends_on_node_id"] for d in deps}

        leaf_ids = {n["id"] for n in nodes if n["node_type"] == "leaf"}
        assert dep_ids == leaf_ids

    def test_fanout_without_reduce(self, db: psycopg.Connection) -> None:
        """build_fanout_graph works without a reduce agent (pure fan-out)."""
        pid, phase_id = _create_project_and_phase(db)
        agents = [
            {"name": "R01", "agent_type": "researcher", "assignment": {"prompt": "a"}},
            {"name": "R02", "agent_type": "researcher", "assignment": {"prompt": "b"}},
        ]
        graph_id = build_fanout_graph(db, pid, phase_id, "fan", agents)

        nodes = GraphEngine.list_nodes(db, graph_id)
        assert len(nodes) == 2
        assert all(n["node_type"] == "leaf" for n in nodes)

    def test_leaf_nodes_ready_after_build(self, db: psycopg.Connection) -> None:
        """After build_fanout_graph, all leaf nodes are 'ready'."""
        pid, phase_id = _create_project_and_phase(db)
        agents = [
            {"name": "R01", "agent_type": "researcher", "assignment": {"prompt": "a"}},
            {"name": "R02", "agent_type": "researcher", "assignment": {"prompt": "b"}},
        ]
        graph_id = build_fanout_graph(db, pid, phase_id, "fan", agents)

        nodes = GraphEngine.list_nodes(db, graph_id)
        for node in nodes:
            assert node["status"] == "ready"

    def test_graph_is_running(self, db: psycopg.Connection) -> None:
        """After build_fanout_graph, the graph status is 'running'."""
        pid, phase_id = _create_project_and_phase(db)
        agents = [
            {"name": "R01", "agent_type": "researcher", "assignment": {"prompt": "a"}},
        ]
        graph_id = build_fanout_graph(db, pid, phase_id, "fan", agents)

        graph = GraphEngine.get_graph(db, graph_id)
        assert graph is not None
        assert graph["status"] == "running"


class TestCompositeActivation:
    def test_start_graph_activates_root_composite(self, db: psycopg.Connection) -> None:
        """start_graph sets root-level composite nodes to 'running', not 'ready'."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite_id = GraphEngine.add_node(db, graph_id, "group-1", "composite")
        leaf_id = GraphEngine.add_node(
            db, graph_id, "leaf-1", "leaf",
            agent_type="researcher", parent_node_id=composite_id, depth=1,
        )
        GraphEngine.start_graph(db, graph_id)

        composite = GraphEngine.get_node(db, composite_id)
        assert composite is not None
        assert composite["status"] == "running"

        leaf = GraphEngine.get_node(db, leaf_id)
        assert leaf is not None
        assert leaf["status"] == "ready"

    def test_start_graph_nested_composite_stays_pending(self, db: psycopg.Connection) -> None:
        """start_graph does NOT activate composites that have dependencies."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        c1 = GraphEngine.add_node(db, graph_id, "group-1", "composite")
        c2 = GraphEngine.add_node(db, graph_id, "group-2", "composite")
        GraphEngine.add_dependency(db, c2, c1)
        GraphEngine.start_graph(db, graph_id)

        node = GraphEngine.get_node(db, c2)
        assert node is not None
        assert node["status"] == "pending"


class TestParentActivationGate:
    def test_composite_never_in_ready_nodes(self, db: psycopg.Connection) -> None:
        """Composite nodes never appear in get_ready_nodes results."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        GraphEngine.add_node(db, graph_id, "group-1", "composite")
        GraphEngine.start_graph(db, graph_id)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        types = [r["node_type"] for r in ready]
        assert "composite" not in types

    def test_child_not_ready_when_parent_pending(self, db: psycopg.Connection) -> None:
        """A leaf inside a pending composite is NOT ready, even with no deps."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        c1 = GraphEngine.add_node(db, graph_id, "group-1", "composite")
        c2 = GraphEngine.add_node(db, graph_id, "group-2", "composite")
        GraphEngine.add_dependency(db, c2, c1)
        leaf = GraphEngine.add_node(
            db, graph_id, "nested-leaf", "leaf",
            agent_type="researcher", parent_node_id=c2, depth=1,
        )
        GraphEngine.start_graph(db, graph_id)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        names = [r["name"] for r in ready]
        assert "nested-leaf" not in names

    def test_child_ready_when_parent_running(self, db: psycopg.Connection) -> None:
        """A leaf inside a running composite IS ready."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite = GraphEngine.add_node(db, graph_id, "group-1", "composite")
        leaf = GraphEngine.add_node(
            db, graph_id, "child-leaf", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        GraphEngine.start_graph(db, graph_id)

        ready = GraphEngine.get_ready_nodes(db, graph_id)
        names = [r["name"] for r in ready]
        assert "child-leaf" in names


class TestCompositeStatusRollup:
    def test_composite_completes_when_all_children_done(self, db: psycopg.Connection) -> None:
        """A composite auto-completes when all its children are completed."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite = GraphEngine.add_node(db, graph_id, "group", "composite")
        l1 = GraphEngine.add_node(
            db, graph_id, "leaf-1", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        l2 = GraphEngine.add_node(
            db, graph_id, "leaf-2", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        GraphEngine.start_graph(db, graph_id)

        GraphEngine.mark_node_running(db, l1)
        GraphEngine.mark_node_completed(db, l1)

        # Not complete yet — leaf-2 still pending
        c = GraphEngine.get_node(db, composite)
        assert c["status"] == "running"

        GraphEngine.mark_node_running(db, l2)
        GraphEngine.mark_node_completed(db, l2)

        # Now composite should auto-complete
        c = GraphEngine.get_node(db, composite)
        assert c["status"] == "completed"

    def test_ancestor_cascade(self, db: psycopg.Connection) -> None:
        """Completion cascades up through nested composites."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        outer = GraphEngine.add_node(db, graph_id, "outer", "composite")
        inner = GraphEngine.add_node(
            db, graph_id, "inner", "composite",
            parent_node_id=outer, depth=1,
        )
        leaf = GraphEngine.add_node(
            db, graph_id, "leaf", "leaf",
            agent_type="researcher", parent_node_id=inner, depth=2,
        )
        # Manually activate composites for this test
        GraphEngine.mark_node_running(db, outer)
        GraphEngine.mark_node_running(db, inner)
        db.execute(
            "UPDATE execution_nodes SET status = 'ready' WHERE id = %s", (leaf,)
        )

        GraphEngine.mark_node_running(db, leaf)
        GraphEngine.mark_node_completed(db, leaf)

        inner_node = GraphEngine.get_node(db, inner)
        assert inner_node["status"] == "completed"

        outer_node = GraphEngine.get_node(db, outer)
        assert outer_node["status"] == "completed"

    def test_composite_not_complete_with_pending_children(self, db: psycopg.Connection) -> None:
        """Composite stays running when some children are still pending."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite = GraphEngine.add_node(db, graph_id, "group", "composite")
        l1 = GraphEngine.add_node(
            db, graph_id, "leaf-1", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        l2 = GraphEngine.add_node(
            db, graph_id, "leaf-2", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        GraphEngine.start_graph(db, graph_id)

        GraphEngine.mark_node_running(db, l1)
        GraphEngine.mark_node_completed(db, l1)

        c = GraphEngine.get_node(db, composite)
        assert c["status"] == "running"


class TestCompositeActivationAfterDeps:
    def test_composite_activates_when_deps_complete(self, db: psycopg.Connection) -> None:
        """A composite node transitions to 'running' when its dependencies complete."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        c1 = GraphEngine.add_node(db, graph_id, "phase-1", "composite")
        l1 = GraphEngine.add_node(
            db, graph_id, "task-1", "leaf",
            agent_type="researcher", parent_node_id=c1, depth=1,
        )
        c2 = GraphEngine.add_node(db, graph_id, "phase-2", "composite")
        GraphEngine.add_dependency(db, c2, c1)
        l2 = GraphEngine.add_node(
            db, graph_id, "task-2", "leaf",
            agent_type="researcher", parent_node_id=c2, depth=1,
        )
        GraphEngine.start_graph(db, graph_id)

        # c1 is running, c2 is pending (depends on c1)
        assert GraphEngine.get_node(db, c2)["status"] == "pending"

        # Complete c1's only child -> c1 auto-completes -> c2 should activate
        GraphEngine.mark_node_running(db, l1)
        GraphEngine.mark_node_completed(db, l1)

        c2_node = GraphEngine.get_node(db, c2)
        assert c2_node["status"] == "running"

        # c2's child should now be ready
        l2_node = GraphEngine.get_node(db, l2)
        assert l2_node["status"] == "ready"


class TestFailurePropagation:
    def test_child_failure_propagates_to_composite(self, db: psycopg.Connection) -> None:
        """When a child fails with max retries exhausted, composite is marked failed."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite = GraphEngine.add_node(db, graph_id, "group", "composite")
        leaf = GraphEngine.add_node(
            db, graph_id, "leaf", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
            max_retries=0,
        )
        GraphEngine.start_graph(db, graph_id)

        GraphEngine.mark_node_running(db, leaf)
        GraphEngine.mark_node_failed(db, leaf)

        c = GraphEngine.get_node(db, composite)
        assert c["status"] == "failed"

    def test_failure_does_not_propagate_with_retries_left(self, db: psycopg.Connection) -> None:
        """When a child fails but has retries left, composite stays running."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite = GraphEngine.add_node(db, graph_id, "group", "composite")
        leaf = GraphEngine.add_node(
            db, graph_id, "leaf", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
            max_retries=2,
        )
        GraphEngine.start_graph(db, graph_id)

        GraphEngine.mark_node_running(db, leaf)
        GraphEngine.mark_node_failed(db, leaf)

        c = GraphEngine.get_node(db, composite)
        assert c["status"] == "running"


class TestSubtreeReset:
    def test_reset_subtree(self, db: psycopg.Connection) -> None:
        """reset_subtree resets a composite and all descendants to pending."""
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")
        composite = GraphEngine.add_node(db, graph_id, "group", "composite")
        l1 = GraphEngine.add_node(
            db, graph_id, "leaf-1", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        l2 = GraphEngine.add_node(
            db, graph_id, "leaf-2", "leaf",
            agent_type="researcher", parent_node_id=composite, depth=1,
        )
        # Simulate completed state
        for nid in (composite, l1, l2):
            db.execute(
                "UPDATE execution_nodes SET status = 'completed' WHERE id = %s",
                (nid,),
            )

        GraphEngine.reset_subtree(db, composite)

        for nid in (composite, l1, l2):
            node = GraphEngine.get_node(db, nid)
            assert node["status"] == "pending"
            assert node["started_at"] is None
            assert node["completed_at"] is None


class TestCrossBranchDependencies:
    def test_cross_branch_cross_depth(self, db: psycopg.Connection) -> None:
        """A deep node can depend on a node in a different branch.

        Structure:
          composite-A (running)
            leaf-A1 (depth 1)
          composite-B (pending, depends on composite-A)
            leaf-B1 (depth 1, also depends on leaf-A1)
        """
        pid, phase_id = _create_project_and_phase(db)
        graph_id = GraphEngine.create_graph(db, pid, phase_id, "g")

        cA = GraphEngine.add_node(db, graph_id, "branch-A", "composite")
        lA1 = GraphEngine.add_node(
            db, graph_id, "task-A1", "leaf",
            agent_type="researcher", parent_node_id=cA, depth=1,
        )

        cB = GraphEngine.add_node(db, graph_id, "branch-B", "composite")
        GraphEngine.add_dependency(db, cB, cA)
        lB1 = GraphEngine.add_node(
            db, graph_id, "task-B1", "leaf",
            agent_type="researcher", parent_node_id=cB, depth=1,
        )
        GraphEngine.add_dependency(db, lB1, lA1)

        GraphEngine.start_graph(db, graph_id)

        # Only leaf-A1 should be ready
        ready = GraphEngine.get_ready_nodes(db, graph_id)
        names = [r["name"] for r in ready]
        assert names == ["task-A1"]

        # Complete leaf-A1 -> composite-A completes -> composite-B activates
        GraphEngine.mark_node_running(db, lA1)
        GraphEngine.mark_node_completed(db, lA1)

        # Now leaf-B1 should be ready (parent running + dep satisfied)
        ready = GraphEngine.get_ready_nodes(db, graph_id)
        names = [r["name"] for r in ready]
        assert "task-B1" in names

        # Complete leaf-B1 -> composite-B completes -> graph complete
        GraphEngine.mark_node_running(db, lB1)
        GraphEngine.mark_node_completed(db, lB1)

        assert GraphEngine.check_graph_complete(db, graph_id) is True
