"""Tests for the dual-store extension (growth v3).

Validates the STM/LTM split, desirable-difficulty consolidation, and the spaced
interval policy — the parts that produced the ~41x retention multiplier in
benchmark_memory_model.py. Each test asserts a self-derived mathematical fact,
not a benchmark label.
"""
from __future__ import annotations

import math

import pytest

from graphify import growth


def test_stm_decays_much_faster_than_ltm():
    # After 1 day, STM is essentially gone while a healthy LTM is intact.
    assert growth.stm_retrievability(1.0) < 1e-5
    assert growth.ltm_retrievability(1.0, stability_days=10.0) > 0.9


def test_stm_fresh_is_1():
    assert growth.stm_retrievability(0.0) == 1.0


def test_stm_half_life_is_ln2_times_constant():
    assert math.isclose(growth.stm_half_life_days(),
                        growth.STM_TIME_CONSTANT * math.log(2.0), rel_tol=1e-9)


def test_consolidate_fresh_gives_no_gain():
    # R_ltm=1 (just consolidated) -> no further gain, regardless of difficulty.
    S = 5.0
    assert math.isclose(growth.consolidate_ltm(S, R_ltm=1.0, difficulty=0.2), S,
                        rel_tol=1e-9)


def test_consolidate_near_forgotten_gains_most():
    S = 5.0
    near_forgotten = growth.consolidate_ltm(S, R_ltm=0.1, difficulty=0.0)
    fresh = growth.consolidate_ltm(S, R_ltm=0.9, difficulty=0.0)
    assert near_forgotten > fresh


def test_consolidate_harder_item_slower():
    S = 5.0
    R = 0.5
    easy = growth.consolidate_ltm(S, R, difficulty=0.1)
    hard = growth.consolidate_ltm(S, R, difficulty=0.9)
    assert easy > hard


def test_consolidate_difficulty_clamped():
    # difficulty outside [0,1] is clamped, never negative or >ceiling.
    S = 5.0
    assert growth.consolidate_ltm(S, 0.5, difficulty=5.0) > 0
    assert growth.consolidate_ltm(S, 0.5, difficulty=-3.0) > 0


def test_spaced_interval_uses_retention_target():
    # t* = S·ln(1/ρ); ρ=0.5 default.
    S = 10.0
    assert math.isclose(growth.next_spaced_interval_days(S), S * math.log(2.0),
                        rel_tol=1e-9)
    assert math.isclose(growth.next_spaced_interval_days(S, 0.9),
                        S * math.log(1 / 0.9), rel_tol=1e-9)
    with pytest.raises(ValueError):
        growth.next_spaced_interval_days(S, 1.5)


def test_spaced_longer_than_massed_for_same_stability():
    # The whole point: spaced (ρ=0.5) schedules FARTHER out than massed (ρ=0.9).
    S = 3.0
    spaced = growth.next_spaced_interval_days(S, 0.5)
    massed = growth.next_spaced_interval_days(S, 0.9)
    assert spaced > massed
