# Footnote Evaluation Harness & Labeled Benchmark Corpus (FN-010 / FN-011)

The `eval/` package implements benchmarking, ground-truth reconciliation corpora, and accuracy regression gates for Footnote's extraction, confidence scoring, classification, and financial model compilation pipeline.

---

## 1. Corpus Architecture

The benchmark corpus lives in `eval/corpus/labels/`, containing ground-truth reconciliation labels keyed by SEC EDGAR Accession Number.

> [!IMPORTANT]
> **No filings in git**: Source PDFs and HTML filings are NEVER committed to version control. Filings are downloaded on-demand to the gitignored directory `eval/.cache/` via `python -m eval.fetch_filings`.

### Dataset Distribution
- **Total filings**: 40 curated public company filings
- **Dev split**: 30 filings (active model tuning and regression testing)
- **Locked test split**: 10 filings (final blind evaluation)
- **Double-labeled sample**: 8 filings (~20% of corpus) evaluated for inter-annotator agreement (kappa/percentage agreement >= 90%)
- **Paired releases**: 6 pairs (12 filings) containing both the 8-K EX-99.1 earnings release and the subsequent 10-Q/10-K for the identical reporting period (e.g. MSFT, WMT, UNH, XOM, T, GE).

### Sector Coverage
1. **Software**: MSFT, CRM, ADBE, NOW, SNOW, DDOG
2. **Retail**: WMT, TGT, COST, AMZN, HD, LOW
3. **Healthcare Services**: UNH, CVS, CI, HUM, HCA, CNC
4. **Energy**: XOM, CVX, COP, SLB, EOG, MPC
5. **Telecom**: T, VZ, TMUS, CHTR, DIS
6. **Industrials**: GE, CAT, DE, HON, MMM

### Adversarial Layout Cases Included
- `tables_spanning_pages`: Multi-page reconciliations with repeating headers
- `parentheses_negatives`: Deductions and negative figures formatted as `(1,234)`
- `restated_periods`: Prior-year adjustments and restatements
- `footnote_markers`: Disclosures with superscript markers (e.g., `(1)`, `*`, `†`)
- `scanned_exhibits`: Unformatted press release exhibits with whitespace anomalies
- `adjusted_net_income`: Non-EBITDA alternative performance measures

---

## 2. Label Schema

Each filing in `eval/corpus/labels/{accession}.json` conforms to `BenchmarkAccessionFiling`:

```json
{
  "accession_number": "0001018724-23-000014",
  "cik": "0001018724",
  "ticker": "MSFT",
  "company_name": "Microsoft Corporation",
  "sector": "software",
  "form": "10-K",
  "period": "FY2023",
  "fiscal_year": 2023,
  "fiscal_quarter": null,
  "filing_date": "2023-07-27",
  "split": "dev",
  "adversarial_cases": ["footnote_markers"],
  "reported_metric_name": "Adjusted EBITDA",
  "reported_total": 102384.0,
  "double_labeled": true,
  "inter_annotator_agreement": 1.0,
  "reconciliation_lines": [
    {
      "label": "GAAP Net Income",
      "value": "72,361",
      "numeric_value": 72361.0,
      "period": "FY2023",
      "scale": 1000000,
      "sign": 1,
      "locator": {
        "type": "html",
        "accession": "0001018724-23-000014",
        "document": "msft_2023.htm",
        "element_path": "table//tr"
      },
      "standard_category": "net_income",
      "is_gaap_seeded": true,
      "is_optional": false,
      "section": "Item 8. Note 19",
      "double_labeled": true,
      "second_annotator_agrees": true
    }
  ]
}
```

### Labeling Rules
1. **Raw values**: Store raw strings with verbatim formatting (e.g., `"72,361"` or `"(1,025)"`).
2. **Numeric values**: Parse signed float numbers (`72361.0`, `-1025.0`).
3. **Scale**: Expressed as multiplier integer: `1` (units), `1000` (thousands), `1000000` (millions).
4. **Sign**: `+1` indicates an add-back or positive addition to the base; `-1` indicates a deduction.
5. **GAAP lines**: Auto-seeded from XBRL fact disclosures (`net_income`, `taxes`, `interest`, `depreciation_amortization`) and marked `is_gaap_seeded: true`.
6. **Standard categories**: Constrained to taxonomy enums: `net_income`, `operating_income`, `interest`, `taxes`, `depreciation_amortization`, `SBC`, `restructuring`, `impairment`, `M&A/integration`, `litigation`, `FX`, `other`.

---

## 3. Harness Scripts & Usage

### 1. Download Filings on Demand
```bash
python -m eval.fetch_filings --dev-only
# Or fetch a specific accession:
python -m eval.fetch_filings --accession 0001018724-23-000014
```

### 2. Validate Benchmark Corpus
```python
from eval.corpus_loader import validate_labeled_corpus

result = validate_labeled_corpus()
assert result.valid is True
```

### 3. Run Accuracy Benchmark
```bash
# Offline deterministic mode with mock classifier
python -m eval.run_benchmark --mock-classifier

# Strict regression gate (exits with code 1 on regression)
python -m eval.run_benchmark --strict --mock-classifier
```
