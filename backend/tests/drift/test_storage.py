"""
Unit tests for SQLite DriftGraphStore persistence (Feature 7, Step 4).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.9 (atomic persistence), spec §4, AC-1, AC-7, AC-10.
"""

from pathlib import Path

from app.drift.comparator import compare_metric_components
from app.drift.graph import HistoricalDriftGraph
from app.drift.models import DriftEdgeType
from app.drift.storage import DriftGraphStore


def test_drift_graph_store_save_and_load_restart_simulation(tmp_path: Path) -> None:
    """
    Test that graph state survives a backend restart simulation by reloading
    from a brand new DriftGraphStore instance pointing to the persisted SQLite DB (AC-1, NFR7).
    """
    store1 = DriftGraphStore(data_dir=tmp_path)
    graph1 = HistoricalDriftGraph()

    # Step 1: Baseline 2022
    n1, _ = graph1.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2022, ["Depreciation", "SBC"], None)
    )

    # Step 2: Redefinition 2023 (add Litigation)
    n2, _e2 = graph1.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2023, ["Depreciation", "SBC", "Litigation"], n1)
    )

    # Step 3: Continuation 2024
    n3, _e3 = graph1.apply_comparison(
        compare_metric_components("ACME", "Adjusted EBITDA", 2024, ["Depreciation", "SBC", "Litigation"], n2)
    )

    # Save to SQLite
    store1.save_graph(graph1)

    # Simulate backend restart: create a new DriftGraphStore instance
    store2 = DriftGraphStore(data_dir=tmp_path)
    restored_graph = store2.load_graph()

    # Verify latest node pointer survived
    latest = restored_graph.get_latest_node("ACME", "Adjusted EBITDA")
    assert latest is not None
    assert latest.node_id == n3.node_id
    assert latest.node_id == n2.node_id
    assert latest.component_labels == ["Depreciation", "Litigation", "SBC"]

    # Verify nodes
    nodes = restored_graph.get_nodes(entity="ACME", target_metric="Adjusted EBITDA")
    assert len(nodes) == 2  # 2022 baseline node and 2023 redefinition node
    assert nodes[0].node_id == n1.node_id
    assert nodes[1].node_id == n2.node_id

    # Verify edges
    edges = restored_graph.get_edges(entity="ACME", target_metric="Adjusted EBITDA")
    assert len(edges) == 2
    assert edges[0].edge_type == DriftEdgeType.redefinition
    assert edges[0].added_labels == ["Litigation"]
    assert edges[1].edge_type == DriftEdgeType.continuation


def test_drift_graph_store_empty_db_loads_empty_graph(tmp_path: Path) -> None:
    store = DriftGraphStore(data_dir=tmp_path)
    graph = store.load_graph()
    assert len(graph.get_nodes()) == 0
    assert len(graph.get_edges()) == 0
    assert graph.get_latest_node("NONEXISTENT", "Adjusted EBITDA") is None
