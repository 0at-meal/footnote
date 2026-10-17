"""
Tests for the P0-10 regression gate. The reports below are synthetic fixtures;
the last test reads the committed baseline and thresholds files.
"""

import json
from pathlib import Path
from typing import Any

import yaml
from tools.eval.score import HEADLINE_METRICS, SCORER_VERSION, check_thresholds

EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"
SHA = "f" * 64


def report(**rates: float | None) -> dict[str, Any]:
    return {
        "scorer_version": SCORER_VERSION,
        "gold": {"labels_sha256": SHA},
        "metrics": {
            name: {"overall": {"rate": rates.get(name, 0.5)}}
            for name in HEADLINE_METRICS
        },
    }


def thresholds(**floors: float) -> dict[str, Any]:
    return {
        "scorer_version": SCORER_VERSION,
        "labels_sha256": SHA,
        "metrics": {name: floors.get(name, 0.5) for name in HEADLINE_METRICS},
    }


def test_equal_or_better_passes() -> None:
    assert check_thresholds(report(), thresholds()) == []
    assert check_thresholds(report(line_exact_match=0.9), thresholds()) == []


def test_any_headline_drop_fails() -> None:
    problems = check_thresholds(report(sign_accuracy=0.4999), thresholds())
    assert problems == ["sign_accuracy regressed: 0.4999 < baseline 0.5"]


def test_no_scored_values_fails() -> None:
    assert check_thresholds(report(table_found=None), thresholds())


def test_changed_gold_set_or_scorer_fails() -> None:
    assert check_thresholds(report(), {**thresholds(), "labels_sha256": "0" * 64})
    assert check_thresholds(report(), {**thresholds(), "scorer_version": 0})


def test_missing_or_unknown_threshold_fails() -> None:
    floors = thresholds()
    del floors["metrics"]["scale_accuracy"]
    assert check_thresholds(report(), floors) == [
        "no threshold recorded for scale_accuracy"
    ]
    floors = thresholds()
    floors["metrics"]["recall"] = 0.1
    assert check_thresholds(report(), floors) == [
        "unknown metric in thresholds: recall"
    ]


def test_committed_thresholds_match_the_recorded_baseline() -> None:
    floors = yaml.safe_load((EVAL_DIR / "thresholds.yaml").read_text("utf-8"))
    baseline = json.loads(
        (EVAL_DIR / "results" / "baseline-2026-10-17.json").read_text("utf-8")
    )
    assert check_thresholds(baseline, floors) == []
    for name in HEADLINE_METRICS:
        assert floors["metrics"][name] == baseline["metrics"][name]["overall"]["rate"]
