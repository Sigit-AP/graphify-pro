"""Benchmark: massed vs spaced scheduling against a ground-truth dual-store
learner. This isolates the SPACING EFFECT — the single largest, best-documented
memory-scheduling principle — and measures it as a real multiplier.

GROUND-TRUTH learner (one item, deterministic):
  - Two traces: STM (S_stm=0.08 day ~2h) and LTM (S_ltm starts 0.1 day), plus a
    fixed per-item difficulty D.
  - recall(t) succeeds if R_stm(t) >= 0.5 OR R_ltm(t) >= 0.5  (joint retrieval).
  - LTM consolidates ONLY on LTM access (R_ltm >= 0.5):
        S_ltm *= 1 + (1.4 - D) * (1 - R_ltm)     [desirable difficulty]
  - STM-only recall gives NO LTM gain (illusion of competence).
  - no recall: lapse, S_ltm *= 0.5.

SCHEDULERS — IDENTICAL information (both know D), IDENTICAL update rule,
differ ONLY in the retention target rho at which they schedule the next review:

  - Massed  (rho=0.9): review while still ~fresh. Short intervals, frequent
    reviews, but each lands in the STM window where LTM gain is ~0.
  - Spaced  (rho=0.5): review at the LTM desirable-difficulty point. Longer
    intervals, each review accesses the LTM trace and consolidates it.

The multiplier is the honest ratio: reviews-to-mastery, and LTM-stability
achieved under a FIXED budget, massed vs spaced. Deterministic and reproducible.
"""
from __future__ import annotations

import math

STABILITY_TARGET = 30.0   # "long-term memory" (days)
S_STM = 0.08              # STM time constant (~2 hours)
LTM0 = 0.1                # true initial LTM stability
REVIEW_BUDGET = 25
DIFFICULTIES = [0.2, 0.35, 0.5, 0.65, 0.8]
GAIN_COEFF = 1.4          # desirable-difficulty ceiling


class GroundTruthLearner:
    def __init__(self, difficulty: float):
        self.D = difficulty
        self.S_ltm = LTM0
        self.reviews = 0
        self.lapses = 0
        self.stm_only = 0

    def ltm(self, t: float) -> float:
        return math.exp(-t / self.S_ltm)

    def stm(self, t: float) -> float:
        return math.exp(-t / S_STM)

    def review(self, t: float) -> bool:
        self.reviews += 1
        R_ltm = self.ltm(t)
        R_stm = self.stm(t)
        if R_ltm >= 0.5 or R_stm >= 0.5:
            if R_ltm >= 0.5:
                self.S_ltm *= (1.0 + (GAIN_COEFF - self.D) * (1.0 - R_ltm))
            else:
                self.stm_only += 1
            return True
        self.lapses += 1
        self.S_ltm *= 0.5
        return False


class Scheduler:
    """Schedule at t*=S·ln(1/rho); consolidate with the same rule as the learner
    (knowing D). Only rho differs between massed and spaced."""

    def __init__(self, difficulty: float, rho: float):
        self.D = difficulty
        self.rho = rho
        self.S = LTM0

    def next_interval(self) -> float:
        return max(self.S * math.log(1.0 / self.rho), 0.001)

    def observe(self, t: float, success: bool) -> None:
        R = math.exp(-t / self.S)
        if success:
            self.S = max(self.S * (1.0 + (GAIN_COEFF - self.D) * (1.0 - R)), 0.001)
        else:
            self.S = max(self.S * 0.5, 0.001)


def reviews_to_mastery(rho: float, d: float, budget: int = REVIEW_BUDGET):
    learner = GroundTruthLearner(d)
    sched = Scheduler(d, rho)
    for _ in range(budget):
        if learner.S_ltm >= STABILITY_TARGET:
            break
        t = sched.next_interval()
        sched.observe(t, learner.review(t))
    return learner.reviews, learner.S_ltm, learner.lapses


def stability_at_budget(rho: float, d: float, budget: int = 12):
    learner = GroundTruthLearner(d)
    sched = Scheduler(d, rho)
    for _ in range(budget):
        t = sched.next_interval()
        sched.observe(t, learner.review(t))
    return learner.S_ltm


def report(rho: float, label: str):
    rows = [reviews_to_mastery(rho, d) for d in DIFFICULTIES]
    reviews = [r for r, s, l in rows]
    finals = [s for r, s, l in rows]
    lapses = [l for r, s, l in rows]
    mastered = sum(1 for s in finals if s >= STABILITY_TARGET)
    avg_r = sum(reviews) / len(reviews)
    avg_s = sum(finals) / len(finals)
    avg_l = sum(lapses) / len(lapses)
    # fixed-budget retention (12 reviews — same budget for both)
    fixed = sum(stability_at_budget(rho, d, 12) for d in DIFFICULTIES) / len(DIFFICULTIES)
    print(f"[{label} (rho={rho})]")
    print(f"  avg reviews to mastery:  {avg_r:.2f}  (fewer = better)")
    print(f"  avg lapses:              {avg_l:.2f}")
    print(f"  mastered (>= {STABILITY_TARGET:.0f}d): {mastered}/{len(DIFFICULTIES)}")
    print(f"  avg LTM stability @ 12 reviews: {fixed:.2f} days")
    return {"avg_reviews": avg_r, "avg_lapses": avg_l, "mastered": mastered,
            "stability_at_12": fixed, "avg_final": avg_s}


if __name__ == "__main__":
    massed = report(0.9, "MASSED (current v2-style, frequent)")
    print()
    spaced = report(0.5, "SPACED  (dual-store, desirable difficulty)")
    print()
    if massed["stability_at_12"] > 0:
        print(f"RETENTION MULTIPLIER (stability @ fixed 12-review budget): "
              f"{spaced['stability_at_12'] / massed['stability_at_12']:.1f}x")
    print(f"REVIEWS-TO-MASTERY RATIO: "
          f"{massed['avg_reviews'] / max(spaced['avg_reviews'], 1):.1f}x fewer reviews")
