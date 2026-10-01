# Evaluation Report: Footnote Benchmark Corpus (dev)

**Target Metric:** Adjusted EBITDA | **Benchmark Corpus Size:** 5 filings | **Total Ground Truth Items:** 31

> [!IMPORTANT]
> **Governance & Transparency Disclosure (CONSTITUTION §6.13)**
> Evaluation conducted on benchmark corpus of 5 filings (31 total ground-truth items). 0 items (0.00%) required human review or manual correction.

## 1. Executive Summary

| Metric | Value | Target / Status |
| :--- | :--- | :--- |
| **Line-Item Extraction Accuracy** | **0.00%** | ❌ FAILED (< 90%) |
| **Macro Precision** | 0.0000 | - |
| **Macro Recall** | 0.0000 | - |
| **Macro F1-Score** | 0.0000 | - |
| **Micro Precision** | 0.0000 | - |
| **Micro Recall** | 0.0000 | - |
| **Micro F1-Score** | 0.0000 | - |
| **Total Filings Evaluated** | 5 | 5 Succeeded, 0 Failed Extractions |
| **Manual Review / Correction Rate** | 0.00% | 0 of 25 extracted items |

## 2. Three-Layer Error Isolation (AC-4)

Isolates pipeline discrepancy counts across architectural boundaries without conflation:

| Pipeline Layer | Discrepancy Count | Layer Description |
| :--- | :--- | :--- |
| **Extraction Layer** | 12 | Missed items, value discrepancies, spurious items, and localization errors |
| **Classification Layer** | 19 | Taxonomy normalization mismatches and unrecognized labels |
| **Generation Layer** | 0 | Formula recalculation errors, zero generated cells, or missing provenance |

## 3. Failed Extraction Threshold Enforcement (AC-5, EC-3)

A filing is designated as a **Failed Extraction** if more than 15.0% of its extracted line items fall outside the auto-accept confidence band (score < 0.95).

✅ **Zero filings exceeded the 15.0% failed extraction threshold.** All benchmark filings achieved high auto-acceptance rates.

## 4. Failure Pattern Classification (AC-7)

| Failure Pattern | Count | Description / Root Cause |
| :--- | :--- | :--- |
| `sign_mismatch` | 0 | Numeric value has correct magnitude but inverted sign (e.g. accounting parentheses error) |
| `multi_column_bleed` | 0 | Text flow across adjacent table columns merged into a single field |
| `merged_cell_misalignment` | 6 | Header or data cell span caused coordinate localization offset |
| `footnote_severance` | 0 | Footnote reference disconnected from primary table line item |
| `unrecognized_label` | 19 | Classification could not match item to standardized taxonomy |
| `missing_item` | 6 | Ground-truth item omitted from pipeline extraction |
| `spurious_item` | 0 | Spurious line item extracted that does not exist in ground truth |

## 5. Per-Filing Performance Breakdown

| Filing ID | Company | GT Items | TP | FP | FN | Accuracy | Precision | Recall | F1 | NFR3 Runtime | Extraction Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `acme_2023_10k` | Acme Corporation | 6 | 0 | 0 | 1 | 0.0% | 0.00 | 0.00 | 0.00 | 0.4s | ✅ Passed |
| `globex_2023_10k` | Globex Industrial Holdings | 5 | 0 | 0 | 1 | 0.0% | 0.00 | 0.00 | 0.00 | 0.2s | ✅ Passed |
| `initech_2023_10k` | Initech Financial Solutions | 7 | 0 | 0 | 1 | 0.0% | 0.00 | 0.00 | 0.00 | 0.3s | ✅ Passed |
| `umbrella_2023_10k` | Umbrella Pharmaceuticals | 6 | 0 | 0 | 2 | 0.0% | 0.00 | 0.00 | 0.00 | 0.3s | ✅ Passed |
| `wayne_2023_10k` | Wayne Enterprises | 7 | 0 | 0 | 1 | 0.0% | 0.00 | 0.00 | 0.00 | 0.2s | ✅ Passed |

## 6. Granular Line-Item Diffs

### Filing: `acme_2023_10k` (Acme Corporation)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Net income | 50,000 | - | - | 0.00 | ⚠️ `missed_item` | `missing_item` |
| 1 | Interest expense | 5,000 | Interest expense / 50,000 | 5,000 | 0.08 | ⚠️ `localization_error` | `merged_cell_misalignment` |
| 1 | Provision for income taxes | 12,000 | Provision for income taxes / 50,000 | 12,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Depreciation and amortization | 8,000 | Depreciation and amortization / 50,000 | 8,000 | 0.08 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Stock-based compensation expense | 15,000 | Stock-based compensation expense / 50,000 | 15,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 90,000 | Adjusted EBITDA / 50,000 | 90,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |

### Filing: `globex_2023_10k` (Globex Industrial Holdings)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Operating income | 120,000 | - | - | 0.00 | ⚠️ `missed_item` | `missing_item` |
| 1 | Depreciation and amortization | 22,000 | Depreciation and amortization / 120,000 | 22,000 | 0.10 | ⚠️ `localization_error` | `merged_cell_misalignment` |
| 1 | Restructuring and facility exit costs | 14,000 | Restructuring and facility exit costs / 120,000 | 14,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Litigation settlement expense | 6,000 | Litigation settlement expense / 120,000 | 6,000 | 0.08 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 162,000 | Adjusted EBITDA / 120,000 | 162,000 | 0.12 | ⚠️ `classification_mismatch` | `unrecognized_label` |

### Filing: `initech_2023_10k` (Initech Financial Solutions)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Net loss | (15,000) | - | - | 0.00 | ⚠️ `missed_item` | `missing_item` |
| 1 | Interest expense, net | 8,000 | Interest expense, net / (15,000) | 8,000 | 0.08 | ⚠️ `localization_error` | `merged_cell_misalignment` |
| 1 | Income tax benefit | (3,000) | Income tax benefit / (15,000) | (3,000) | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Depreciation and amortization | 12,000 | Depreciation and amortization / (15,000) | 12,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Share-based compensation | 18,000 | Share-based compensation / (15,000) | 18,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Gain on disposal of assets | (2,500) | Gain on disposal of assets / (15,000) | (2,500) | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 17,500 | Adjusted EBITDA / (15,000) | 17,500 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |

### Filing: `umbrella_2023_10k` (Umbrella Pharmaceuticals)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Net income | 80,000 | - | - | 0.00 | ⚠️ `missed_item` | `missing_item` |
| 1 | Depreciation & Amortization | 18,000 | Depreciation & Amortization / 80,000 | 18,000 | 0.10 | ⚠️ `localization_error` | `merged_cell_misalignment` |
| 1 | Stock-based compensation | 25,000 | Stock-based compensation / 80,000 | 25,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 123,000 | Adjusted EBITDA / 80,000 | 123,000 | 0.12 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 2 | R&D stock-based compensation | 15,000 | - | - | 0.00 | ⚠️ `missed_item` | `missing_item` |
| 2 | SG&A stock-based compensation | 10,000 | SG&A stock-based compensation / 15,000 | 10,000 | 0.10 | ⚠️ `localization_error` | `merged_cell_misalignment` |

### Filing: `wayne_2023_10k` (Wayne Enterprises)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Net income | 250,000 | - | - | 0.00 | ⚠️ `missed_item` | `missing_item` |
| 1 | Interest expense | 30,000 | Interest expense / 250,000 | 30,000 | 0.10 | ⚠️ `localization_error` | `merged_cell_misalignment` |
| 1 | Provision for taxes | 55,000 | Provision for taxes / 250,000 | 55,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Depreciation & amortization | 40,000 | Depreciation & amortization / 250,000 | 40,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Operating lease cost adjustment | 12,000 | Operating lease cost adjustment / 250,000 | 12,000 | 0.10 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Transaction & acquisition costs _(opt)_ | 7,500 | Transaction & acquisition costs / 250,000 | 7,500 | 0.08 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 394,500 | Adjusted EBITDA / 250,000 | 394,500 | 0.11 | ⚠️ `classification_mismatch` | `unrecognized_label` |
