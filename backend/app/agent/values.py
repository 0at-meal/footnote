"""
Values the agent may cite, each under a stable value ID (``vid``), and the
per-session ledger of every value a tool returned (ADR-011).

- ``obs:<bridge_id>:<row_order>:<period_id>``: one stored observation.
- ``norm:<cik>:<period_id>:<policy_version>``: a normalized EBITDA figure.
- ``calc:<sha256[:12]>``: a deterministic computation over other vids.

The model cites vids; the renderer writes the numbers. A vid the session never
retrieved cannot be cited (the provenance gate checks the ledger).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Unit = Literal["usd", "percent", "ratio", "items"]


class Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vid: str
    kind: Literal["obs", "norm", "calc"]
    ticker: str
    label: str
    period_id: str | None
    value: Decimal | None  # None for a dash placeholder
    value_raw: str | None = None  # as reported, for observations
    unit: Unit = "usd"
    scale: str | None = None  # units | thousands | millions | billions
    role: str | None = None
    sign: int | None = None  # +1 adds toward the total, -1 subtracts
    line_key: str | None = None
    accession: str | None = None
    filed: str | None = None
    url: str | None = None
    xpath: str | None = None
    checks: dict[str, str] = Field(default_factory=dict)  # sum / anchor status
    verified: bool = False  # sum and anchor pass and the scale is known
    formula: str | None = None  # calc only
    inputs: tuple[str, ...] = ()  # calc / norm: the vids it was computed from
    notes: tuple[str, ...] = ()

    def brief(self) -> dict[str, Any]:
        """What a tool result shows the model about this value."""
        out: dict[str, Any] = {
            "vid": self.vid,
            "label": self.label,
            "period_id": self.period_id,
            "value": None if self.value is None else str(self.value),
            "unit": self.unit,
        }
        for name in ("value_raw", "scale", "role", "sign", "filed", "formula"):
            if getattr(self, name) is not None:
                out[name] = getattr(self, name)
        if self.kind != "calc":
            out["verified"] = self.verified
            out["checks"] = self.checks
        if self.notes:
            out["notes"] = list(self.notes)
        return out


class Ledger:
    """Every value retrieved in one agent session, by vid."""

    def __init__(self) -> None:
        self._values: dict[str, Value] = {}

    def add(self, values: list[Value]) -> None:
        for v in values:
            prior = self._values.get(v.vid)
            if prior is not None and prior != v:
                raise ValueError(f"vid {v.vid} retrieved with two different values")
            self._values[v.vid] = v

    def get(self, vid: str) -> Value | None:
        return self._values.get(vid)

    def __contains__(self, vid: object) -> bool:
        return vid in self._values

    def __len__(self) -> int:
        return len(self._values)

    def all(self) -> list[Value]:
        return list(self._values.values())
