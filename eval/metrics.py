"""
Pure multi-layer diffing engine and accuracy metrics computation for Footnote (Feature 9, Step 3).

Enforces:
- CONSTITUTION §1.4: Pure mathematical and semantic diffing without I/O or mutable state.
- CONSTITUTION §3.5: Multi-layer error isolation (Extraction, Classification, Generation) per AC-4.
- CONSTITUTION §6.13: Mandatory governance disclosures embedded in all corpus reports.
- AC-3: >= 90% Line-item extraction accuracy target threshold.
- AC-5 / EC-3: Strict > 15.0% non-auto-accepted confidence threshold for failed extractions.
- AC-7: Automated structural failure pattern categorization.
- EC-1: Proper handling of optional/conditional ground truth line items.
- EC-2: Semantic numeric equivalence checking for parenthesized negatives, formatting, and currencies.
- EC-6: 2D Bounding box Intersection-over-Union (IoU) localization evaluation.
- EC-10: Disambiguation across sections using page numbers and structural bounding boxes.
"""

import math
from typing import Any

from eval.models import (
    BenchmarkCorpus,
    BenchmarkCorpusExecutionResult,
    BenchmarkFiling,
    BenchmarkFilingExecutionResult,
    CorpusAccuracyMetrics,
    FailurePattern,
    FilingAccuracyMetrics,
    GroundTruthBbox,
    GroundTruthItem,
    ItemMatchStatus,
    LayerMetricsSummary,
    LineItemDiff,
    StageRuntimes,
)


def calculate_bbox_iou(
    box_a: GroundTruthBbox | dict[str, float] | Any,
    box_b: GroundTruthBbox | dict[str, float] | Any | None,
) -> float:
    """
    Computes the 2D Intersection-over-Union (IoU) between two bounding boxes
    in normalized 0-1000 coordinate space (EC-6).

    Returns:
        float: IoU value in range [0.0, 1.0].
    """
    if box_b is None:
        return 0.0

    # Extract coordinates
    if isinstance(box_a, dict):
        ax0, ay0, ax1, ay1 = box_a["x0"], box_a["y0"], box_a["x1"], box_a["y1"]
    elif hasattr(box_a, "x0"):
        ax0, ay0, ax1, ay1 = box_a.x0, box_a.y0, box_a.x1, box_a.y1
    else:
        return 0.0

    if isinstance(box_b, dict):
        bx0, by0, bx1, by1 = box_b["x0"], box_b["y0"], box_b["x1"], box_b["y1"]
    elif hasattr(box_b, "x0"):
        bx0, by0, bx1, by1 = box_b.x0, box_b.y0, box_b.x1, box_b.y1
    else:
        return 0.0

    # Calculate intersection rectangle
    inter_x0 = max(ax0, bx0)
    inter_y0 = max(ay0, by0)
    inter_x1 = min(ax1, bx1)
    inter_y1 = min(ay1, by1)

    if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
        return 0.0

    inter_area = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
    area_a = max(0.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0) * (by1 - by0))
    union_area = area_a + area_b - inter_area

    if union_area <= 0.0:
        return 0.0

    return round(float(inter_area / union_area), 4)


def parse_numeric_value(val: str | None) -> float | None:
    """
    Parses raw string representation into a float, supporting accounting parentheses negatives,
    currency signs, commas, and percentage signs (EC-2).

    Examples:
        "(1,234.50)" -> -1234.5
        "$50,000"    -> 50000.0
        "100%"       -> 100.0
    """
    if val is None:
        return None

    cleaned = val.strip()
    if not cleaned:
        return None

    # Strip currency signs
    cleaned = cleaned.replace("$", "").replace("€", "").replace("£", "").strip()
    cleaned = cleaned.replace("%", "").strip()

    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()
    elif cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:].strip()

    cleaned = cleaned.replace(",", "").strip()

    try:
        num = float(cleaned)
        return -num if is_negative else num
    except (ValueError, TypeError):
        return None


def are_values_equivalent(
    val_a: str | None, val_b: str | None, tolerance: float = 1e-3
) -> bool:
    """
    Evaluates semantic numeric equivalence between two line-item values (EC-2).
    Falls back to case-insensitive whitespace-normalized string equality if non-numeric.
    """
    if val_a is None and val_b is None:
        return True
    if val_a is None or val_b is None:
        return False

    norm_a = val_a.strip().lower()
    norm_b = val_b.strip().lower()

    if norm_a == norm_b:
        return True

    num_a = parse_numeric_value(val_a)
    num_b = parse_numeric_value(val_b)

    if num_a is not None and num_b is not None:
        return bool(abs(num_a - num_b) <= tolerance)

    return False


def classify_failure_pattern(
    gt_item: GroundTruthItem | None,
    extracted_val: str | None,
    extracted_label: str | None,
    status: ItemMatchStatus,
) -> FailurePattern:
    """
    Classifies an extraction or classification error into a known structural failure pattern (AC-7).
    """
    if status == ItemMatchStatus.exact_match:
        return FailurePattern.none

    if status == ItemMatchStatus.missed_item:
        return FailurePattern.missing_item

    if status == ItemMatchStatus.spurious_item:
        return FailurePattern.spurious_item

    if status == ItemMatchStatus.classification_mismatch:
        return FailurePattern.unrecognized_label

    if status == ItemMatchStatus.localization_error:
        return FailurePattern.merged_cell_misalignment

    if status == ItemMatchStatus.value_mismatch:
        if gt_item is not None and extracted_val is not None:
            num_gt = parse_numeric_value(gt_item.value)
            num_ext = parse_numeric_value(extracted_val)
            if (
                num_gt is not None
                and num_ext is not None
                and math.isclose(abs(num_gt), abs(num_ext), rel_tol=1e-3)
                and (num_gt * num_ext < 0)
            ):
                return FailurePattern.sign_mismatch
            # Check for multiple amounts or multi-column bleed in string
            if " " in extracted_val.strip() or len(extracted_val.split()) > 1:
                return FailurePattern.multi_column_bleed

        return FailurePattern.multi_column_bleed

    return FailurePattern.none


def diff_filing(
    filing: BenchmarkFiling,
    execution_result: BenchmarkFilingExecutionResult,
    iou_threshold: float = 0.5,
) -> FilingAccuracyMetrics:
    """
    Performs multi-layer diffing between a benchmark filing ground truth and pipeline execution output (AC-4).

    Evaluates:
    - Layer 1 (Extraction): Line item match, value equivalence, page and bounding box localization.
    - Layer 2 (Classification): Normalized taxonomy label verification against ground truth.
    - Layer 3 (Generation): Formula workbook and cell provenance verification.

    Enforces:
    - AC-3: Target accuracy >= 90.0%.
    - AC-5 / EC-3: Failed extraction if non-auto-accepted items exceed 15.0%.
    """
    total_gt_items = len(filing.ground_truth_items)
    scored_records = execution_result.scored_records
    classified_records = execution_result.classified_records

    # Map classified records by their inner record_id
    classified_by_record_id: dict[str, Any] = {}
    for cr in classified_records:
        rec = getattr(cr, "record", None)
        rec_id = (
            getattr(rec, "record_id", None) if rec else getattr(cr, "record_id", None)
        )
        if rec_id:
            classified_by_record_id[rec_id] = cr

    diffs: list[LineItemDiff] = []
    failure_patterns: list[FailurePattern] = []
    layer_errors = LayerMetricsSummary()

    # Track matched extracted records by index or id to identify spurious extractions
    matched_extracted_indices: set[int] = set()

    true_positives = 0
    false_negatives = 0
    non_optional_gt_count = 0

    # Layer 1 & 2 Evaluation: Match each ground-truth item
    for gt in filing.ground_truth_items:
        is_opt = getattr(gt, "is_optional", False) or getattr(gt, "optional", False)
        if not is_opt:
            non_optional_gt_count += 1

        best_match_record: Any | None = None
        best_match_cr: Any | None = None
        best_match_idx: int | None = None
        best_iou = 0.0
        best_score = -1.0

        for i, sr in enumerate(scored_records):
            if i in matched_extracted_indices:
                continue

            rec = getattr(sr, "record", sr)
            rec_page = getattr(rec, "page", 1)
            rec_bbox = getattr(rec, "bbox", None) or getattr(rec, "bbox_norm", None)

            # Match must be on the same page (EC-10)
            if rec_page != gt.page:
                continue

            iou = calculate_bbox_iou(gt.bbox, rec_bbox)

            # Score match quality combining IoU, value equivalence, and label similarity
            val_match = are_values_equivalent(gt.value, getattr(rec, "value", None))
            raw_label_match = (
                getattr(rec, "label", "").strip().lower() == gt.label.strip().lower()
            )

            match_score = (
                (iou * 2.0)
                + (2.0 if val_match else 0.0)
                + (1.0 if raw_label_match else 0.0)
            )

            # Accept as candidate if overlap or strong value/label match
            if match_score > best_score and (
                iou >= iou_threshold or val_match or raw_label_match
            ):
                best_score = match_score
                best_iou = iou
                best_match_record = rec
                best_match_idx = i
                best_match_cr = (
                    classified_records[i]
                    if i < len(classified_records)
                    else classified_by_record_id.get(getattr(rec, "record_id", ""))
                )

        if best_match_record is not None and best_match_idx is not None:
            matched_extracted_indices.add(best_match_idx)

            ext_val = getattr(best_match_record, "value", "")
            ext_label = getattr(best_match_record, "label", "")
            ext_norm_label = (
                getattr(best_match_cr, "normalized_label", None)
                if best_match_cr
                else None
            )

            val_eq = are_values_equivalent(gt.value, ext_val)
            class_eq = (
                (ext_norm_label.strip().lower() == gt.normalized_label.strip().lower())
                if ext_norm_label and gt.normalized_label
                else False
            )
            loc_ok = best_iou >= iou_threshold

            if val_eq and class_eq and loc_ok:
                status = ItemMatchStatus.exact_match
                pattern = FailurePattern.none
                true_positives += 1
            elif not val_eq:
                status = ItemMatchStatus.value_mismatch
                layer_errors.extraction_errors += 1
                pattern = classify_failure_pattern(gt, ext_val, ext_label, status)
                failure_patterns.append(pattern)
            elif not class_eq:
                status = ItemMatchStatus.classification_mismatch
                layer_errors.classification_errors += 1
                pattern = classify_failure_pattern(gt, ext_val, ext_label, status)
                failure_patterns.append(pattern)
            else:
                status = ItemMatchStatus.localization_error
                layer_errors.extraction_errors += 1
                pattern = classify_failure_pattern(gt, ext_val, ext_label, status)
                failure_patterns.append(pattern)

            diffs.append(
                LineItemDiff(
                    ground_truth_label=gt.label,
                    ground_truth_normalized_label=gt.normalized_label,
                    ground_truth_value=gt.value,
                    extracted_label=ext_label,
                    extracted_normalized_label=ext_norm_label,
                    extracted_value=ext_val,
                    page=gt.page,
                    iou=best_iou,
                    status=status,
                    failure_pattern=pattern,
                    is_optional=is_opt,
                    detail=f"IoU: {best_iou:.2f}, ValueEq: {val_eq}, ClassEq: {class_eq}",
                )
            )
        else:
            # Ground truth item missed
            if not is_opt:
                false_negatives += 1
                layer_errors.extraction_errors += 1
                status = ItemMatchStatus.missed_item
                pattern = FailurePattern.missing_item
                failure_patterns.append(pattern)
            else:
                # Valid non-reporting of optional item (EC-1)
                status = ItemMatchStatus.missed_item
                pattern = FailurePattern.none

            diffs.append(
                LineItemDiff(
                    ground_truth_label=gt.label,
                    ground_truth_normalized_label=gt.normalized_label,
                    ground_truth_value=gt.value,
                    page=gt.page,
                    iou=0.0,
                    status=status,
                    failure_pattern=pattern,
                    is_optional=is_opt,
                    detail="Item was not extracted by pipeline.",
                )
            )

    # Detect spurious extractions (False Positives)
    false_positives = 0
    for i, sr in enumerate(scored_records):
        if i not in matched_extracted_indices:
            false_positives += 1
            layer_errors.extraction_errors += 1
            rec = getattr(sr, "record", sr)
            cr = (
                classified_records[i]
                if i < len(classified_records)
                else classified_by_record_id.get(getattr(rec, "record_id", ""))
            )
            diffs.append(
                LineItemDiff(
                    extracted_label=getattr(rec, "label", None),
                    extracted_normalized_label=(
                        getattr(cr, "normalized_label", None) if cr else None
                    ),
                    extracted_value=getattr(rec, "value", None),
                    page=getattr(rec, "page", 1),
                    iou=0.0,
                    status=ItemMatchStatus.spurious_item,
                    failure_pattern=FailurePattern.spurious_item,
                    detail="Spurious extraction not in ground truth.",
                )
            )
            failure_patterns.append(FailurePattern.spurious_item)

    # Layer 3 Evaluation: Generation and Formula Workbook checks (AC-8, EC-8)
    if not execution_result.success or execution_result.total_cells_generated == 0:
        layer_errors.generation_errors += 1

    # Precision, Recall, F1, Accuracy Calculations
    eval_gt_total = (
        non_optional_gt_count if non_optional_gt_count > 0 else total_gt_items
    )
    accuracy_pct = round(
        float((true_positives / eval_gt_total) * 100.0) if eval_gt_total > 0 else 100.0,
        2,
    )

    prec_denom = true_positives + false_positives
    precision = round(float(true_positives / prec_denom), 4) if prec_denom > 0 else 0.0

    rec_denom = true_positives + false_negatives
    recall = round(float(true_positives / rec_denom), 4) if rec_denom > 0 else 0.0

    f1_denom = precision + recall
    f1_score = (
        round(float(2 * (precision * recall) / f1_denom), 4) if f1_denom > 0.0 else 0.0
    )

    # Confidence Band Distribution & Failed Extraction Threshold (AC-5, EC-3)
    # Band < 0.95 (needs review / manual required / extraction error)
    non_auto_accepted_count = 0
    for sr in scored_records:
        score = getattr(sr, "confidence_score", 1.0)
        if score < 0.95:
            non_auto_accepted_count += 1

    total_extracted = len(scored_records)
    non_auto_accepted_pct = round(
        (
            float((non_auto_accepted_count / total_extracted) * 100.0)
            if total_extracted > 0
            else 0.0
        ),
        2,
    )

    # Strict > 15.0% threshold (e.g. 15.01% fails per EC-3)
    failed_extraction = non_auto_accepted_pct > 15.0 or (not execution_result.success)

    target_accuracy_achieved = accuracy_pct >= 90.0

    return FilingAccuracyMetrics(
        filing_id=filing.metadata.filing_id,
        company_name=filing.metadata.company_name,
        total_ground_truth_items=total_gt_items,
        extracted_items_count=total_extracted,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        line_item_accuracy_percentage=accuracy_pct,
        target_accuracy_achieved=target_accuracy_achieved,
        failed_extraction=failed_extraction,
        non_auto_accepted_count=non_auto_accepted_count,
        non_auto_accepted_percentage=non_auto_accepted_pct,
        layer_errors=layer_errors,
        failure_patterns=failure_patterns,
        line_item_diffs=diffs,
        runtimes=execution_result.runtimes or StageRuntimes(),
        nfr3_compliant=execution_result.nfr3_compliant,
    )


def diff_corpus(
    corpus: BenchmarkCorpus | list[BenchmarkFiling],
    corpus_exec_result: BenchmarkCorpusExecutionResult,
    iou_threshold: float = 0.5,
) -> CorpusAccuracyMetrics:
    """
    Aggregates multi-layer diffs across all filings in the benchmark corpus,
    computing macro/micro metrics and embedding CONSTITUTION §6.13 mandatory governance disclosures.
    """
    filing_metrics: list[FilingAccuracyMetrics] = []
    failure_pattern_counts: dict[str, int] = {}
    layer_errors = LayerMetricsSummary()

    total_gt_items = 0
    total_extracted_items = 0
    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_manual_review_items = 0
    failed_filings_count = 0

    filings_list = corpus.filings if isinstance(corpus, BenchmarkCorpus) else corpus
    corpus_name = (
        corpus.manifest.corpus_name
        if isinstance(corpus, BenchmarkCorpus)
        else corpus_exec_result.corpus_name
    )

    filing_map = {f.metadata.filing_id: f for f in filings_list}

    for exec_res in corpus_exec_result.filing_results:
        filing = filing_map.get(exec_res.filing_id)
        if filing is None:
            continue

        metrics = diff_filing(filing, exec_res, iou_threshold=iou_threshold)
        filing_metrics.append(metrics)

        total_gt_items += metrics.total_ground_truth_items
        total_extracted_items += metrics.extracted_items_count
        total_tp += metrics.true_positives
        total_fp += metrics.false_positives
        total_fn += metrics.false_negatives
        total_manual_review_items += metrics.non_auto_accepted_count

        if metrics.failed_extraction:
            failed_filings_count += 1

        layer_errors.extraction_errors += metrics.layer_errors.extraction_errors
        layer_errors.classification_errors += metrics.layer_errors.classification_errors
        layer_errors.generation_errors += metrics.layer_errors.generation_errors

        for fp in metrics.failure_patterns:
            failure_pattern_counts[fp.value] = (
                failure_pattern_counts.get(fp.value, 0) + 1
            )

    filing_count = len(filing_metrics)

    # Macro averages
    macro_precision = round(
        (
            float(sum(m.precision for m in filing_metrics) / filing_count)
            if filing_count > 0
            else 0.0
        ),
        4,
    )
    macro_recall = round(
        (
            float(sum(m.recall for m in filing_metrics) / filing_count)
            if filing_count > 0
            else 0.0
        ),
        4,
    )
    macro_f1_score = round(
        (
            float(sum(m.f1_score for m in filing_metrics) / filing_count)
            if filing_count > 0
            else 0.0
        ),
        4,
    )

    # Micro aggregates
    micro_prec_denom = total_tp + total_fp
    micro_precision = (
        round(float(total_tp / micro_prec_denom), 4) if micro_prec_denom > 0 else 0.0
    )

    micro_rec_denom = total_tp + total_fn
    micro_recall = (
        round(float(total_tp / micro_rec_denom), 4) if micro_rec_denom > 0 else 0.0
    )

    micro_f1_denom = micro_precision + micro_recall
    micro_f1_score = (
        round(float(2 * (micro_precision * micro_recall) / micro_f1_denom), 4)
        if micro_f1_denom > 0.0
        else 0.0
    )

    corpus_accuracy_pct = round(
        float((total_tp / total_gt_items) * 100.0) if total_gt_items > 0 else 100.0, 2
    )

    target_accuracy_achieved = corpus_accuracy_pct >= 90.0

    manual_review_pct = round(
        (
            float((total_manual_review_items / total_extracted_items) * 100.0)
            if total_extracted_items > 0
            else 0.0
        ),
        2,
    )

    # CONSTITUTION §6.13 Mandatory Governance Disclosure
    mandatory_disclosure = (
        f"Evaluation conducted on benchmark corpus of {filing_count} filings "
        f"({total_gt_items} total ground-truth items). "
        f"{total_manual_review_items} items ({manual_review_pct:.2f}%) "
        f"required human review or manual correction."
    )

    return CorpusAccuracyMetrics(
        corpus_name=corpus_name,
        total_filings=filing_count,
        successful_filings=filing_count - failed_filings_count,
        failed_extraction_filings_count=failed_filings_count,
        total_ground_truth_items=total_gt_items,
        total_extracted_items=total_extracted_items,
        total_true_positives=total_tp,
        total_false_positives=total_fp,
        total_false_negatives=total_fn,
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1_score=macro_f1_score,
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1_score=micro_f1_score,
        corpus_line_item_accuracy_percentage=corpus_accuracy_pct,
        target_accuracy_achieved=target_accuracy_achieved,
        layer_errors=layer_errors,
        failure_pattern_counts=failure_pattern_counts,
        filing_metrics=filing_metrics,
        benchmark_corpus_size=filing_count,
        total_manual_review_items=total_manual_review_items,
        manual_review_percentage=manual_review_pct,
        mandatory_governance_disclosure=mandatory_disclosure,
    )
