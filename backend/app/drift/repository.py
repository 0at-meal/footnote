"""
Repository for persisting and retrieving drift flags, comparison state, and historical graph (Feature 7, Step 4).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.9 (atomic persistence), §3.11 (isolation).
"""

import json
import logging
import os
from pathlib import Path

from app.drift.graph import HistoricalDriftGraph
from app.drift.models import DriftComparisonResult, DriftFlag
from app.drift.storage import DriftGraphStore

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class DriftRepository:
    """
    Persists and retrieves drift flags, comparison records, and the durable SQLite drift graph.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._results_dir = data_dir / "results"
        self._graph_store = DriftGraphStore(data_dir=data_dir)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def graph_store(self) -> DriftGraphStore:
        return self._graph_store

    def _ensure_dirs(self) -> None:
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def load_graph(self) -> HistoricalDriftGraph:
        """Load the authoritative historical drift graph from SQLite."""
        return self._graph_store.load_graph()

    def save_graph(self, graph: HistoricalDriftGraph) -> None:
        """Atomically persist the historical drift graph to SQLite."""
        self._graph_store.save_graph(graph)

    def save_drift_flags(self, job_id: str, flags: list[DriftFlag]) -> Path:
        """
        Atomically persist drift flags for a job to data/results/<job_id>_drift_flags.json.
        """
        self._ensure_dirs()
        dest_path = self._results_dir / f"{job_id}_drift_flags.json"
        tmp_path = self._results_dir / f"{job_id}_drift_flags.json.tmp"

        payload = [f.model_dump() for f in flags]
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def get_drift_flags(self, job_id: str) -> list[DriftFlag]:
        """
        Retrieve persisted drift flags for a job. Returns empty list if no flags file exists.
        """
        self._ensure_dirs()
        flags_path = self._results_dir / f"{job_id}_drift_flags.json"
        if not flags_path.exists():
            return []

        try:
            content = flags_path.read_text(encoding="utf-8")
            raw_data = json.loads(content)
            if isinstance(raw_data, list):
                return [DriftFlag.model_validate(item) for item in raw_data]
            return []
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.error("Failed to load drift flags for job %s: %s", job_id, err)
            return []

    def save_comparison_result(self, job_id: str, result: DriftComparisonResult) -> Path:
        """
        Atomically persist full comparison result for a job to data/results/<job_id>_drift_comparison.json.
        """
        self._ensure_dirs()
        dest_path = self._results_dir / f"{job_id}_drift_comparison.json"
        tmp_path = self._results_dir / f"{job_id}_drift_comparison.json.tmp"

        tmp_path.write_text(
            json.dumps(result.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def get_comparison_result(self, job_id: str) -> DriftComparisonResult | None:
        """
        Retrieve persisted DriftComparisonResult for a job, if available.
        """
        self._ensure_dirs()
        comp_path = self._results_dir / f"{job_id}_drift_comparison.json"
        if not comp_path.exists():
            return None

        try:
            content = comp_path.read_text(encoding="utf-8")
            raw_data = json.loads(content)
            if isinstance(raw_data, dict):
                return DriftComparisonResult.model_validate(raw_data)
            return None
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.error("Failed to load drift comparison for job %s: %s", job_id, err)
            return None
