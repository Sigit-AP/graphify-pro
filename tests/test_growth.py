"""Tests for graphify.growth v2 — the self-consistent pure-math memory model.

Validates the single Ebbinghaus decay law and its derived update rules, the
spacing effect (recall at low R strengthens more), lapse collapse, and the
time-aware weakness detection.
"""
from __future__ import annotations

import math

import pytest

from graphify import growth


def test_retrievability_exponential_decay():
    assert growth.retrievability(0.0, 10.0) == 1.0
    assert math.isclose(growth.retrievability(10.0, 10.0), math.exp(-1), rel_tol=1e-9)
    assert math.isclose(growth.retrievability(20.0, 10.0), math.exp(-2), rel_tol=1e-9)
    # negative elapsed clamps to 0 (no going above 1.0)
    assert growth.retrievability(-5.0, 10.0) == 1.0
    assert growth.retrievability(1.0, 0.0) == 0.0


def test_half_life_formula():
    assert math.isclose(growth.half_life_days(10.0), 10.0 * math.log(2), rel_tol=1e-9)


def test_next_review_formula():
    # t* = S·ln(1/ρ); for S=10, ρ=0.9 -> 10·ln(1/0.9) = 10·ln(1.111..)
    assert math.isclose(growth.next_review_days(10.0, 0.9), 10.0 * math.log(1/0.9), rel_tol=1e-9)
    with pytest.raises(ValueError):
        growth.next_review_days(10.0, 1.5)


def test_spacing_effect_recall_at_low_R_strengthens_more():
    S = 5.0
    S_fresh = growth.stability_after_success(S, R_at_review=1.0)  # no forgetting -> no gain
    S_low = growth.stability_after_success(S, R_at_review=0.2)    # nearly forgotten -> big gain
    assert math.isclose(S_fresh, S, rel_tol=1e-9)
    assert S_low > S


def test_lapse_collapses_stability():
    S = 20.0
    after = growth.stability_after_lapse(S)
    assert after < S
    assert math.isclose(after, S * 0.5, rel_tol=1e-9)


def test_engine_spaced_recall_strengthens_long_term():
    eng = growth.GrowthEngine()
    eng.register("a")
    s0 = eng.snapshot("a")
    for i in range(5):
        eng.items["a"].last_recall_ts -= (i + 1) * 86400.0  # spaced
        eng.recall("a", success=True)
    s1 = eng.snapshot("a")
    assert s1["stability_days"] > s0["stability_days"]
    assert s1["repetitions"] == 5


def test_engine_silence_forgets():
    eng = growth.GrowthEngine()
    eng.register("b")
    eng.items["b"].last_recall_ts -= 100 * 86400.0
    snap = eng.snapshot("b")
    assert snap["retrievability"] < 0.5
    assert snap["weakness_score"] > 0.0


def test_engine_lapse_tracks_and_detects_weakness():
    eng = growth.GrowthEngine()
    eng.register("c")
    eng.items["c"].stability = 0.5
    eng.items["c"].last_recall_ts -= 50 * 86400.0  # long silence
    snap = eng.snapshot("c")
    assert snap["retrievability"] < 0.7
    # a lapse then flags it weak via lapse_count
    eng.recall("c", success=False)
    snap2 = eng.snapshot("c")
    assert snap2["lapse_count"] == 1


def test_engine_restore_roundtrip():
    eng = growth.GrowthEngine()
    eng.register("x")
    eng.items["x"].stability = 7.5
    eng.items["x"].repetitions = 3
    eng.items["x"].lapse_count = 1
    state = {k: v for k, v in eng.items.items()}

    eng2 = growth.GrowthEngine()
    n = eng2.restore({"x": eng.snapshot("x")})
    assert n == 1
    s = eng2.snapshot("x")
    assert s["stability_days"] == 7.5
    assert s["repetitions"] == 3
    assert s["lapse_count"] == 1


def test_record_query_recalls_creates_store(tmp_path):
    # storage is always available in the package, so recording 1 node returns 1.
    n = growth.record_query_recalls(str(tmp_path / "fresh.db"), ["a"])
    assert n == 1
