"""Topology Builder — generates multi-layer execution graphs from source material inventory.

Two-stage process:
1. Assessment: Analyze source materials + classification → TopologyPlan (via LLM or rules)
2. Graph generation: Convert TopologyPlan → execution graph nodes + dependencies
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import psycopg
from pydantic import BaseModel
from pydantic_ai import Agent

from etc_platform.graph_engine import GraphEngine

logger = logging.getLogger(__name__)


# ===========================================================================
# Topology plan models
# ===========================================================================


class NodeSpec(BaseModel):
    """Specification for a single execution node."""
    name: str
    agent_type: str
    assignment: dict[str, Any] = {}


class LayerSpec(BaseModel):
    """Specification for one layer of the topology."""
    name: str
    dimension: str  # e.g., "bounded_context", "cx_workflow", "migration"
    nodes: list[NodeSpec]


class TopologyPlan(BaseModel):
    """Complete topology plan ready for graph generation."""
    layers: list[LayerSpec]
    reduce_strategy: str = "single_synthesis"  # "single_synthesis" | "per_layer_then_final"
    estimated_agents: int = 0
    reasoning: str = ""


# ===========================================================================
# Assessment (stage 1)
# ===========================================================================


def assess_topology(
    conn: psycopg.Connection,
    project_id: UUID,
    model: str = "anthropic:claude-sonnet-4-20250514",
    model_override: Any | None = None,
) -> TopologyPlan:
    """Assess source materials and produce a TopologyPlan.

    For MVP: calls an LLM to analyze the source material inventory
    and recommend a decomposition strategy.

    Args:
        conn: Database connection.
        project_id: Project to assess.
        model: Model to use for assessment.
        model_override: Optional model override (e.g., TestModel for testing).

    Returns:
        TopologyPlan with layers, nodes, and reduce strategy.
    """
    # Load project info
    project = conn.execute(
        "SELECT name, classification FROM projects WHERE id = %s",
        (project_id,),
    ).fetchone()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    # Load source materials
    from etc_platform.intake import list_source_materials, triage_summary
    materials = list_source_materials(conn, project_id)
    summary = triage_summary(conn, project_id)

    if not materials:
        # No materials: return a minimal single-agent plan
        return TopologyPlan(
            layers=[
                LayerSpec(
                    name="research",
                    dimension="general",
                    nodes=[NodeSpec(name="general-researcher", agent_type="researcher")],
                )
            ],
            estimated_agents=1,
            reasoning="No source materials found. Single researcher assigned.",
        )

    # Use LLM to assess topology
    agent: Agent[None, TopologyPlan] = Agent(
        model,
        output_type=TopologyPlan,
        system_prompt=_ASSESSMENT_PROMPT,
        defer_model_check=True,
    )

    # Build user prompt with material inventory
    material_lines = []
    for m in materials:
        line = f"- [{m['priority']}] {m['name']} ({m['type']}/{m['classification']})"
        if m.get("reading_instructions"):
            line += f" — {m['reading_instructions']}"
        material_lines.append(line)

    user_prompt = (
        f"Project: {project['name']}\n"
        f"Classification: {project['classification']}\n\n"
        f"Source Materials:\n" + "\n".join(material_lines) + "\n\n"
        f"Summary:\n{summary}\n\n"
        f"Design the execution topology for this project."
    )

    if model_override is not None:
        with agent.override(model=model_override):
            result = agent.run_sync(user_prompt)
    else:
        result = agent.run_sync(user_prompt)

    return result.output


_ASSESSMENT_PROMPT = """\
You are a topology planner for the ETC Orchestration Platform. Given a project's \
source material inventory and classification, design an execution topology.

Your output is a TopologyPlan with:
- layers: List of LayerSpec, each containing a dimension name and NodeSpec list
- reduce_strategy: "single_synthesis" (one synthesis agent after all layers) or \
"per_layer_then_final" (synthesis per layer, then final synthesis)
- estimated_agents: Total agent count
- reasoning: Why you chose this decomposition

Design principles:
- Each leaf node should be scoped to fit in one agent's context
- Group by natural dimensions (bounded contexts, workflow types, concerns)
- Primary materials drive the main decomposition dimensions
- Re-engineering projects need extra attention to avoid reproducing legacy patterns
- Use reduce nodes when parallel outputs need synthesis
- Prefer fewer, well-scoped agents over many overlapping ones
"""


# ===========================================================================
# Graph generation (stage 2)
# ===========================================================================


def generate_graph(
    conn: psycopg.Connection,
    project_id: UUID,
    phase_id: UUID,
    plan: TopologyPlan,
    graph_name: str | None = None,
) -> UUID:
    """Convert a TopologyPlan into an execution graph with nodes and dependencies.

    Creates:
    - One execution_graph
    - Leaf nodes for each layer's nodes
    - Dependencies: each layer depends on the previous layer's completion
    - Reduce node(s) based on reduce_strategy

    Args:
        conn: Database connection.
        project_id: Project ID.
        phase_id: Phase to attach the graph to.
        plan: The TopologyPlan to convert.
        graph_name: Optional name for the graph.

    Returns:
        The graph_id UUID.
    """
    name = graph_name or f"topology-{plan.layers[0].dimension if plan.layers else 'auto'}"

    graph_id = GraphEngine.create_graph(
        conn=conn,
        project_id=project_id,
        phase_id=phase_id,
        name=name,
        description=plan.reasoning,
    )

    # Track nodes per layer for dependency wiring
    previous_layer_node_ids: list[UUID] = []
    all_leaf_node_ids: list[UUID] = []

    for layer_idx, layer in enumerate(plan.layers):
        current_layer_node_ids: list[UUID] = []

        for node_spec in layer.nodes:
            node_id = GraphEngine.add_node(
                conn=conn,
                graph_id=graph_id,
                node_type="leaf",
                name=node_spec.name,
                agent_type=node_spec.agent_type,
                assignment=node_spec.assignment,
                depth=layer_idx,
            )
            current_layer_node_ids.append(node_id)
            all_leaf_node_ids.append(node_id)

            # Add dependencies on all nodes from previous layer
            for dep_id in previous_layer_node_ids:
                GraphEngine.add_dependency(conn, node_id, dep_id)

        previous_layer_node_ids = current_layer_node_ids

    # Add reduce/synthesis node(s)
    if plan.reduce_strategy == "per_layer_then_final" and len(plan.layers) > 1:
        # Final synthesis depends on the last layer
        synthesis_id = GraphEngine.add_node(
            conn=conn,
            graph_id=graph_id,
            node_type="reduce",
            name="final-synthesis",
            agent_type="researcher",
            assignment={"task": "Synthesize all research outputs into a unified report"},
            depth=len(plan.layers),
        )
        for dep_id in previous_layer_node_ids:
            GraphEngine.add_dependency(conn, synthesis_id, dep_id)

    elif len(all_leaf_node_ids) > 1:
        # Single synthesis after all leaves
        synthesis_id = GraphEngine.add_node(
            conn=conn,
            graph_id=graph_id,
            node_type="reduce",
            name="synthesis",
            agent_type="researcher",
            assignment={"task": "Synthesize all research outputs into a unified report"},
            depth=len(plan.layers),
        )
        for dep_id in previous_layer_node_ids:
            GraphEngine.add_dependency(conn, synthesis_id, dep_id)

    # Start the graph (promotes zero-dep nodes to 'ready')
    GraphEngine.start_graph(conn, graph_id)

    return graph_id


# ===========================================================================
# Convenience: assess + generate in one call
# ===========================================================================


def build_topology(
    conn: psycopg.Connection,
    project_id: UUID,
    phase_id: UUID,
    model: str = "anthropic:claude-sonnet-4-20250514",
    model_override: Any | None = None,
    graph_name: str | None = None,
) -> tuple[TopologyPlan, UUID]:
    """Assess and generate a topology in one call.

    Returns (plan, graph_id).
    """
    plan = assess_topology(conn, project_id, model=model, model_override=model_override)
    graph_id = generate_graph(conn, project_id, phase_id, plan, graph_name=graph_name)
    return plan, graph_id
