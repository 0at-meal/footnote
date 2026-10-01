"""
Unit tests for Shared Extraction Cache and Per-User Overlay (FN-025).
"""


from app.extraction.locator import HtmlLocator
from app.extraction.models import ExtractedRecord
from app.extraction.shared_cache import (
    CacheKey,
    SharedExtractionCache,
)


def _make_sample_record(value: str = "100", label: str = "Net Income") -> ExtractedRecord:
    loc = HtmlLocator(
        accession="0001652044-24-000088",
        document="goog-10q.htm",
        element_path="/html/body/table[1]/tr[1]/td[2]",
    )
    return ExtractedRecord(
        value=value,
        label=label,
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
        source_file="goog-10q.htm",
        locator=loc,
    )


def test_merge_precedence_user_over_verified_over_machine() -> None:
    cache = SharedExtractionCache()
    key = CacheKey(
        accession="0001652044-24-000088",
        document="goog-10q.htm",
        pack="non_gaap_bridge",
        extractor_version="2.0.0",
        taxonomy_version="2026.1",
    )

    # 1. Base machine extraction: value = "100"
    rec1 = _make_sample_record(value="100", label="Adjusted EBITDA")
    cache.put_machine_base(key, [rec1])

    # Unmodified user sees machine base
    res_clean = cache.get_merged(user_id="user_unmodified", key=key)
    assert res_clean[0].record.value == "100"
    assert res_clean[0].origin_layer == "machine"

    # 2. Staff approves a verified correction: value = "110"
    cache.approve_by_staff(
        staff_user_id="lead_analyst",
        key=key,
        item_id="Adjusted EBITDA",
        field="value",
        new_value="110",
    )

    # User B (without private overlay) sees verified correction
    res_user_b = cache.get_merged(user_id="user_b", key=key)
    assert res_user_b[0].record.value == "110"
    assert res_user_b[0].origin_layer == "verified"
    assert res_user_b[0].is_verified_correction is True

    # 3. User A submits private overlay: value = "120"
    cache.submit_user_correction(
        user_id="user_a",
        key=key,
        item_id="Adjusted EBITDA",
        field="value",
        old_value="110",
        new_value="120",
    )

    # User A sees private overlay (user > verified)
    res_user_a = cache.get_merged(user_id="user_a", key=key)
    assert res_user_a[0].record.value == "120"
    assert res_user_a[0].origin_layer == "user"
    assert res_user_a[0].is_user_modified is True

    # User B still sees verified correction ("110"), strictly isolated from User A's private overlay
    res_user_b_again = cache.get_merged(user_id="user_b", key=key)
    assert res_user_b_again[0].record.value == "110"
    assert res_user_b_again[0].origin_layer == "verified"


def test_promotion_via_consensus_threshold() -> None:
    # Threshold N = 3 users
    cache = SharedExtractionCache(consensus_threshold=3)
    key = CacheKey(
        accession="0001652044-24-000088",
        document="goog-10q.htm",
        pack="non_gaap_bridge",
    )
    rec = _make_sample_record(value="50", label="Stock-based compensation")
    cache.put_machine_base(key, [rec])

    # User 1 submits correction
    cache.submit_user_correction("u1", key, "Stock-based compensation", "value", "50", "65")
    # Not yet promoted
    assert cache.get_merged("u4", key)[0].record.value == "50"

    # User 2 submits same correction
    cache.submit_user_correction("u2", key, "Stock-based compensation", "value", "50", "65")
    # Not yet promoted (2 < 3)
    assert cache.get_merged("u4", key)[0].record.value == "50"

    # User 3 submits same correction -> Consensus reached!
    cache.submit_user_correction("u3", key, "Stock-based compensation", "value", "50", "65")

    # User 4 (third party) now receives the promoted verified correction
    res_u4 = cache.get_merged("u4", key)
    assert res_u4[0].record.value == "65"
    assert res_u4[0].origin_layer == "verified"
    assert res_u4[0].is_verified_correction is True


def test_no_per_user_data_in_shared_layer() -> None:
    cache = SharedExtractionCache()
    key = CacheKey(
        accession="0001652044-24-000088",
        document="goog-10q.htm",
        pack="non_gaap_bridge",
    )
    rec = _make_sample_record(value="100", label="Net Income")
    cache.put_machine_base(key, [rec])

    # User submits private correction
    cache.submit_user_correction(
        user_id="secret_trader_42",
        key=key,
        item_id="Net Income",
        field="value",
        old_value="100",
        new_value="999",
    )

    # Inspect the raw shared layer data
    shared_dump = cache.get_shared_layer_raw(key)

    # Verification: 'secret_trader_42' or '999' must NOT appear anywhere in the shared base or verified layer
    raw_json = str(shared_dump)
    assert "secret_trader_42" not in raw_json
    assert "999" not in raw_json


def test_invalidation_and_audit_preservation_on_version_bump() -> None:
    cache = SharedExtractionCache()
    key_v1 = CacheKey(
        accession="0001652044-24-000088",
        document="goog-10q.htm",
        pack="non_gaap_bridge",
        extractor_version="2.0.0",
        taxonomy_version="2026.1",
    )
    rec_v1 = _make_sample_record(value="100")
    cache.put_machine_base(key_v1, [rec_v1])

    # Key v2 representing a bumped extractor version
    key_v2 = CacheKey(
        accession="0001652044-24-000088",
        document="goog-10q.htm",
        pack="non_gaap_bridge",
        extractor_version="2.1.0",
        taxonomy_version="2026.2",
    )

    # v2 is a cache miss (triggers lazy recompute)
    assert cache.get_machine_base(key_v2) is None

    # v1 is still preserved in cache for audit trail
    entry_v1 = cache.get_machine_base(key_v1)
    assert entry_v1 is not None
    assert entry_v1.records[0].value == "100"


def test_supersedes_link_for_amended_filings() -> None:
    cache = SharedExtractionCache()
    orig_key = CacheKey(
        accession="0001652044-24-000010",
        document="goog-10k.htm",
        pack="non_gaap_bridge",
    )
    amended_key = CacheKey(
        accession="0001652044-24-000099",
        document="goog-10ka.htm",
        pack="non_gaap_bridge",
    )

    # Put original 10-K
    entry_orig = cache.put_machine_base(orig_key, [_make_sample_record(value="1000")])
    assert entry_orig.is_superseded is False

    # Put 10-K/A which supersedes original
    entry_amended = cache.put_machine_base(
        amended_key,
        [_make_sample_record(value="1050")],
        supersedes_accession="0001652044-24-000010",
    )

    assert entry_amended.supersedes == "0001652044-24-000010"

    # Original entry is linked and marked superseded while preserved for audit
    updated_orig = cache.get_machine_base(orig_key)
    assert updated_orig is not None
    assert updated_orig.is_superseded is True
    assert updated_orig.superseded_by == "0001652044-24-000099"
    assert updated_orig.records[0].value == "1000"
