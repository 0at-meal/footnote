"""
Source-chain resolution engine for Audit Trail Lookup (Feature 6 Step 1).

Enforces:
- CONSTITUTION §1.1, §1.3, §1.9, §2.3, §3.4, §6.6
- spec.md §1 (Source-chain resolution), AC-1, AC-2, AC-5, AC-6, AC-7, AC-10
- EC-1 (Missing record gap tracking), EC-2, EC-7, EC-8, EC-9
- Strictly read-only: reads provenance and review state, modifies nothing.
- Strictly isolated: does not import from classification, extraction, or formula_engine.
"""

import logging
import re
from enum import Enum
from pathlib import Path

from app.audit_trail.models import SourceChainResponse, SourceComponent
from app.excel_export.models import W3CAnnotationRecord
from app.excel_export.repository import ModelRepository
from app.review.models import ReviewItem
from app.review.repository import ReviewRepository

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


class AuditTrailResolver:
    """
    Resolves a cell reference or provenance record ID to its complete source chain.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._model_repo = ModelRepository(data_dir=data_dir)
        self._review_repo = ReviewRepository(data_dir=data_dir)

    def resolve_by_cell(
        self,
        job_id: str,
        sheet_name: str,
        cell_coord: str,
    ) -> SourceChainResponse:
        """
        Resolves a cell selection in the generated workbook to its full source chain (AC-1, AC-2).
        """
        provenance_records = self._model_repo.get_provenance_records(job_id)
        if provenance_records is None:
            return SourceChainResponse(
                job_id=job_id,
                sheet_name=sheet_name,
                cell_coord=cell_coord,
                is_found=False,
                error_detail=f"No provenance records found for job '{job_id}'.",
            )

        target_coord = cell_coord.strip().upper()
        target_sheet = sheet_name.strip()

        target_record: W3CAnnotationRecord | None = None
        for record in provenance_records:
            if (
                record.sheet_name == target_sheet
                and record.cell_coord.strip().upper() == target_coord
            ):
                target_record = record
                break

        if target_record is None:
            return SourceChainResponse(
                job_id=job_id,
                sheet_name=sheet_name,
                cell_coord=cell_coord,
                is_found=False,
                error_detail=f"No provenance record found for cell '{sheet_name}!{cell_coord}' (EC-2).",
            )

        return self._resolve_record_chain(job_id, target_record, provenance_records)

    def resolve_by_provenance_id(
        self,
        job_id: str,
        provenance_id: str,
    ) -> SourceChainResponse:
        """
        Resolves a provenance record ID directly to its full source chain (AC-7, EC-7).
        """
        provenance_records = self._model_repo.get_provenance_records(job_id)
        if provenance_records is None:
            return SourceChainResponse(
                job_id=job_id,
                provenance_id=provenance_id,
                is_found=False,
                error_detail=f"No provenance records found for job '{job_id}'.",
            )

        target_id = provenance_id.strip()
        target_record: W3CAnnotationRecord | None = None
        for record in provenance_records:
            if record.id == target_id:
                target_record = record
                break

        if target_record is None:
            return SourceChainResponse(
                job_id=job_id,
                provenance_id=provenance_id,
                is_found=False,
                error_detail=f"No provenance record found with ID '{provenance_id}' (EC-7).",
            )

        return self._resolve_record_chain(job_id, target_record, provenance_records)

    def _resolve_record_chain(
        self,
        job_id: str,
        target_record: W3CAnnotationRecord,
        all_records: list[W3CAnnotationRecord],
    ) -> SourceChainResponse:
        """
        Internal resolution worker to expand target record to all contributing leaf components.
        """
        # Map leaf node_id -> W3CAnnotationRecord
        # Prefer Source_Inputs records as canonical leaf sources
        leaf_records_by_node_id: dict[str, W3CAnnotationRecord] = {}
        for record in all_records:
            if record.node_id.startswith("leaf_") and (
                record.node_id not in leaf_records_by_node_id
                or record.sheet_name == "Source_Inputs"
            ):
                leaf_records_by_node_id[record.node_id] = record

        # Determine contributing leaf node IDs in deterministic order
        contributing_leaf_ids: list[str] = []
        node_id = target_record.node_id

        if node_id.startswith("leaf_"):
            # Single leaf record
            contributing_leaf_ids.append(node_id)
        elif node_id.startswith("agg_"):
            # Aggregate node: extract contributing leaf IDs from formula expression or matching group
            formula_expr = target_record.body.value
            referenced_leaf_ids = re.findall(r"leaf_\w+", formula_expr)
            if referenced_leaf_ids:
                contributing_leaf_ids.extend(referenced_leaf_ids)
            else:
                # Fallback: match by slug group in leaf_records_by_node_id
                agg_slug = node_id.replace("agg_", "")
                for l_id in leaf_records_by_node_id:
                    if l_id.endswith(f"_{agg_slug}"):
                        contributing_leaf_ids.append(l_id)
        elif node_id.startswith("root_") or node_id == "root":
            # Root target metric: all leaf nodes in Source_Inputs order
            for record in all_records:
                if (
                    record.sheet_name == "Source_Inputs"
                    and record.node_id.startswith("leaf_")
                    and record.node_id not in contributing_leaf_ids
                ):
                    contributing_leaf_ids.append(record.node_id)
        else:
            # Check if it has a direct selector or check formula
            if target_record.target.selector is not None:
                contributing_leaf_ids.append(node_id)
            else:
                referenced_leaf_ids = re.findall(r"leaf_\w+", target_record.body.value)
                contributing_leaf_ids.extend(referenced_leaf_ids)

        # Retrieve live review items for status enrichment (AC-4)
        review_items = self._review_repo.get_review_items(job_id)
        review_items_by_id: dict[str, ReviewItem] = {}
        if review_items:
            for item in review_items:
                review_items_by_id[item.id] = item

        components: list[SourceComponent] = []

        for leaf_id in contributing_leaf_ids:
            leaf_record = leaf_records_by_node_id.get(leaf_id)

            # Extract record index from leaf_id: leaf_{record_index}_{slug}
            m = re.match(r"^leaf_(\d+)_", leaf_id)
            record_index = int(m.group(1)) if m else None
            review_item_id = (
                f"{job_id}_{record_index}" if record_index is not None else None
            )

            review_item: ReviewItem | None = None
            if review_item_id and review_item_id in review_items_by_id:
                review_item = review_items_by_id[review_item_id]

            if leaf_record is None:
                # Gap entry for missing provenance record (EC-1)
                components.append(
                    SourceComponent(
                        component_id=leaf_id,
                        source_file="unknown",
                        page=1,
                        bbox={"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0},
                        value="[missing]",
                        label="[missing]",
                        normalized_label=None,
                        review_status="source_record_missing",
                        is_missing=True,
                        provenance_id=f"urn:footnote:provenance:{job_id}:{leaf_id}",
                    )
                )
                continue

            # Populate component details from leaf provenance record
            source_file = leaf_record.target.source
            if leaf_record.target.selector is not None:
                page = leaf_record.target.selector.page
                coords = leaf_record.target.selector.refinedBy.coordinates
                bbox_dict = {
                    "x0": coords.x0,
                    "y0": coords.y0,
                    "x1": coords.x1,
                    "y1": coords.y1,
                }
            else:
                page = 1
                bbox_dict = {"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0}

            value = leaf_record.body.value
            label = leaf_record.body.original_label or leaf_record.body.label
            normalized_label = leaf_record.body.label

            # Live review status enrichment (AC-4)
            if review_item is not None:
                status_val = (
                    review_item.status.value
                    if isinstance(review_item.status, Enum)
                    else str(review_item.status)
                )
                review_status = status_val
                # Use updated/corrected value or label if modified in review UI
                value = review_item.value
                label = review_item.label
                if review_item.normalized_label:
                    normalized_label = review_item.normalized_label
                is_missing = False
            elif review_items is not None and len(review_items) > 0:
                # Review records exist for this job, but this specific record is missing (EC-1)
                review_status = "source_record_missing"
                is_missing = True
            else:
                # Review state not initialized yet
                review_status = "unreviewed"
                is_missing = False

            components.append(
                SourceComponent(
                    component_id=review_item_id or leaf_id,
                    source_file=source_file,
                    page=page,
                    bbox=bbox_dict,
                    value=value,
                    label=label,
                    normalized_label=normalized_label,
                    review_status=review_status,
                    is_missing=is_missing,
                    provenance_id=leaf_record.id,
                )
            )

        formula_expression = (
            target_record.body.value if target_record.is_formula else None
        )

        return SourceChainResponse(
            job_id=job_id,
            sheet_name=target_record.sheet_name,
            cell_coord=target_record.cell_coord,
            provenance_id=target_record.id,
            node_id=target_record.node_id,
            is_formula=target_record.is_formula,
            formula_expression=formula_expression,
            is_found=True,
            components=components,
            error_detail=None,
        )
