"""
NetworkX-backed historical drift graph implementation (Feature 7, Step 3).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.4 (pure graph state management), §3.11 (isolation).
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import networkx as nx  # type: ignore[import-untyped]

from app.drift.models import (
    DriftComparisonResult,
    DriftEdge,
    DriftEdgeType,
    DriftGraphExport,
    MetricDefinitionNode,
)


class HistoricalDriftGraph:
    """
    Manages the historical drift graph using NetworkX DiGraph.

    Invariants:
    - Append-only for definition nodes and transitions (spec §3).
    - Keyed by (entity, target_metric) at the top level.
    - Existing definition nodes are reused if component sets are identical across filings (AC-6).
    """

    def __init__(self) -> None:
        self._graph = nx.DiGraph()
        # Mapping from (entity, target_metric) to the latest MetricDefinitionNode ID
        self._latest_nodes: dict[tuple[str, str], str] = {}
        # Explicit edge registry to preserve multi-edge/continuation records cleanly
        self._edges: list[DriftEdge] = []

    def get_latest_node(
        self, entity: str, target_metric: str
    ) -> MetricDefinitionNode | None:
        """
        Retrieve the most recent definition node for a given (entity, target_metric) pair.
        """
        node_id = self._latest_nodes.get((entity, target_metric))
        if node_id is None:
            return None
        return self._node_from_id(node_id)

    def _node_from_id(self, node_id: str) -> MetricDefinitionNode | None:
        if not self._graph.has_node(node_id):
            return None
        node_data = self._graph.nodes[node_id]
        return MetricDefinitionNode(
            node_id=node_id,
            entity=node_data["entity"],
            target_metric=node_data["target_metric"],
            filing_year=node_data["filing_year"],
            component_labels=list(node_data.get("component_labels", [])),
            created_at=node_data["created_at"],
        )

    def add_baseline_node(
        self,
        entity: str,
        target_metric: str,
        filing_year: int,
        component_labels: list[str],
    ) -> MetricDefinitionNode:
        """
        Initialize a baseline definition node for a new (entity, target_metric) pair (AC-3, EC-10).
        """
        node_id = f"node_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        node = MetricDefinitionNode(
            node_id=node_id,
            entity=entity,
            target_metric=target_metric,
            filing_year=filing_year,
            component_labels=sorted(set(component_labels)),
            created_at=created_at,
        )

        self._graph.add_node(
            node_id,
            entity=entity,
            target_metric=target_metric,
            filing_year=filing_year,
            component_labels=node.component_labels,
            created_at=created_at,
        )
        self._latest_nodes[(entity, target_metric)] = node_id
        return node

    def add_redefinition_node(
        self,
        prior_node_id: str,
        entity: str,
        target_metric: str,
        filing_year: int,
        component_labels: list[str],
        added_labels: list[str],
        removed_labels: list[str],
    ) -> tuple[MetricDefinitionNode, DriftEdge]:
        """
        Add a new definition node and a directed redefinition edge from prior_node_id (spec §3, AC-2, AC-4).
        """
        if not self._graph.has_node(prior_node_id):
            raise ValueError(
                f"Prior definition node '{prior_node_id}' does not exist in graph."
            )

        new_node_id = f"node_{uuid.uuid4().hex[:12]}"
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_node = MetricDefinitionNode(
            node_id=new_node_id,
            entity=entity,
            target_metric=target_metric,
            filing_year=filing_year,
            component_labels=sorted(set(component_labels)),
            created_at=now_ts,
        )

        self._graph.add_node(
            new_node_id,
            entity=entity,
            target_metric=target_metric,
            filing_year=filing_year,
            component_labels=new_node.component_labels,
            created_at=now_ts,
        )

        edge_id = f"edge_{uuid.uuid4().hex[:12]}"
        edge = DriftEdge(
            edge_id=edge_id,
            from_node_id=prior_node_id,
            to_node_id=new_node_id,
            entity=entity,
            target_metric=target_metric,
            filing_year=filing_year,
            edge_type=DriftEdgeType.redefinition,
            added_labels=sorted(added_labels),
            removed_labels=sorted(removed_labels),
            created_at=now_ts,
        )

        self._graph.add_edge(
            prior_node_id,
            new_node_id,
            edge_id=edge.edge_id,
            edge_type=edge.edge_type.value,
            filing_year=filing_year,
            added_labels=edge.added_labels,
            removed_labels=edge.removed_labels,
            created_at=now_ts,
        )
        self._edges.append(edge)
        self._latest_nodes[(entity, target_metric)] = new_node_id
        return new_node, edge

    def add_continuation_edge(
        self,
        node_id: str,
        entity: str,
        target_metric: str,
        filing_year: int,
    ) -> DriftEdge:
        """
        Record a continuation edge reusing the existing definition node (AC-6).
        """
        if not self._graph.has_node(node_id):
            raise ValueError(f"Definition node '{node_id}' does not exist in graph.")

        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        edge_id = f"edge_{uuid.uuid4().hex[:12]}"

        edge = DriftEdge(
            edge_id=edge_id,
            from_node_id=node_id,
            to_node_id=node_id,
            entity=entity,
            target_metric=target_metric,
            filing_year=filing_year,
            edge_type=DriftEdgeType.continuation,
            added_labels=[],
            removed_labels=[],
            created_at=now_ts,
        )

        self._edges.append(edge)
        return edge

    def apply_comparison(
        self,
        comparison: DriftComparisonResult,
    ) -> tuple[MetricDefinitionNode, DriftEdge | None]:
        """
        Apply a DriftComparisonResult to update the historical graph state.

        - Baseline year -> Creates baseline node, returns (node, None).
        - Discrepancy detected -> Creates new node and redefinition edge, returns (new_node, edge).
        - No discrepancy -> Reuses prior node and adds continuation edge, returns (existing_node, edge).
        """
        if comparison.is_baseline or comparison.prior_node_id is None:
            baseline_node = self.add_baseline_node(
                entity=comparison.entity,
                target_metric=comparison.target_metric,
                filing_year=comparison.filing_year,
                component_labels=comparison.current_labels,
            )
            return baseline_node, None

        if comparison.has_discrepancy:
            new_node, edge = self.add_redefinition_node(
                prior_node_id=comparison.prior_node_id,
                entity=comparison.entity,
                target_metric=comparison.target_metric,
                filing_year=comparison.filing_year,
                component_labels=comparison.current_labels,
                added_labels=comparison.added_labels,
                removed_labels=comparison.removed_labels,
            )
            return new_node, edge

        # Identical definition -> reuse existing node (AC-6)
        existing_node = self._node_from_id(comparison.prior_node_id)
        if existing_node is None:
            # Fallback to creating baseline if prior node ID is missing from graph
            return (
                self.add_baseline_node(
                    entity=comparison.entity,
                    target_metric=comparison.target_metric,
                    filing_year=comparison.filing_year,
                    component_labels=comparison.current_labels,
                ),
                None,
            )

        continuation_edge = self.add_continuation_edge(
            node_id=comparison.prior_node_id,
            entity=comparison.entity,
            target_metric=comparison.target_metric,
            filing_year=comparison.filing_year,
        )
        return existing_node, continuation_edge

    def get_nodes(
        self,
        entity: str | None = None,
        target_metric: str | None = None,
    ) -> list[MetricDefinitionNode]:
        """
        Retrieve definition nodes, optionally filtered by entity and target_metric.
        """
        nodes: list[MetricDefinitionNode] = []
        for n_id in self._graph.nodes:
            node = self._node_from_id(n_id)
            if node is None:
                continue
            if entity is not None and node.entity != entity:
                continue
            if target_metric is not None and node.target_metric != target_metric:
                continue
            nodes.append(node)
        return sorted(nodes, key=lambda n: (n.entity, n.target_metric, n.filing_year))

    def get_edges(
        self,
        entity: str | None = None,
        target_metric: str | None = None,
    ) -> list[DriftEdge]:
        """
        Retrieve transition edges, optionally filtered by entity and target_metric.
        """
        edges: list[DriftEdge] = []
        for edge in self._edges:
            if entity is not None and edge.entity != entity:
                continue
            if target_metric is not None and edge.target_metric != target_metric:
                continue
            edges.append(edge)
        return sorted(edges, key=lambda e: (e.entity, e.target_metric, e.filing_year))

    def get_history(
        self, entity: str, target_metric: str
    ) -> list[MetricDefinitionNode]:
        """
        Retrieve chronological sequence of distinct definition nodes for an (entity, target_metric) pair.
        """
        return self.get_nodes(entity=entity, target_metric=target_metric)

    def export_graph(
        self,
        entity: str | None = None,
        target_metric: str | None = None,
    ) -> DriftGraphExport:
        """
        Export graph nodes and edges as a DriftGraphExport payload.
        """
        nodes = self.get_nodes(entity=entity, target_metric=target_metric)
        edges = self.get_edges(entity=entity, target_metric=target_metric)
        return DriftGraphExport(
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize graph to dictionary representation for persistence."""
        return {
            "nodes": [n.model_dump() for n in self.get_nodes()],
            "edges": [e.model_dump() for e in self._edges],
            "latest_nodes": {
                f"{k[0]}::{k[1]}": v for k, v in self._latest_nodes.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoricalDriftGraph":
        """Reconstruct a HistoricalDriftGraph from serialized dictionary."""
        graph = cls()
        for node_data in data.get("nodes", []):
            node = MetricDefinitionNode.model_validate(node_data)
            graph._graph.add_node(
                node.node_id,
                entity=node.entity,
                target_metric=node.target_metric,
                filing_year=node.filing_year,
                component_labels=node.component_labels,
                created_at=node.created_at,
            )
        for edge_data in data.get("edges", []):
            edge = DriftEdge.model_validate(edge_data)
            graph._edges.append(edge)
            if graph._graph.has_node(edge.from_node_id) and graph._graph.has_node(
                edge.to_node_id
            ):
                graph._graph.add_edge(
                    edge.from_node_id,
                    edge.to_node_id,
                    edge_id=edge.edge_id,
                    edge_type=edge.edge_type.value,
                    filing_year=edge.filing_year,
                    added_labels=edge.added_labels,
                    removed_labels=edge.removed_labels,
                    created_at=edge.created_at,
                )
        for k_str, node_id in data.get("latest_nodes", {}).items():
            if "::" in k_str:
                ent, metric = k_str.split("::", 1)
                graph._latest_nodes[(ent, metric)] = node_id
        return graph
