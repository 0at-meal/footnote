# Footnote: Glossary

### SEC and filing terms

**CIK.** SEC Central Index Key, the filer's permanent identifier, written
zero-padded to 10 digits (e.g. `0001652044`). Archive URLs use the unpadded
integer: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{document}`.

**Accession number.** Unique ID of one filing submission, `XXXXXXXXXX-YY-NNNNNN`.
The first ten digits identify the *submitter* (often a filing agent), not
necessarily the company. Never derive a CIK from an accession number.

**Submissions API.** `https://data.sec.gov/submissions/CIK##########.json`.
Returns company metadata plus `filings.recent` (most recent filings). Older
filings are in separate JSON files listed under `filings.files`.

**8-K Item 2.02 ("Results of Operations and Financial Condition").** The 8-K
item used to furnish an earnings release.

**EX-99.1.** The exhibit that typically carries the earnings press release on
an Item 2.02 8-K. It is usually HTML, and its tables are generally not
XBRL-tagged.

**iXBRL (Inline XBRL).** XBRL facts embedded in HTML via `ix:nonFraction` and
similar tags. Each tag carries a concept (e.g. `us-gaap:NetIncomeLoss`), a
context (period), unit, scale, and sign.

**Foreign filer.** Files 20-F / 40-F / 6-K instead of 10-K / 10-Q / 8-K. These
filers are unsupported, and the EDGAR client raises
`ForeignFilerUnsupportedError` for them.

### Financial terms

**Non-GAAP financial measure.** A measure that adjusts a GAAP figure, such as
Adjusted EBITDA, Adjusted Net Income, or Free Cash Flow.

**Reconciliation table (bridge).** The table that walks from the most
comparable GAAP measure (e.g. net income) to the non-GAAP measure, line by
line.

**Add-back / adjustment.** A reconciliation line added to or subtracted from
the GAAP starting point, e.g. stock-based compensation, D&A, restructuring,
impairment, acquisition costs, litigation. These map to
`StandardAddBackCategory`.

**Scale.** The unit caption of a table ("in thousands", "in millions").
Per-share and percentage rows are exempt from scaling.

**Sign.** Direction of a line. Parentheses, minus signs, and label directives
such as "Less:" mark a deduction.

### Code terms

**ExtractedRecord.** One extracted value. It holds the raw as-reported string
(`value`), a label path (`label`), and a provenance `locator`. The legacy
`page`/`bbox`/`source_file` fields are kept in sync for compatibility.

**Locator.** A discriminated union. `HtmlLocator` holds the accession,
document, XPath, an optional character range, and a URL. `PdfLocator` holds a
page and a bbox normalized to 0–1000.

**Master taxonomy.** Canonical line items with aliases, used for deterministic
label matching (`match_master_taxonomy`). Unmatched labels become
`pending_taxonomy_confirmation`; they are never auto-accepted.
