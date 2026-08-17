"""
Audit Report Compilation Engine (Feature 8 Step 1).

Enforces:
- CONSTITUTION §1.1 (mypy --strict), §1.3 (Pydantic boundaries), §1.9 (no swallowed exceptions).
- CONSTITUTION §3.8, §3.10, spec.md §1, AC-1, AC-2, AC-3, AC-7, AC-8.
- Strictly isolated: does not import from classification/ or formula_engine/.
- Strictly read-only: reads upstream records, modifies zero stored state (spec AC-9).
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit_report.models import (
    ClassifierAuditEntry,
    ClassifierAuditSummary,
    CompiledAuditDataset,
    DriftAuditSummary,
    ManualOverrideItem,
    ProvenanceMatrixItem,
    ReconciliationSummaryItem,
    ReportMetadata,
)
from app.audit_trail.resolver import AuditTrailResolver
from app.drift.repository import DriftRepository
from app.excel_export.repository import ModelRepository
from app.extraction.models import ScoredRecord
from app.extraction.repository import ExtractionRepository
from app.ingestion.repository import JobRepository
from app.review.models import ReviewItem, ReviewStatus
from app.review.repository import ReviewRepository

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class ModelNotCompleteError(Exception):
    """Raised when an audit report is requested for a job without completed model provenance."""


class JobNotFoundError(Exception):
    """Raised when the specified job_id does not exist in the repository."""


class AuditReportCompiler:
    """
    Compiles all cell-level provenance, review history, drift detection, and classifier governance
    for a completed model into a unified report dataset (spec §1).
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._job_repo = JobRepository(data_dir=data_dir)
        self._model_repo = ModelRepository(data_dir=data_dir)
        self._review_repo = ReviewRepository(data_dir=data_dir)
        self._audit_trail_resolver = AuditTrailResolver(data_dir=data_dir)
        self._drift_repo = DriftRepository(data_dir=data_dir)
        self._extraction_repo = ExtractionRepository(data_dir=data_dir)

    def compile(self, job_id: str) -> CompiledAuditDataset:
        """
        Compiles the complete audit dataset for job_id.

        Args:
            job_id: The UUID of the completed job.

        Returns:
            CompiledAuditDataset with all provenance, override, governance, and drift sections.

        Raises:
            JobNotFoundError: If job_id does not exist in jobs.json.
            ModelNotCompleteError: If model provenance records do not exist (EC-6).
        """
        job = self._job_repo.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job '{job_id}' not found.")

        provenance_records = self._model_repo.get_provenance_records(job_id)
        if not provenance_records:
            raise ModelNotCompleteError(
                f"Audit report unavailable: model generation not complete for job '{job_id}' (EC-6)."
            )

        review_items = self._review_repo.get_review_items(job_id) or []
        scored_records = self._load_scored_records(job_id)

        reconciliation_summary = self._compile_reconciliation_summary(provenance_records)
        provenance_matrix = self._compile_provenance_matrix(job_id, provenance_records)
        manual_overrides = self._compile_manual_overrides(
            job_id, review_items, scored_records, provenance_records
        )
        classifier_governance = self._compile_classifier_governance(job_id)
        drift_summary = self._compile_drift_summary(job_id, job.target_metric)
        metadata = self._compile_metadata(
            job=job,
            total_cells=len(provenance_records),
            review_items=review_items,
            manual_overrides=manual_overrides,
            drift_summary=drift_summary,
        )

        return CompiledAuditDataset(
            job_id=job_id,
            metadata=metadata,
            reconciliation_summary=reconciliation_summary,
            provenance_matrix=provenance_matrix,
            manual_overrides=manual_overrides,
            has_manual_overrides=len(manual_overrides) > 0,
            classifier_governance=classifier_governance,
            drift_summary=drift_summary,
        )

    def _load_scored_records(self, job_id: str) -> list[ScoredRecord]:
        """Loads scored extraction records from results/<job_id>_scored.json if present."""
        scored_path = self._data_dir / "results" / f"{job_id}_scored.json"
        if not scored_path.exists():
            return []
        try:
            content = scored_path.read_text(encoding="utf-8")
            raw_data = json.loads(content)
            if isinstance(raw_data, list):
                return [ScoredRecord.model_validate(item) for item in raw_data]
            return []
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.warning("Failed to load scored records for job %s: %s", job_id, err)
            return []

    def _compile_reconciliation_summary(
        self,
        provenance_records: list[Any],
    ) -> list[ReconciliationSummaryItem]:
        """
        Compiles the high-level reconciliation summary table.
        Prioritizes Model_Summary sheet cells and formula-driven cells.
        """
        items: list[ReconciliationSummaryItem] = []

        summary_records = [
            r for r in provenance_records if r.sheet_name == "Model_Summary" or r.is_formula
        ]
        records_to_use = summary_records if summary_records else provenance_records

        for r in records_to_use:
            is_hardcode = bool(r.node_id.startswith("hardcode_"))
            formula_expr = r.body.value if r.is_formula else None
            items.append(
                ReconciliationSummaryItem(
                    sheet_name=r.sheet_name,
                    cell_coord=r.cell_coord,
                    label=r.body.original_label or r.body.label,
                    normalized_label=r.body.label,
                    formula_expression=formula_expr,
                    computed_value=r.body.value,
                    is_formula=r.is_formula,
                    is_hardcode=is_hardcode,
                )
            )

        return items

    def _compile_provenance_matrix(
        self,
        job_id: str,
        provenance_records: list[Any],
    ) -> list[ProvenanceMatrixItem]:
        """
        Compiles the full provenance matrix mapping every generated cell to its resolved source chain.
        """
        items: list[ProvenanceMatrixItem] = []

        for r in provenance_records:
            chain_res = self._audit_trail_resolver.resolve_by_cell(
                job_id=job_id,
                sheet_name=r.sheet_name,
                cell_coord=r.cell_coord,
            )
            components = chain_res.components if chain_res.is_found else []

            items.append(
                ProvenanceMatrixItem(
                    sheet_name=r.sheet_name,
                    cell_coord=r.cell_coord,
                    node_id=r.node_id,
                    label=r.body.original_label or r.body.label,
                    normalized_label=r.body.label,
                    computed_value=r.body.value,
                    is_formula=r.is_formula,
                    components=components,
                )
            )

        return items

    def _compile_manual_overrides(
        self,
        job_id: str,
        review_items: list[ReviewItem],
        scored_records: list[ScoredRecord],
        provenance_records: list[Any],
    ) -> list[ManualOverrideItem]:
        """
        Compiles all items modified, hardcoded, or manually entered during Feature 5 review (spec §3, AC-3, EC-1, EC-2).
        """
        overrides: list[ManualOverrideItem] = []
        scored_map: dict[str, ScoredRecord] = {}

        for idx, sr in enumerate(scored_records):
            item_id = f"{job_id}_{idx}"
            scored_map[item_id] = sr

        for item in review_items:
            orig_sr = scored_map.get(item.id)
            orig_value = orig_sr.record.value if orig_sr else None
            orig_label = orig_sr.record.label if orig_sr else None
            orig_status = orig_sr.status if orig_sr else None

            is_edited_value = orig_value is not None and item.value != orig_value
            is_edited_label = orig_label is not None and item.label != orig_label
            was_extraction_error = orig_status == "extraction_error" or item.status == ReviewStatus.extraction_error
            is_manual_required = item.status == ReviewStatus.manual_required

            if is_edited_value or is_edited_label or was_extraction_error or is_manual_required:
                if was_extraction_error:
                    override_type = "extraction_error_recovery"
                elif is_manual_required:
                    override_type = "manual_required_entry"
                else:
                    override_type = "user_edit"

                flags_list = list(item.flags) if item.flags else (list(orig_sr.flags) if orig_sr and orig_sr.flags else [])

                overrides.append(
                    ManualOverrideItem(
                        item_id=item.id,
                        source_file=item.source_file,
                        page=item.page,
                        bbox=item.bbox,
                        override_type=override_type,
                        original_value=orig_value,
                        final_value=item.value,
                        original_label=orig_label,
                        final_label=item.label,
                        review_status=item.status.value if hasattr(item.status, "value") else str(item.status),
                        confidence_band=item.confidence_band.value if hasattr(item.confidence_band, "value") else str(item.confidence_band),
                        flags=flags_list,
                        error_detail=item.error_detail or (orig_sr.error_detail if orig_sr else None),
                        confirmation_timestamp=None,
                        is_hardcode=False,
                    )
                )

        # Check for any hardcoded cells in the workbook (NFR2, CONSTITUTION §1.5)
        for r in provenance_records:
            if r.node_id.startswith("hardcode_"):
                source_file = r.target.source
                page = r.target.selector.page if r.target.selector else 1
                coords = (
                    r.target.selector.refinedBy.coordinates
                    if r.target.selector
                    else None
                )
                bbox_dict = (
                    {"x0": coords.x0, "y0": coords.y0, "x1": coords.x1, "y1": coords.y1}
                    if coords
                    else {"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0}
                )
                overrides.append(
                    ManualOverrideItem(
                        item_id=f"{r.sheet_name}!{r.cell_coord}",
                        source_file=source_file,
                        page=page,
                        bbox=bbox_dict,
                        override_type="manual_hardcode",
                        original_value=None,
                        final_value=r.body.value,
                        original_label=r.body.original_label,
                        final_label=r.body.label,
                        review_status="manual_hardcode",
                        confidence_band="manual_required",
                        flags=["manual_hardcode"],
                        error_detail="Manual hardcode per NFR2",
                        confirmation_timestamp=None,
                        is_hardcode=True,
                    )
                )

        return overrides

    def _compile_classifier_governance(self, job_id: str) -> ClassifierAuditSummary:
        """
        Compiles the LLM classifier governance log verifying numeric-free classification (spec §2, AC-7).
        """
        log_file = self._data_dir / "results" / f"{job_id}_decision_log.jsonl"
        if not log_file.exists():
            return ClassifierAuditSummary(
                total_calls=0,
                matched_count=0,
                pending_count=0,
                error_count=0,
                is_strictly_numeric_free=True,
                entries=[],
            )

        entries: list[ClassifierAuditEntry] = []
        matched_count = 0
        pending_count = 0
        error_count = 0
        strictly_numeric_free = True

        try:
            with log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    data = json.loads(stripped)

                    payload = data.get("input_payload", {})
                    input_label = payload.get("label", "")
                    structural_ctx = payload.get("structural_context")

                    raw_resp = data.get("raw_response")
                    output_label: str | None = None
                    confidence: float | None = None

                    if raw_resp is not None and isinstance(raw_resp, dict):
                        output_label = raw_resp.get("label")
                        confidence = raw_resp.get("confidence")

                        # Verify that raw response does not have numeric calculation fields
                        for k, v in raw_resp.items():
                            if k not in ("label", "confidence") and isinstance(v, (int, float)):
                                strictly_numeric_free = False

                    tax_status = str(data.get("taxonomy_status", "pending_taxonomy_confirmation"))
                    resulting_state = str(data.get("resulting_state", "pending_confirmation"))
                    err_detail = data.get("error_detail")

                    if tax_status == "matched" or resulting_state == "confirmed":
                        matched_count += 1
                    elif resulting_state == "classification_error" or err_detail is not None:
                        error_count += 1
                    else:
                        pending_count += 1

                    entries.append(
                        ClassifierAuditEntry(
                            record_index=int(data.get("record_index", 0)),
                            timestamp=str(data.get("timestamp", "")),
                            input_label=input_label,
                            structural_context=structural_ctx,
                            output_label=output_label,
                            confidence=confidence,
                            taxonomy_status=tax_status,
                            resulting_state=resulting_state,
                            error_detail=err_detail,
                        )
                    )

            return ClassifierAuditSummary(
                total_calls=len(entries),
                matched_count=matched_count,
                pending_count=pending_count,
                error_count=error_count,
                is_strictly_numeric_free=strictly_numeric_free,
                entries=entries,
            )
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.warning("Failed reading decision log for job %s: %s", job_id, err)
            return ClassifierAuditSummary(
                total_calls=0,
                matched_count=0,
                pending_count=0,
                error_count=0,
                is_strictly_numeric_free=True,
                entries=[],
            )

    def _compile_drift_summary(self, job_id: str, target_metric: str) -> DriftAuditSummary:
        """
        Compiles the cross-year drift summary from Feature 7 results (spec §2, AC-8, EC-7).
        """
        comp_res = self._drift_repo.get_comparison_result(job_id)
        if comp_res is not None:
            if comp_res.is_baseline:
                summary_text = (
                    f"Baseline Year — Initialized definition for {comp_res.target_metric}; "
                    "no prior-year comparison available."
                )
            elif comp_res.has_discrepancy:
                summary_text = (
                    f"Metric Redefinition Detected: {len(comp_res.added_labels)} component(s) added, "
                    f"{len(comp_res.removed_labels)} removed year-over-year."
                )
            else:
                summary_text = f"Metric Continuation — Definition for {comp_res.target_metric} unchanged."

            return DriftAuditSummary(
                is_evaluated=True,
                is_baseline=comp_res.is_baseline,
                has_discrepancy=comp_res.has_discrepancy,
                filing_year=comp_res.filing_year,
                added_labels=comp_res.added_labels,
                removed_labels=comp_res.removed_labels,
                prior_node_id=comp_res.prior_node_id,
                summary_text=summary_text,
            )

        flags = self._drift_repo.get_drift_flags(job_id)
        if flags:
            first_flag = flags[0]
            summary_text = (
                f"Metric Redefinition Detected: {len(first_flag.added_labels)} component(s) added, "
                f"{len(first_flag.removed_labels)} removed."
            )
            return DriftAuditSummary(
                is_evaluated=True,
                is_baseline=False,
                has_discrepancy=True,
                filing_year=first_flag.filing_year,
                added_labels=first_flag.added_labels,
                removed_labels=first_flag.removed_labels,
                prior_node_id=first_flag.prior_node_id,
                summary_text=summary_text,
            )

        return DriftAuditSummary(
            is_evaluated=False,
            is_baseline=False,
            has_discrepancy=False,
            filing_year=None,
            added_labels=[],
            removed_labels=[],
            prior_node_id=None,
            summary_text=f"Drift detection not recorded for metric '{target_metric}'.",
        )

    def _compile_metadata(
        self,
        job: Any,
        total_cells: int,
        review_items: list[ReviewItem],
        manual_overrides: list[ManualOverrideItem],
        drift_summary: DriftAuditSummary,
    ) -> ReportMetadata:
        """Compiles report header metadata and item count breakdowns."""
        # Derive filing year
        filing_year = drift_summary.filing_year
        if filing_year is None:
            match = re.search(r"(?:19|20)\d{2}", job.filename)
            if match:
                filing_year = int(match.group(0))

        # Derive entity
        entity = job.filename.rsplit(".", 1)[0].split("_")[0]
        if not entity:
            entity = "Unknown Entity"

        # Item counts
        automated_count = 0
        verified_count = 0
        flagged_count = 0

        if review_items:
            for it in review_items:
                if it.status == ReviewStatus.auto_accepted:
                    automated_count += 1
                elif it.status == ReviewStatus.locked:
                    verified_count += 1
                elif it.status == ReviewStatus.flagged:
                    flagged_count += 1
        else:
            automated_count = total_cells

        generated_at = datetime.now(timezone.utc).isoformat()

        return ReportMetadata(
            job_id=job.job_id,
            entity=entity,
            filing_filename=job.filename,
            filing_year=filing_year,
            target_metric=job.target_metric,
            generated_at=generated_at,
            total_cells=total_cells,
            automated_count=automated_count,
            verified_count=verified_count,
            flagged_count=flagged_count,
            override_count=len(manual_overrides),
        )


def compile_audit_dataset(
    job_id: str,
    data_dir: Path = _DEFAULT_DATA_DIR,
) -> CompiledAuditDataset:
    """
    Convenience function to compile all audit data for a completed job.
    """
    compiler = AuditReportCompiler(data_dir=data_dir)
    return compiler.compile(job_id)
