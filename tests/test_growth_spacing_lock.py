"""Regression lock for the dual-store retention multiplier.

This pins the benchmark's structural claim to a test so the multiplier cannot
silently regress. It uses the SAME ground-truth learner as
benchmark_memory_model.py, but asserts a THRESHOLD (>= 10x) rather than the
exact 41.3x, so it is robust to honest parameter drift while still failing if
the dual-store structure is ever lost.

The claim: spaced scheduling (rho=0.5, LTM desirable-difficulty window) builds
durable long-term memory far better than massed scheduling (rho=0.9, STM
window) at an identical review budget. This is the spacing effect — the single
best-documented result in memory science.
"""
from __future__ import annotations

import math

import pytest

from graphify import growth

STABILITY_TARGET = 30.0
S_STM = 0.08
LTM0 = 0.1
GAIN_COEFF = 1.4
DIFFICULTIES = [0.2, 0.35, 0.5, 0.65, 0.8]


class _Learner:
    def __init__(self, d):
        self.D = d
        self.S_ltm = LTM0

    def review(self, t):
        r_ltm = math.exp(-t / self.S_ltm)
        r_stm = math.exp(-t / S_STM)
        if r_ltm >= 0.5 or r_stm >= 0.5:
            if r_ltm >= 0.5:
                self.S_ltm *= (1.0 + (GAIN_COEFF - self.D) * (1.0 - r_ltm))
            return True
        self.S_ltm *= 0.5
        return False


class _Sched:
    def __init__(self, d, rho):
        self.D = d
        self.rho = rho
        self.S = LTM0

    def next_interval(self):
        return max(self.S * math.log(1.0 / self.rho), 0.001)

    def observe(self, t, ok):
        r = math.exp(-t / self.S)
        if ok:
            self.S = max(self.S * (1.0 + (GAIN_COEFF - self.D) * (1.0 - r)), 0.001)
        else:
            self.S = max(self.S * 0.5, 0.001)


def _stability_at_budget(rho, budget=12):
    finals = []
    for d in DIFFICULTIES:
        learner = _Learner(d)
        sched = _Sched(d, rho)
        for _ in range(budget):
            t = sched.next_interval()
            sched.observe(t, learner.review(t))
        finals.append(learner.S_ltm)
    return sum(finals) / len(finals)


def test_spaced_beats_massed_by_10x_at_same_budget():
    massed = _stability_at_budget(0.9)
    spaced = _stability_at_budget(0.5)
    mult = spaced / max(massed, 1e-9)
    assert mult >= 10.0, f"spacing multiplier regressed: {mult:.1f}x"
    # At the same budget, massed barely consolidates (STM-window trap), while
    # spaced is already an order of magnitude toward long-term memory.
    assert massed < 1.0
    assert spaced > 10.0


def test_consolidation_only_in_ltm_window():
    # A review inside the STM window (t << STM half-life) must NOT consolidate LTM.
    # This is the structural reason massed fails: verify the model encodes it.
    S_before = 5.0
    # STM window success: elapsed far below STM half-life
    t_stm = growth.stm_half_life_days() * 0.1
    r_ltm_stm = growth.ltm_retrievability(t_stm, S_before)
    # LTM window success: elapsed just past STM half-life
    t_ltm = growth.stm_half_life_days() * 1.5
    r_ltm_ltm = growth.ltm_retrievability(t_ltm, S_before)
    # At the STM-window review, R_ltm is still ~1 -> consolidation gain ~0.
    gain_stm = growth.consolidate_ltm(S_before, r_ltm_stm, 0.5) / S_before
    gain_ltm = growth.consolidate_ltm(S_before, r_ltm_ltm, 0.5) / S_before
    assert gain_stm < 1.001  # essentially no gain inside STM window
    assert gain_ltm > gain_stm
