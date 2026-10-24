"""Change-feed amounts in the snapshot (``raw_usd``, ``impact_usd``)."""

from __future__ import annotations

from app.analytics.snapshot import raw_usd


def test_raw_usd_reads_accounting_cells() -> None:
    assert raw_usd("(1,431)", "thousands") == -1_431_000.0
    assert raw_usd("$ 12.5", "millions") == 12_500_000.0
    assert raw_usd("225", "millions") == 225_000_000.0
    assert raw_usd("− 3", "units") == -3.0


def test_raw_usd_refuses_non_numbers_and_unknown_scale() -> None:
    assert raw_usd("—", "millions") is None
    assert raw_usd("3 of 9 lines carried over", "millions") is None
    assert raw_usd(None, "millions") is None
    assert raw_usd("12", None) is None
