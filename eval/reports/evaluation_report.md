# Evaluation Report: Footnote Benchmark Corpus

**Target Metric:** Adjusted EBITDA | **Benchmark Corpus Size:** 5 filings | **Total Ground Truth Items:** 31

> [!IMPORTANT]
> **Governance & Transparency Disclosure (CONSTITUTION §6.13)**
> Evaluation conducted on benchmark corpus of 5 filings (31 total ground-truth items). 66 items (100.00%) required human review or manual correction.

## 1. Executive Summary

| Metric | Value | Target / Status |
| :--- | :--- | :--- |
| **Line-Item Extraction Accuracy** | **12.90%** | ❌ FAILED (< 90%) |
| **Macro Precision** | 0.1333 | - |
| **Macro Recall** | 0.2000 | - |
| **Macro F1-Score** | 0.1600 | - |
| **Micro Precision** | 0.1026 | - |
| **Micro Recall** | 1.0000 | - |
| **Micro F1-Score** | 0.1861 | - |
| **Total Filings Evaluated** | 5 | 0 Succeeded, 5 Failed Extractions |
| **Manual Review / Correction Rate** | 100.00% | 66 of 66 extracted items |

## 2. Three-Layer Error Isolation (AC-4)

Isolates pipeline discrepancy counts across architectural boundaries without conflation:

| Pipeline Layer | Discrepancy Count | Layer Description |
| :--- | :--- | :--- |
| **Extraction Layer** | 35 | Missed items, value discrepancies, spurious items, and localization errors |
| **Classification Layer** | 27 | Taxonomy normalization mismatches and unrecognized labels |
| **Generation Layer** | 0 | Formula recalculation errors, zero generated cells, or missing provenance |

## 3. Failed Extraction Threshold Enforcement (AC-5, EC-3)

A filing is designated as a **Failed Extraction** if more than 15.0% of its extracted line items fall outside the auto-accept confidence band (score < 0.95).

⚠️ **5 filing(s)** exceeded the 15.0% threshold:

| Filing ID | Company | Non-Auto-Accepted Count | Non-Auto-Accepted % | Status |
| :--- | :--- | :--- | :--- | :--- |
| `acme_2023_10k` | Acme Corporation | 14 | 100.0% | ❌ Failed Extraction |
| `globex_2023_10k` | Globex Industrial Holdings | 12 | 100.0% | ❌ Failed Extraction |
| `initech_2023_10k` | Initech Financial Solutions | 16 | 100.0% | ❌ Failed Extraction |
| `umbrella_2023_10k` | Umbrella Pharmaceuticals | 8 | 100.0% | ❌ Failed Extraction |
| `wayne_2023_10k` | Wayne Enterprises | 16 | 100.0% | ❌ Failed Extraction |

## 4. Failure Pattern Classification (AC-7)

| Failure Pattern | Count | Description / Root Cause |
| :--- | :--- | :--- |
| `sign_mismatch` | 0 | Numeric value has correct magnitude but inverted sign (e.g. accounting parentheses error) |
| `multi_column_bleed` | 0 | Text flow across adjacent table columns merged into a single field |
| `merged_cell_misalignment` | 0 | Header or data cell span caused coordinate localization offset |
| `footnote_severance` | 0 | Footnote reference disconnected from primary table line item |
| `unrecognized_label` | 27 | Classification could not match item to standardized taxonomy |
| `missing_item` | 0 | Ground-truth item omitted from pipeline extraction |
| `spurious_item` | 35 | Spurious line item extracted that does not exist in ground truth |

## 5. Per-Filing Performance Breakdown

| Filing ID | Company | GT Items | TP | FP | FN | Accuracy | Precision | Recall | F1 | NFR3 Runtime | Extraction Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `acme_2023_10k` | Acme Corporation | 6 | 0 | 8 | 0 | 0.0% | 0.00 | 0.00 | 0.00 | 16.7s | ❌ Failed |
| `globex_2023_10k` | Globex Industrial Holdings | 5 | 0 | 7 | 0 | 0.0% | 0.00 | 0.00 | 0.00 | 7.8s | ❌ Failed |
| `initech_2023_10k` | Initech Financial Solutions | 7 | 0 | 9 | 0 | 0.0% | 0.00 | 0.00 | 0.00 | 6.3s | ❌ Failed |
| `umbrella_2023_10k` | Umbrella Pharmaceuticals | 6 | 4 | 2 | 0 | 66.7% | 0.67 | 1.00 | 0.80 | 5.8s | ❌ Failed |
| `wayne_2023_10k` | Wayne Enterprises | 7 | 0 | 9 | 0 | 0.0% | 0.00 | 0.00 | 0.00 | 6.6s | ❌ Failed |

## 6. Granular Line-Item Diffs

### Filing: `acme_2023_10k` (Acme Corporation)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Net income | 50,000 | 50,000 | 50,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Interest expense | 5,000 | 5,000 | 5,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Provision for income taxes | 12,000 | 12,000 | 12,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Depreciation and amortization | 8,000 | 8,000 | 8,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Stock-based compensation expense | 15,000 | 15,000 | 15,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 90,000 | 90,000 | 90,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | - | - | Net income | Net income | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Interest expense | Interest expense | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Provision for income taxes | Provision for income taxes | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Depreciation and amortization | Depreciation and amortization | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Stock-based compensation expense | Stock-based compensation expense | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Adjusted EBITDA | Adjusted EBITDA | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | No additional manual adjustments required | No additional manual adjustments required | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | -- | -- | 0.00 | ⚠️ `spurious_item` | `spurious_item` |

### Filing: `globex_2023_10k` (Globex Industrial Holdings)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Operating income | 120,000 | 120,000 | 120,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Depreciation and amortization | 22,000 | 22,000 | 22,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Restructuring and facility exit costs | 14,000 | 14,000 | 14,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Litigation settlement expense | 6,000 | 6,000 | 6,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 162,000 | 162,000 | 162,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | - | - | Operating income | Operating income | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Depreciation and amortization | Depreciation and amortization | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Restructuring and facility exit costs | Restructuring and facility exit costs | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Litigation settlement expense | Litigation settlement expense | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Adjusted EBITDA | Adjusted EBITDA | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | No additional manual adjustments required | No additional manual adjustments required | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | -- | -- | 0.00 | ⚠️ `spurious_item` | `spurious_item` |

### Filing: `initech_2023_10k` (Initech Financial Solutions)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Net loss | (15,000) | (15,000) | (15,000) | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Interest expense, net | 8,000 | 8,000 | 8,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Income tax benefit | (3,000) | (3,000) | (3,000) | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Depreciation and amortization | 12,000 | 12,000 | 12,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Share-based compensation | 18,000 | 18,000 | 18,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Gain on disposal of assets | (2,500) | (2,500) | (2,500) | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 17,500 | 17,500 | 17,500 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | - | - | Net loss | Net loss | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Interest expense, net | Interest expense, net | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Income tax benefit | Income tax benefit | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Depreciation and amortization | Depreciation and amortization | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Share-based compensation | Share-based compensation | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Gain on disposal of assets | Gain on disposal of assets | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Adjusted EBITDA | Adjusted EBITDA | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | No additional manual adjustments required | No additional manual adjustments required | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | -- | -- | 0.00 | ⚠️ `spurious_item` | `spurious_item` |

### Filing: `umbrella_2023_10k` (Umbrella Pharmaceuticals)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Net income | 80,000 | 80,000 | 80,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Depreciation & Amortization | 18,000 | Depreciation & Amortization | 18,000 | 0.67 | ✅ `exact_match` | `none` |
| 1 | Stock-based compensation | 25,000 | Stock-based compensation | 25,000 | 0.67 | ✅ `exact_match` | `none` |
| 1 | Adjusted EBITDA | 123,000 | Adjusted EBITDA | 123,000 | 0.67 | ✅ `exact_match` | `none` |
| 2 | R&D stock-based compensation | 15,000 | R&D stock-based compensation | 15,000 | 0.67 | ✅ `exact_match` | `none` |
| 2 | SG&A stock-based compensation | 10,000 | 10,000 | 10,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | - | - | Net income | Net income | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | SG&A stock-based compensation | SG&A stock-based compensation | 0.00 | ⚠️ `spurious_item` | `spurious_item` |

### Filing: `wayne_2023_10k` (Wayne Enterprises)

| Page | Ground Truth Label | GT Value | Extracted Label | Extracted Value | IoU | Match Status | Failure Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Net income | 250,000 | 250,000 | 250,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Interest expense | 30,000 | 30,000 | 30,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Provision for taxes | 55,000 | 55,000 | 55,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Depreciation & amortization | 40,000 | 40,000 | 40,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Operating lease cost adjustment | 12,000 | 12,000 | 12,000 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Transaction & acquisition costs _(opt)_ | 7,500 | 7,500 | 7,500 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | Adjusted EBITDA | 394,500 | 394,500 | 394,500 | 0.67 | ⚠️ `classification_mismatch` | `unrecognized_label` |
| 1 | - | - | Net income | Net income | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Interest expense | Interest expense | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Provision for taxes | Provision for taxes | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Depreciation & amortization | Depreciation & amortization | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Operating lease cost adjustment | Operating lease cost adjustment | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Transaction & acquisition costs | Transaction & acquisition costs | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 1 | - | - | Adjusted EBITDA | Adjusted EBITDA | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | No additional manual adjustments required | No additional manual adjustments required | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
| 2 | - | - | -- | -- | 0.00 | ⚠️ `spurious_item` | `spurious_item` |
