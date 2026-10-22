"""
Deterministic category suggestions for bridge adjustment lines (spec v0.1 §4).

These are *suggestions*, recorded in label memory with ``source='rule'`` and
shown as pending review. Spec §4.5 says a category is decided by label memory
or a human; a rule never overrides a human decision (``Store.set_label``).
No LLM is involved. A label that matches no rule is ``OTHER``, which blocks the
normalized number until someone classifies it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Order matters only for readability; every matching code is collected.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("NCI", re.compile(r"non[- ]?controlling|minority interest")),
    (
        "TAX",
        re.compile(
            r"income tax|tax (?:provision|benefit|expense)|provision for .{0,30}tax"
            r"|benefit from .{0,30}tax|\btaxes\b|tax[- ]effect"
        ),
    ),
    (
        "DEBT",
        re.compile(
            r"extinguishment|debt financing|refinanc|retirement of debt|(?:gain|loss)"
            r" on debt|debt modification|early redemption|financing arrangement"
        ),
    ),
    # Receivables securitization costs are a financing cost.
    ("INT", re.compile(r"\binterest\b(?! in\b)|securitization")),
    ("DA", re.compile(r"depreciation|amortization|depletion")),
    (
        "SBC",
        re.compile(
            r"stock[- ]based|share[- ]based|stock compensation|equity[- ]based comp"
            r"|equity compensation|non[- ]?cash compensation|stock and deferred comp"
            r"|stock[- ]settled|restricted stock|deferred compensation"
        ),
    ),
    (
        "RESTR",
        re.compile(
            r"restructuring|severance|termination benefits|exit (?:cost|activit)"
            r"|reorganization|idled? facilit|indefinite idle|office closure"
        ),
    ),
    (
        "TRANSFORM",
        re.compile(
            r"transformation|modernization|simplification|cloud computing"
            r"|implementation (?:cost|expense)|\berp\b|optimization|it infrastructure"
        ),
    ),
    (
        "IMPAIR",
        re.compile(r"impairment|write[- ]?downs?|write[- ]?offs?|property charges"),
    ),
    (
        "MA",
        re.compile(
            r"acquisition|transaction|integration|merger|separation|spin[- ]?off"
            r"|business combination|purchase accounting|former parent"
        ),
    ),
    ("LITIG", re.compile(r"litigation|legal|settlement|investigation|arbitration")),
    ("ENV", re.compile(r"environmental|remediation")),
    (
        "FX",
        re.compile(
            r"foreign (?:currency|exchange)|exchange (?:\(?gains?|\(?loss)|currency"
        ),
    ),
    (
        "DERIV",
        re.compile(
            r"fair value|derivative|warrant|contingent consideration|earn[- ]?out"
            r"|mark[- ]to[- ]market|financial instruments|contingent purchase price"
            r"|\bswaps?\b|\bhedg"
        ),
    ),
    (
        "DIVEST",
        re.compile(
            r"\bsales? of\b|disposal|disposition|retirement of (?:fixed )?assets"
            r"|deconsolidation|divestiture|property transactions|held for sale"
        ),
    ),
    ("PREOPEN", re.compile(r"pre[- ]?opening|start[- ]?up|launch")),
    ("RENT", re.compile(r"\brent\b|\blease")),
    ("CORP", re.compile(r"corporate (?:general|g&a|expense|cost|overhead)")),
    (
        "NONOP",
        re.compile(
            r"other \(?(?:income|expense)|non[- ]?operating|pension|equity (?:in|method)"
            r"|(?:gain|loss)e?s? on investments?|investment (?:gain|loss|income)"
            r"|other (?:income|expense)(?:\)|,)|unconsolidated affiliates"
            r"|miscellaneous \(?(?:income|expense)|joint venture ebitda"
            r"|attributable ebitda|investment (?:expense|\(?income)"
        ),
    ),
    ("SYNERGY", re.compile(r"synerg|run[- ]?rate|cost savings")),
    # Cost recoveries shown as revenue are revenue-side (spec §4.2, CC).
    ("REV", re.compile(r"\brevenues?\b|spend recovery")),
]
_OTHER_NR = re.compile(
    r"^other\b|other items|other adjustments|non[- ]?recurring|unusual|special items"
    r"|:\s*other$|recall|incident|weather|insurance|\blifo\b|special bonus"
    r"|certain operating expense|professional (?:advisory )?fees|advisory income"
    r"|indemnified"
)
_RESIDUAL = re.compile(r"\band other\b|,\s*and other\b|\bother,? net\b")
_NETTED = re.compile(r"net of (?:insurance|recover)|a portion of|partially offset")
# Codes that a label can name incidentally alongside a more specific one.
_SUBSUMED = {
    ("DEBT", "INT"),  # "loss on debt financing ... interest" is DEBT
    ("FX", "DERIV"),
    ("NCI", "TAX"),
    ("NCI", "INT"),  # "noncontrolling interest"
    ("DEBT", "MA"),  # "debt financing transactions"
    ("REV", "MA"),
    ("REV", "DERIV"),  # "warrant revenue" is revenue-side (spec §4.2)
    # Gaming "property transactions, net": gains, losses and impairments on
    # property, not M&A.
    ("DIVEST", "MA"),
}
# "(excluding amortization of intangible assets)" names what is *not* included.
_EXCLUDING = re.compile(r"\((?:excluding|excludes|other than)[^)]*\)")


@dataclass(frozen=True)
class Suggestion:
    code: str
    components: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()


def suggest(line_key: str) -> Suggestion:
    """Category suggestion for one normalized adjustment label."""
    text = _EXCLUDING.sub("", line_key.lower())
    codes = [code for code, pat in _RULES if pat.search(text)]
    for keep, drop in _SUBSUMED:
        if keep in codes and drop in codes:
            codes.remove(drop)
    flags: list[str] = []
    if _NETTED.search(text):
        flags.append("netted")
    if codes and _RESIDUAL.search(text):
        flags.append("residual_other")
    if not codes:
        if _OTHER_NR.search(text):
            return Suggestion("OTHER_NR", flags=tuple(flags))
        return Suggestion("OTHER", flags=tuple(flags))
    if len(codes) == 1:
        return Suggestion(codes[0], flags=tuple(flags))
    return Suggestion("MIXED", components=tuple(codes), flags=(*flags, "mixed"))
