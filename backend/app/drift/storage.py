"""
SQLite-backed persistence storage for HistoricalDriftGraph (Feature 7, Step 4).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.9 (atomic persistence), §4.5 (SQLite only).
"""

import json
import logging
import sqlite3
from pathlib import Path

from app.drift.graph import HistoricalDriftGraph
from app.drift.models import DriftEdge, DriftEdgeType

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class DriftGraphStore:
    """
    Durable SQLite storage for HistoricalDriftGraph ensuring ACID atomicity and restart durability.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._db_path = data_dir / "drift.db"
        self._ensure_dirs()
        self._init_db()

    def _ensure_dirs(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create database tables if they do not already exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drift_nodes (
                    node_id TEXT PRIMARY KEY,
                    entity TEXT NOT NULL,
                    target_metric TEXT NOT NULL,
                    filing_year INTEGER NOT NULL,
                    component_labels TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drift_edges (
                    edge_id TEXT PRIMARY KEY,
                    from_node_id TEXT NOT NULL,
                    to_node_id TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    target_metric TEXT NOT NULL,
                    filing_year INTEGER NOT NULL,
                    edge_type TEXT NOT NULL,
                    added_labels TEXT NOT NULL,
                    removed_labels TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drift_latest_nodes (
                    entity TEXT NOT NULL,
                    target_metric TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    PRIMARY KEY (entity, target_metric)
                )
                """
            )

    def save_graph(self, graph: HistoricalDriftGraph) -> None:
        """
        Atomically persist all nodes, edges, and latest-node pointers to SQLite in a single transaction (AC-7, AC-10).
        """
        nodes = graph.get_nodes()
        edges = graph.get_edges()
        latest_nodes = graph._latest_nodes

        with self._get_connection() as conn:
            # Clear existing records and re-insert state atomically
            conn.execute("DELETE FROM drift_nodes")
            conn.execute("DELETE FROM drift_edges")
            conn.execute("DELETE FROM drift_latest_nodes")

            for node in nodes:
                conn.execute(
                    """
                    INSERT INTO drift_nodes (node_id, entity, target_metric, filing_year, component_labels, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node.node_id,
                        node.entity,
                        node.target_metric,
                        node.filing_year,
                        json.dumps(node.component_labels, ensure_ascii=False),
                        node.created_at,
                    ),
                )

            for edge in edges:
                conn.execute(
                    """
                    INSERT INTO drift_edges (edge_id, from_node_id, to_node_id, entity, target_metric, filing_year, edge_type, added_labels, removed_labels, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge.edge_id,
                        edge.from_node_id,
                        edge.to_node_id,
                        edge.entity,
                        edge.target_metric,
                        edge.filing_year,
                        edge.edge_type.value,
                        json.dumps(edge.added_labels, ensure_ascii=False),
                        json.dumps(edge.removed_labels, ensure_ascii=False),
                        edge.created_at,
                    ),
                )

            for (ent, metric), node_id in latest_nodes.items():
                conn.execute(
                    """
                    INSERT INTO drift_latest_nodes (entity, target_metric, node_id)
                    VALUES (?, ?, ?)
                    """,
                    (ent, metric, node_id),
                )

    def load_graph(self) -> HistoricalDriftGraph:
        """
        Load the authoritative HistoricalDriftGraph from SQLite (AC-1, NFR7).
        """
        graph = HistoricalDriftGraph()
        with self._get_connection() as conn:
            # Load nodes
            cursor = conn.execute(
                "SELECT node_id, entity, target_metric, filing_year, component_labels, created_at FROM drift_nodes"
            )
            for row in cursor.fetchall():
                node_id = str(row["node_id"])
                entity = str(row["entity"])
                target_metric = str(row["target_metric"])
                filing_year = int(row["filing_year"])
                raw_labels = json.loads(str(row["component_labels"]))
                component_labels = [str(lbl) for lbl in raw_labels] if isinstance(raw_labels, list) else []
                created_at = str(row["created_at"])

                graph._graph.add_node(
                    node_id,
                    entity=entity,
                    target_metric=target_metric,
                    filing_year=filing_year,
                    component_labels=component_labels,
                    created_at=created_at,
                )

            # Load edges
            cursor = conn.execute(
                """
                SELECT edge_id, from_node_id, to_node_id, entity, target_metric, filing_year, edge_type, added_labels, removed_labels, created_at
                FROM drift_edges
                """
            )
            for row in cursor.fetchall():
                edge_id = str(row["edge_id"])
                from_node_id = str(row["from_node_id"])
                to_node_id = str(row["to_node_id"])
                entity = str(row["entity"])
                target_metric = str(row["target_metric"])
                filing_year = int(row["filing_year"])
                edge_type = DriftEdgeType(str(row["edge_type"]))
                raw_added = json.loads(str(row["added_labels"]))
                added_labels = [str(lbl) for lbl in raw_added] if isinstance(raw_added, list) else []
                raw_removed = json.loads(str(row["removed_labels"]))
                removed_labels = [str(lbl) for lbl in raw_removed] if isinstance(raw_removed, list) else []
                created_at = str(row["created_at"])

                edge = DriftEdge(
                    edge_id=edge_id,
                    from_node_id=from_node_id,
                    to_node_id=to_node_id,
                    entity=entity,
                    target_metric=target_metric,
                    filing_year=filing_year,
                    edge_type=edge_type,
                    added_labels=added_labels,
                    removed_labels=removed_labels,
                    created_at=created_at,
                )
                graph._edges.append(edge)
                if graph._graph.has_node(from_node_id) and graph._graph.has_node(to_node_id):
                    graph._graph.add_edge(
                        from_node_id,
                        to_node_id,
                        edge_id=edge_id,
                        edge_type=edge_type.value,
                        filing_year=filing_year,
                        added_labels=added_labels,
                        removed_labels=removed_labels,
                        created_at=created_at,
                    )

            # Load latest nodes
            cursor = conn.execute("SELECT entity, target_metric, node_id FROM drift_latest_nodes")
            for row in cursor.fetchall():
                ent = str(row["entity"])
                metric = str(row["target_metric"])
                n_id = str(row["node_id"])
                graph._latest_nodes[(ent, metric)] = n_id

        return graph
