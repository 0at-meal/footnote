"""
Unit tests for HistoricalDriftGraph (Feature 7, Step 3).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.4 (pure graph state management), spec §3, AC-3, AC-6, EC-1, EC-9.
"""

import pytest
from app.drift.comparator import compare_metric_components
from app.drift.graph import HistoricalDriftGraph
from app.drift.models import DriftEdgeType


def test_graph_initializes_baseline_node() -> None:
    graph = HistoricalDriftGraph()
    comp = compare_metric_components(
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        current_labels=["Depreciation", "Stock-Based Comp"],
        prior_node=None,
    )

    node, edge = graph.apply_comparison(comp)
    assert node.entity == "ACME"
    assert node.target_metric == "Adjusted EBITDA"
    assert node.filing_year == 2022
    assert node.component_labels == ["Depreciation", "Stock-Based Comp"]
    assert edge is None

    latest = graph.get_latest_node("ACME", "Adjusted EBITDA")
    assert latest is not None
    assert latest.node_id == node.node_id


def test_graph_creates_new_node_and_edge_on_redefinition() -> None:
    graph = HistoricalDriftGraph()

    # Baseline 2022
    comp_2022 = compare_metric_components(
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        current_labels=["Depreciation", "Stock-Based Comp"],
        prior_node=None,
    )
    node_2022, _ = graph.apply_comparison(comp_2022)

    # Redefinition 2023
    comp_2023 = compare_metric_components(
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        current_labels=["Depreciation", "Stock-Based Comp", "Litigation Settlement"],
        prior_node=node_2022,
    )
    node_2023, edge_2023 = graph.apply_comparison(comp_2023)

    assert node_2023.node_id != node_2022.node_id
    assert node_2023.filing_year == 2023
    assert edge_2023 is not None
    assert edge_2023.from_node_id == node_2022.node_id
    assert edge_2023.to_node_id == node_2023.node_id
    assert edge_2023.edge_type == DriftEdgeType.redefinition
    assert edge_2023.added_labels == ["Litigation Settlement"]
    assert edge_2023.removed_labels == []

    latest = graph.get_latest_node("ACME", "Adjusted EBITDA")
    assert latest is not None
    assert latest.node_id == node_2023.node_id


def test_graph_reuses_existing_node_on_continuation() -> None:
    graph = HistoricalDriftGraph()

    # Baseline 2022
    comp_2022 = compare_metric_components(
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        current_labels=["Depreciation", "Stock-Based Comp"],
        prior_node=None,
    )
    node_2022, _ = graph.apply_comparison(comp_2022)

    # Continuation 2023 (same component set)
    comp_2023 = compare_metric_components(
        entity="ACME",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        current_labels=["Depreciation", "Stock-Based Comp"],
        prior_node=node_2022,
    )
    node_2023, edge_2023 = graph.apply_comparison(comp_2023)

    # AC-6: Node is reused
    assert node_2023.node_id == node_2022.node_id
    assert edge_2023 is not None
    assert edge_2023.from_node_id == node_2022.node_id
    assert edge_2023.to_node_id == node_2022.node_id
    assert edge_2023.edge_type == DriftEdgeType.continuation

    # Node count remains 1
    nodes = graph.get_nodes(entity="ACME", target_metric="Adjusted EBITDA")
    assert len(nodes) == 1


def test_graph_multi_year_lifecycle() -> None:
    graph = HistoricalDriftGraph()

    # 1. 2021: Baseline
    n1, _ = graph.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2021, ["A", "B"], None)
    )

    # 2. 2022: Redefinition (add C)
    n2, e2 = graph.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2022, ["A", "B", "C"], n1)
    )
    assert n2.node_id != n1.node_id
    assert e2 is not None and e2.edge_type == DriftEdgeType.redefinition

    # 3. 2023: Continuation (same)
    n3, e3 = graph.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2023, ["A", "B", "C"], n2)
    )
    assert n3.node_id == n2.node_id
    assert e3 is not None and e3.edge_type == DriftEdgeType.continuation

    # 4. 2024: Redefinition (remove A, add D)
    n4, e4 = graph.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2024, ["B", "C", "D"], n3)
    )
    assert n4.node_id != n2.node_id
    assert e4 is not None and e4.edge_type == DriftEdgeType.redefinition
    assert e4.added_labels == ["D"]
    assert e4.removed_labels == ["A"]

    history = graph.get_history("ACME", "Adjusted EBITDA")
    assert len(history) == 3  # 3 distinct definition nodes (2021, 2022, 2024)

    edges = graph.get_edges("ACME", "Adjusted EBITDA")
    assert len(edges) == 3


def test_graph_entity_isolation() -> None:
    graph = HistoricalDriftGraph()

    # ACME baseline
    n_acme, _ = graph.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2022, ["LabelA"], None)
    )

    # BETA baseline (identical labels)
    n_beta, _ = graph.apply_comparison(
        compare_metric_components("BETA", "Adjusted EBITDA", 2022, ["LabelA"], None)
    )

    # EC-9: Separate nodes, no cross-linkage
    assert n_acme.node_id != n_beta.node_id
    assert graph.get_latest_node("ACME", "Adjusted EBITDA") == n_acme
    assert graph.get_latest_node("BETA", "Adjusted EBITDA") == n_beta

    acme_nodes = graph.get_nodes(entity="ACME")
    beta_nodes = graph.get_nodes(entity="BETA")
    assert len(acme_nodes) == 1
    assert len(beta_nodes) == 1


def test_graph_serialization_round_trip() -> None:
    graph = HistoricalDriftGraph()
    n1, _ = graph.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2022, ["A", "B"], None)
    )
    n2, _e2 = graph.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2023, ["A", "B", "C"], n1)
    )

    serialized = graph.to_dict()
    assert "nodes" in serialized
    assert "edges" in serialized
    assert "latest_nodes" in serialized

    restored = HistoricalDriftGraph.from_dict(serialized)
    latest_restored = restored.get_latest_node("ACME", "Adjusted EBITDA")
    assert latest_restored is not None
    assert latest_restored.node_id == n2.node_id
    assert len(restored.get_nodes()) == 2
    assert len(restored.get_edges()) == 1


def test_graph_invalid_prior_node_raises_error() -> None:
    graph = HistoricalDriftGraph()
    with pytest.raises(ValueError, match="does not exist in graph"):
        graph.add_redefinition_node(
            prior_node_id="non_existent_node",
            entity="ACME",
            target_metric="Adjusted EBITDA",
            filing_year=2023,
            component_labels=["A"],
            added_labels=["A"],
            removed_labels=[],
        )
