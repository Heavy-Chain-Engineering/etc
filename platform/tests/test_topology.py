"""Tests for the topology builder module."""
from uuid import UUID

import pytest
from pydantic_ai.models.test import TestModel

from etc_platform.graph_engine import GraphEngine
from etc_platform.intake import add_source_material
from etc_platform.topology import (
    LayerSpec,
    NodeSpec,
    TopologyPlan,
    assess_topology,
    build_topology,
    generate_graph,
)


def _create_project(db, classification="re-engineering"):
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) VALUES (%s, %s, %s) RETURNING id",
        ("test-project", "/tmp/test", classification),
    ).fetchone()
    return row["id"]


def _create_phase(db, project_id, name="Decompose"):
    row = db.execute(
        "INSERT INTO phases (project_id, name) VALUES (%s, %s) RETURNING id",
        (project_id, name),
    ).fetchone()
    return row["id"]


class TestTopologyPlanModels:
    def test_node_spec(self):
        ns = NodeSpec(name="R01-compliance", agent_type="researcher")
        assert ns.name == "R01-compliance"
        assert ns.assignment == {}

    def test_node_spec_with_assignment(self):
        ns = NodeSpec(name="R01", agent_type="researcher", assignment={"scope": "compliance"})
        assert ns.assignment == {"scope": "compliance"}

    def test_layer_spec(self):
        ls = LayerSpec(
            name="domain-research",
            dimension="bounded_context",
            nodes=[NodeSpec(name="R01", agent_type="researcher")],
        )
        assert len(ls.nodes) == 1
        assert ls.dimension == "bounded_context"

    def test_topology_plan(self):
        plan = TopologyPlan(
            layers=[
                LayerSpec(name="L1", dimension="domain", nodes=[
                    NodeSpec(name="R01", agent_type="researcher"),
                    NodeSpec(name="R02", agent_type="researcher"),
                ]),
            ],
            reduce_strategy="single_synthesis",
            estimated_agents=3,
            reasoning="Two domain researchers plus synthesis",
        )
        assert plan.estimated_agents == 3
        assert len(plan.layers) == 1
        assert len(plan.layers[0].nodes) == 2

    def test_topology_plan_defaults(self):
        plan = TopologyPlan(layers=[])
        assert plan.reduce_strategy == "single_synthesis"
        assert plan.estimated_agents == 0
        assert plan.reasoning == ""


class TestGenerateGraph:
    def test_single_layer_generates_nodes(self, db):
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)

        plan = TopologyPlan(
            layers=[
                LayerSpec(name="research", dimension="domain", nodes=[
                    NodeSpec(name="R01", agent_type="researcher", assignment={"scope": "compliance"}),
                    NodeSpec(name="R02", agent_type="researcher", assignment={"scope": "vendors"}),
                ]),
            ],
            estimated_agents=3,
            reasoning="Two researchers plus synthesis",
        )

        graph_id = generate_graph(db, pid, phase_id, plan, graph_name="test-topology")

        # Verify graph created
        graph = GraphEngine.get_graph(db, graph_id)
        assert graph is not None
        assert graph["name"] == "test-topology"

        # Verify nodes: 2 leaf + 1 synthesis = 3
        nodes = GraphEngine.list_nodes(db, graph_id)
        assert len(nodes) == 3
        leaf_nodes = [n for n in nodes if n["node_type"] == "leaf"]
        reduce_nodes = [n for n in nodes if n["node_type"] == "reduce"]
        assert len(leaf_nodes) == 2
        assert len(reduce_nodes) == 1

    def test_multi_layer_dependencies(self, db):
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)

        plan = TopologyPlan(
            layers=[
                LayerSpec(name="L1-domain", dimension="domain", nodes=[
                    NodeSpec(name="R01", agent_type="researcher"),
                    NodeSpec(name="R02", agent_type="researcher"),
                ]),
                LayerSpec(name="L2-cx", dimension="cx_workflow", nodes=[
                    NodeSpec(name="CX01", agent_type="researcher"),
                ]),
            ],
            estimated_agents=4,
            reasoning="Domain research then CX analysis then synthesis",
        )

        graph_id = generate_graph(db, pid, phase_id, plan)
        nodes = GraphEngine.list_nodes(db, graph_id)

        # Should be: 2 (L1) + 1 (L2) + 1 (synthesis) = 4
        assert len(nodes) == 4

        # L1 nodes should be ready (no deps)
        l1_nodes = [n for n in nodes if n["depth"] == 0]
        assert len(l1_nodes) == 2
        assert all(n["status"] == "ready" for n in l1_nodes)

        # L2 node should be pending (depends on L1)
        l2_nodes = [n for n in nodes if n["depth"] == 1]
        assert len(l2_nodes) == 1
        assert l2_nodes[0]["status"] == "pending"

    def test_single_node_no_synthesis(self, db):
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)

        plan = TopologyPlan(
            layers=[
                LayerSpec(name="research", dimension="general", nodes=[
                    NodeSpec(name="R01", agent_type="researcher"),
                ]),
            ],
            estimated_agents=1,
            reasoning="Single researcher",
        )

        graph_id = generate_graph(db, pid, phase_id, plan)
        nodes = GraphEngine.list_nodes(db, graph_id)

        # Single node, no synthesis needed
        assert len(nodes) == 1
        assert nodes[0]["node_type"] == "leaf"

    def test_graph_starts_after_generation(self, db):
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)

        plan = TopologyPlan(
            layers=[
                LayerSpec(name="L1", dimension="domain", nodes=[
                    NodeSpec(name="R01", agent_type="researcher"),
                ]),
            ],
            estimated_agents=1,
        )

        graph_id = generate_graph(db, pid, phase_id, plan)
        graph = GraphEngine.get_graph(db, graph_id)
        assert graph["status"] == "running"

    def test_default_graph_name(self, db):
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)

        plan = TopologyPlan(
            layers=[
                LayerSpec(name="research", dimension="bounded_context", nodes=[
                    NodeSpec(name="R01", agent_type="researcher"),
                ]),
            ],
        )

        graph_id = generate_graph(db, pid, phase_id, plan)
        graph = GraphEngine.get_graph(db, graph_id)
        assert graph["name"] == "topology-bounded_context"

    def test_per_layer_then_final_strategy(self, db):
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)

        plan = TopologyPlan(
            layers=[
                LayerSpec(name="L1", dimension="domain", nodes=[
                    NodeSpec(name="R01", agent_type="researcher"),
                ]),
                LayerSpec(name="L2", dimension="cx", nodes=[
                    NodeSpec(name="CX01", agent_type="researcher"),
                ]),
            ],
            reduce_strategy="per_layer_then_final",
            estimated_agents=3,
        )

        graph_id = generate_graph(db, pid, phase_id, plan)
        nodes = GraphEngine.list_nodes(db, graph_id)

        # 1 (L1) + 1 (L2) + 1 (final-synthesis) = 3
        assert len(nodes) == 3
        reduce_nodes = [n for n in nodes if n["node_type"] == "reduce"]
        assert len(reduce_nodes) == 1
        assert reduce_nodes[0]["name"] == "final-synthesis"

    def test_leaf_node_assignments_preserved(self, db):
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)

        plan = TopologyPlan(
            layers=[
                LayerSpec(name="research", dimension="domain", nodes=[
                    NodeSpec(name="R01", agent_type="researcher", assignment={"scope": "compliance", "focus": "HIPAA"}),
                ]),
            ],
        )

        graph_id = generate_graph(db, pid, phase_id, plan)
        nodes = GraphEngine.list_nodes(db, graph_id)
        leaf = [n for n in nodes if n["node_type"] == "leaf"][0]
        assert leaf["assignment"]["scope"] == "compliance"
        assert leaf["assignment"]["focus"] == "HIPAA"

    def test_multi_layer_dependency_wiring(self, db):
        """L2 nodes depend on ALL L1 nodes."""
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)

        plan = TopologyPlan(
            layers=[
                LayerSpec(name="L1", dimension="domain", nodes=[
                    NodeSpec(name="R01", agent_type="researcher"),
                    NodeSpec(name="R02", agent_type="researcher"),
                ]),
                LayerSpec(name="L2", dimension="cx", nodes=[
                    NodeSpec(name="CX01", agent_type="researcher"),
                ]),
            ],
        )

        graph_id = generate_graph(db, pid, phase_id, plan)
        nodes = GraphEngine.list_nodes(db, graph_id)

        l1_ids = {n["id"] for n in nodes if n["depth"] == 0}
        l2_node = [n for n in nodes if n["depth"] == 1 and n["node_type"] == "leaf"][0]

        # Check CX01 depends on both R01 and R02
        deps = db.execute(
            "SELECT depends_on_node_id FROM execution_node_dependencies WHERE node_id = %s",
            (l2_node["id"],),
        ).fetchall()
        dep_ids = {d["depends_on_node_id"] for d in deps}
        assert dep_ids == l1_ids


class TestAssessTopology:
    def test_no_materials_returns_minimal_plan(self, db):
        pid = _create_project(db)
        plan = assess_topology(db, pid)
        # When no materials, returns minimal plan directly (no LLM call)
        assert len(plan.layers) == 1
        assert plan.layers[0].nodes[0].name == "general-researcher"
        assert plan.estimated_agents == 1

    def test_nonexistent_project_raises(self, db):
        from uuid import uuid4
        with pytest.raises(ValueError, match="not found"):
            assess_topology(db, uuid4())

    def test_with_materials_calls_llm(self, db):
        pid = _create_project(db)
        add_source_material(db, pid, "CX Workflows", "spreadsheet", "domain_truth", "primary")
        add_source_material(db, pid, "API Spec", "document", "requirements", "high")

        plan = assess_topology(
            db, pid,
            model_override=TestModel(
                custom_output_args={
                    "layers": [
                        {"name": "domain", "dimension": "bounded_context", "nodes": [
                            {"name": "R01", "agent_type": "researcher", "assignment": {"scope": "cx"}},
                            {"name": "R02", "agent_type": "researcher", "assignment": {"scope": "api"}},
                        ]},
                    ],
                    "reduce_strategy": "single_synthesis",
                    "estimated_agents": 3,
                    "reasoning": "Two researchers plus synthesis",
                }
            ),
        )

        assert len(plan.layers) == 1
        assert len(plan.layers[0].nodes) == 2
        assert plan.estimated_agents == 3


class TestBuildTopology:
    def test_assess_and_generate(self, db):
        pid = _create_project(db)
        phase_id = _create_phase(db, pid)
        add_source_material(db, pid, "Source A", "document", "requirements", "primary")

        plan, graph_id = build_topology(
            db, pid, phase_id,
            model_override=TestModel(
                custom_output_args={
                    "layers": [
                        {"name": "research", "dimension": "general", "nodes": [
                            {"name": "R01", "agent_type": "researcher"},
                        ]},
                    ],
                    "estimated_agents": 1,
                    "reasoning": "Single researcher",
                }
            ),
        )

        assert isinstance(plan, TopologyPlan)
        assert isinstance(graph_id, UUID)

        nodes = GraphEngine.list_nodes(db, graph_id)
        assert len(nodes) >= 1
