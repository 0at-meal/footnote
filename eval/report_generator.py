"""
Evaluation Report Generator for Footnote Benchmark Corpus (Feature 9).

Produces:
1. Machine-readable JSON evaluation reports.
2. Structured GitHub-Flavored Markdown reports with mandatory CONSTITUTION §6.13 governance disclosures.
3. Clean ASCII terminal summaries for CLI and CI/CD logging.

Enforces:
- CONSTITUTION §6.13: Mandatory governance disclosures stating benchmark corpus size and manual review rates.
- AC-3: >= 90% Line-item accuracy target achievement check.
- AC-4: Three-layer architectural error isolation (extraction, classification, generation).
- AC-5 / EC-3: Explicit failed extraction threshold (> 15% non-auto-accept items) reporting.
- AC-7: Layout and structural failure pattern taxonomy breakdown.
"""

from __future__ import annotations

from pathlib import Path

from eval.models import (
    CorpusAccuracyMetrics,
    FailurePattern,
    ItemMatchStatus,
)


def generate_json_report(corpus_metrics: CorpusAccuracyMetrics, indent: int = 2) -> str:
    """
    Serializes CorpusAccuracyMetrics into a formatted, schema-valid JSON string.

    Args:
        corpus_metrics: Complete evaluated corpus metrics.
        indent: JSON indentation spacing (default: 2).

    Returns:
        JSON string representation.
    """
    return corpus_metrics.model_dump_json(indent=indent)


def generate_markdown_report(
    corpus_metrics: CorpusAccuracyMetrics, include_diff_details: bool = True
) -> str:
    """
    Generates a structured, rich Markdown evaluation report.

    Args:
        corpus_metrics: Evaluated corpus metrics.
        include_diff_details: If True, includes granular line-item diff tables per filing.

    Returns:
        Formatted GitHub-Flavored Markdown string.
    """
    lines: list[str] = []

    # Title & Header
    lines.append(f"# Evaluation Report: {corpus_metrics.corpus_name}")
    lines.append("")
    lines.append(
        f"**Target Metric:** Adjusted EBITDA | **Benchmark Corpus Size:** {corpus_metrics.benchmark_corpus_size} filings | "
        f"**Total Ground Truth Items:** {corpus_metrics.total_ground_truth_items}"
    )
    lines.append("")

    # CONSTITUTION §6.13 Mandatory Governance Disclosure Alert
    lines.append("> [!IMPORTANT]")
    lines.append("> **Governance & Transparency Disclosure (CONSTITUTION §6.13)**")
    lines.append(f"> {corpus_metrics.mandatory_governance_disclosure}")
    lines.append("")

    # Executive Summary / KPI Table
    accuracy_badge = (
        "✅ PASSED (>= 90%)"
        if corpus_metrics.target_accuracy_achieved
        else "❌ FAILED (< 90%)"
    )
    lines.append("## 1. Executive Summary")
    lines.append("")
    lines.append("| Metric | Value | Target / Status |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(
        f"| **Line-Item Extraction Accuracy** | **{corpus_metrics.corpus_line_item_accuracy_percentage:.2f}%** | {accuracy_badge} |"
    )
    lines.append(f"| **Macro Precision** | {corpus_metrics.macro_precision:.4f} | - |")
    lines.append(f"| **Macro Recall** | {corpus_metrics.macro_recall:.4f} | - |")
    lines.append(f"| **Macro F1-Score** | {corpus_metrics.macro_f1_score:.4f} | - |")
    lines.append(f"| **Micro Precision** | {corpus_metrics.micro_precision:.4f} | - |")
    lines.append(f"| **Micro Recall** | {corpus_metrics.micro_recall:.4f} | - |")
    lines.append(f"| **Micro F1-Score** | {corpus_metrics.micro_f1_score:.4f} | - |")
    lines.append(
        f"| **Total Filings Evaluated** | {corpus_metrics.total_filings} | {corpus_metrics.successful_filings} Succeeded, {corpus_metrics.failed_extraction_filings_count} Failed Extractions |"
    )
    lines.append(
        f"| **Manual Review / Correction Rate** | {corpus_metrics.manual_review_percentage:.2f}% | {corpus_metrics.total_manual_review_items} of {corpus_metrics.total_extracted_items} extracted items |"
    )
    lines.append("")

    # Architectural Three-Layer Error Isolation (AC-4)
    lines.append("## 2. Three-Layer Error Isolation (AC-4)")
    lines.append("")
    lines.append(
        "Isolates pipeline discrepancy counts across architectural boundaries without conflation:"
    )
    lines.append("")
    lines.append("| Pipeline Layer | Discrepancy Count | Layer Description |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(
        f"| **Extraction Layer** | {corpus_metrics.layer_errors.extraction_errors} | Missed items, value discrepancies, spurious items, and localization errors |"
    )
    lines.append(
        f"| **Classification Layer** | {corpus_metrics.layer_errors.classification_errors} | Taxonomy normalization mismatches and unrecognized labels |"
    )
    lines.append(
        f"| **Generation Layer** | {corpus_metrics.layer_errors.generation_errors} | Formula recalculation errors, zero generated cells, or missing provenance |"
    )
    lines.append("")

    # Failed Extraction Threshold Enforcement (AC-5, EC-3)
    lines.append("## 3. Failed Extraction Threshold Enforcement (AC-5, EC-3)")
    lines.append("")
    lines.append(
        "A filing is designated as a **Failed Extraction** if more than 15.0% of its extracted line items fall outside the auto-accept confidence band (score < 0.95)."
    )
    lines.append("")
    if corpus_metrics.failed_extraction_filings_count > 0:
        lines.append(
            f"⚠️ **{corpus_metrics.failed_extraction_filings_count} filing(s)** exceeded the 15.0% threshold:"
        )
        lines.append("")
        lines.append(
            "| Filing ID | Company | Non-Auto-Accepted Count | Non-Auto-Accepted % | Status |"
        )
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for fm in corpus_metrics.filing_metrics:
            if fm.failed_extraction:
                lines.append(
                    f"| `{fm.filing_id}` | {fm.company_name} | {fm.non_auto_accepted_count} | {fm.non_auto_accepted_percentage:.1f}% | ❌ Failed Extraction |"
                )
    else:
        lines.append(
            "✅ **Zero filings exceeded the 15.0% failed extraction threshold.** All benchmark filings achieved high auto-acceptance rates."
        )
    lines.append("")

    # Structural Failure Pattern Taxonomy Breakdown (AC-7)
    lines.append("## 4. Failure Pattern Classification (AC-7)")
    lines.append("")
    lines.append("| Failure Pattern | Count | Description / Root Cause |")
    lines.append("| :--- | :--- | :--- |")
    pattern_descriptions = {
        FailurePattern.sign_mismatch.value: "Numeric value has correct magnitude but inverted sign (e.g. accounting parentheses error)",
        FailurePattern.multi_column_bleed.value: "Text flow across adjacent table columns merged into a single field",
        FailurePattern.merged_cell_misalignment.value: "Header or data cell span caused coordinate localization offset",
        FailurePattern.footnote_severance.value: "Footnote reference disconnected from primary table line item",
        FailurePattern.unrecognized_label.value: "Classification could not match item to standardized taxonomy",
        FailurePattern.missing_item.value: "Ground-truth item omitted from pipeline extraction",
        FailurePattern.spurious_item.value: "Spurious line item extracted that does not exist in ground truth",
    }
    for pat, desc in pattern_descriptions.items():
        cnt = corpus_metrics.failure_pattern_counts.get(pat, 0)
        lines.append(f"| `{pat}` | {cnt} | {desc} |")
    lines.append("")

    # Per-Filing Performance Table
    lines.append("## 5. Per-Filing Performance Breakdown")
    lines.append("")
    lines.append(
        "| Filing ID | Company | GT Items | TP | FP | FN | Accuracy | Precision | Recall | F1 | NFR3 Runtime | Extraction Status |"
    )
    lines.append(
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    )
    for fm in corpus_metrics.filing_metrics:
        status_str = "❌ Failed" if fm.failed_extraction else "✅ Passed"
        runtime_str = f"{fm.runtimes.total_time_seconds:.1f}s" if fm.runtimes else "N/A"
        if not fm.nfr3_compliant:
            runtime_str += " ⚠️ (>300s)"

        lines.append(
            f"| `{fm.filing_id}` | {fm.company_name} | {fm.total_ground_truth_items} | {fm.true_positives} | "
            f"{fm.false_positives} | {fm.false_negatives} | {fm.line_item_accuracy_percentage:.1f}% | "
            f"{fm.precision:.2f} | {fm.recall:.2f} | {fm.f1_score:.2f} | {runtime_str} | {status_str} |"
        )
    lines.append("")

    # Granular Line-Item Diffs (Optional)
    if include_diff_details:
        lines.append("## 6. Granular Line-Item Diffs")
        lines.append("")
        for fm in corpus_metrics.filing_metrics:
            lines.append(f"### Filing: `{fm.filing_id}` ({fm.company_name})")
            lines.append("")
            if not fm.line_item_diffs:
                lines.append("_No line-item diff records available._")
                lines.append("")
                continue

            lines.append(
                "| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |"
            )
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for d in fm.line_item_diffs:
                gt_lbl = d.ground_truth_label or "-"
                gt_val = d.ground_truth_value or "-"
                ext_lbl = d.extracted_label or "-"
                ext_val = d.extracted_value or "-"
                iou_str = f"{d.iou:.2f}"
                opt_str = " _(opt)_" if d.is_optional else ""

                status_icon = "✅" if d.status == ItemMatchStatus.exact_match else "⚠️"
                lines.append(
                    f"| {d.page} | {gt_lbl}{opt_str} | {gt_val} | {ext_lbl} | {ext_val} | "
                    f"{iou_str} | {status_icon} `{d.status.value}` | `{d.failure_pattern.value}` |"
                )
            lines.append("")

    return "\n".join(lines)


def generate_terminal_summary(corpus_metrics: CorpusAccuracyMetrics) -> str:
    """
    Generates a concise ASCII summary suitable for terminal CLI output and CI logs.

    Args:
        corpus_metrics: Evaluated corpus metrics.

    Returns:
        Formatted terminal output string.
    """
    div = "=" * 78
    sub_div = "-" * 78

    lines: list[str] = [
        div,
        f" FOOTNOTE BENCHMARK EVALUATION REPORT: {corpus_metrics.corpus_name.upper()}",
        div,
        f" Benchmark Corpus Size:        {corpus_metrics.benchmark_corpus_size} filings ({corpus_metrics.total_ground_truth_items} total ground-truth items)",
        f" Line-Item Accuracy:          {corpus_metrics.corpus_line_item_accuracy_percentage:.2f}% (Target: >= 90.0%)",
        f" Target Accuracy Achieved:    {'YES [PASS]' if corpus_metrics.target_accuracy_achieved else 'NO [FAIL]'}",
        sub_div,
        f" Macro Precision:             {corpus_metrics.macro_precision:.4f}",
        f" Macro Recall:                {corpus_metrics.macro_recall:.4f}",
        f" Macro F1-Score:              {corpus_metrics.macro_f1_score:.4f}",
        f" Micro Precision:             {corpus_metrics.micro_precision:.4f}",
        f" Micro Recall:                {corpus_metrics.micro_recall:.4f}",
        f" Micro F1-Score:              {corpus_metrics.micro_f1_score:.4f}",
        sub_div,
        " THREE-LAYER ERROR ISOLATION (AC-4):",
        f"   - Extraction Errors:        {corpus_metrics.layer_errors.extraction_errors}",
        f"   - Classification Errors:    {corpus_metrics.layer_errors.classification_errors}",
        f"   - Generation Errors:        {corpus_metrics.layer_errors.generation_errors}",
        sub_div,
        " FAILED EXTRACTION THRESHOLD (>15% non-auto-accept items, AC-5):",
        f"   - Failed Filings:           {corpus_metrics.failed_extraction_filings_count} of {corpus_metrics.total_filings}",
        sub_div,
        " MANDATORY GOVERNANCE DISCLOSURE (CONSTITUTION §6.13):",
        f'   "{corpus_metrics.mandatory_governance_disclosure}"',
        div,
    ]

    return "\n".join(lines)


def save_reports(
    corpus_metrics: CorpusAccuracyMetrics,
    output_dir: Path | str,
    base_filename: str = "evaluation_report",
    include_diff_details: bool = True,
) -> tuple[Path, Path]:
    """
    Saves JSON and Markdown evaluation reports to a target directory.

    Args:
        corpus_metrics: Evaluated corpus metrics.
        output_dir: Path to output directory.
        base_filename: Base filename prefix (default: 'evaluation_report').
        include_diff_details: Whether to include granular diffs in Markdown.

    Returns:
        Tuple of (json_path, markdown_path).
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_file = out_path / f"{base_filename}.json"
    md_file = out_path / f"{base_filename}.md"

    json_content = generate_json_report(corpus_metrics)
    md_content = generate_markdown_report(
        corpus_metrics, include_diff_details=include_diff_details
    )

    json_file.write_text(json_content, encoding="utf-8")
    md_file.write_text(md_content, encoding="utf-8")

    return json_file, md_file
