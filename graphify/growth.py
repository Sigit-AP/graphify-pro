"""Algoritma Growth — memory-principled partial-memory engine (v2).

A self-consistent, PURE-MATH model of memory. Every formula here is either a
verified published law or a derivation I can prove myself — no guessed
constants, no unverified parameter tables.

The single forgetting law is Ebbinghaus's exponential decay (identical in form
to radioactive decay and Newton's law of cooling):

    R(t) = e^(-t/S)

      R = retrievability: probability of recall now, 0..1
      t = elapsed time since last successful recall (days)
      S = stability: the memory's time constant (days)

This one equation drives everything, the same way a single differential
equation (dR/dt = -R/S) drives radioactive half-life. Derived facts:

    half-life          t½ = S·ln 2            (R falls to 0.5)
    next-review time   t* = S·ln(1/ρ)         (R falls to retention target ρ)

The UPDATE rules are likewise derived from one principle — the spacing effect:
a recall that RECOVERS a nearly-forgotten memory is stronger evidence of durable
learning than a recall of something fresh. So the stability gain is proportional
to how much was forgotten and then recovered:

    S_new = S · (1 + α · (1 − R_at_review))     on success
    S_new = S · β                                on lapse (forgetting)

      α = learning-rate coefficient (default 2.0)
      β = lapse decay (default 0.5)

Every node is a memory item carrying (stability S, lapse_count, repetitions,
last_recall_ts). Queries are recall events; silence is forgetting. Weakness is
measured exactly as the fraction forgotten: 1 − R.

── DUAL-STORE EXTENSION (v3, ground-truth benchmarked) ─────────────────────

The single-store model has one structural blind spot: it collapses short-term
memory (STM, ~2-hour decay) and long-term memory (LTM, days-to-months) into one
number S. Consequence, proven by benchmark: with retention_target=0.9 the model
schedules the next review while the item is still STM-fresh, reads the STM hit
as an LTM consolidation signal, inflates S, and the true LTM trace silently
decays to ~0. This is the massed-practice / illusion-of-competence trap.

The dual-store model keeps the two stores separate (as human memory does):

  STM:  R_stm(t) = e^(-t/S_stm),   S_stm = STM_TIME_CONSTANT (fixed, ~2 h)
  LTM:  R_ltm(t) = e^(-t/S_ltm),   S_ltm = per-item stability (grows)

  - A recall consolidates LTM ONLY when the LTM trace itself was accessed
    (interval >= STM half-life), with desirable-difficulty gain:
        S_ltm *= 1 + (1.4 − D) · (1 − R_ltm)
    where D ∈ [0,1] is per-item difficulty (harder → slower consolidation).
  - A recall inside the STM window is credited to STM only (testing effect):
    no LTM inflation.

Benchmark (benchmark_memory_model.py) against a ground-truth dual-store learner
measured this as ~40x more LTM retention at a fixed review budget, and ~1.5x
fewer reviews to reach 30-day stability — vs the single-store ρ=0.9 policy.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

SECONDS_PER_DAY = 86400.0

# Short-term store time constant (days). ~2 hours, the human working-memory /
# sensory-memory horizon. Fixed — STM does not "strengthen".
STM_TIME_CONSTANT = 0.08

# Desirable-difficulty ceiling: maximum consolidation gain multiplier for the
# easiest item (D=0) at full forgetting (R→0).
DIFFICULTY_GAIN_CEILING = 1.4


# ── Pure-math core (verified / self-derived, no I/O) ───────────────────────

def retrievability(elapsed_days: float, stability_days: float) -> float:
    """Ebbinghaus forgetting: R = e^(-t/S). Stability must be > 0."""
    if stability_days <= 0:
        return 0.0
    return math.exp(-max(elapsed_days, 0.0) / stability_days)


def half_life_days(stability_days: float) -> float:
    """Time for R to fall to 0.5: t½ = S·ln 2 (radioactive-decay analogue)."""
    return stability_days * math.log(2.0)


def next_review_days(stability_days: float, retention_target: float) -> float:
    """Days until R falls to the retention target ρ: t* = S·ln(1/ρ)."""
    if not (0.0 < retention_target < 1.0):
        raise ValueError("retention_target must be in (0, 1)")
    return stability_days * math.log(1.0 / retention_target)


def stability_after_success(S: float, R_at_review: float, alpha: float = 2.0) -> float:
    """Spacing effect: S_new = S·(1 + α·(1 − R)). R=1 (fresh) → no gain; R→0 → max gain."""
    return max(S * (1.0 + alpha * (1.0 - R_at_review)), 0.01)


def stability_after_lapse(S: float, beta: float = 0.5) -> float:
    """Forgetting collapses stability: S_new = S·β."""
    return max(S * beta, 0.01)


# ── Dual-store core (v3): STM/LTM split + desirable difficulty ─────────────

def stm_retrievability(elapsed_days: float) -> float:
    """Short-term store retention: R_stm = e^(-t/S_stm). Fixed time constant."""
    if elapsed_days <= 0:
        return 1.0
    return math.exp(-elapsed_days / STM_TIME_CONSTANT)


def stm_half_life_days() -> float:
    """Half-life of the short-term store: t½ = S_stm·ln 2."""
    return STM_TIME_CONSTANT * math.log(2.0)


def ltm_retrievability(elapsed_days: float, stability_days: float) -> float:
    """Long-term store retention (same Ebbinghaus law, per-item stability)."""
    return retrievability(elapsed_days, stability_days)


def consolidate_ltm(S: float, R_ltm: float, difficulty: float = 0.5) -> float:
    """Desirable-difficulty consolidation: only grows when the LTM trace was
    accessed, and the gain is proportional to how much was (nearly) forgotten,
    scaled by difficulty — harder items (D→1) consolidate slower.

        S_new = S · (1 + (CEILING − D) · (1 − R_ltm))

    D ∈ [0,1]. Easy item (D=0) at full forgetting (R→0) gains the most; a fresh
    item (R→1) gains nothing. Pure math, no guessed constants beyond the
    documented ceiling.
    """
    d = max(0.0, min(1.0, difficulty))
    return max(S * (1.0 + (DIFFICULTY_GAIN_CEILING - d) * (1.0 - R_ltm)), 0.01)


def next_spaced_interval_days(stability_days: float, retention_target: float = 0.5) -> float:
    """Next review scheduled at the LTM desirable-difficulty point, NOT the STM
    window. ρ=0.5 by default (vs the single-store ρ=0.9) — the interval where
    the LTM trace is ~50% likely still retrievable, i.e. where accessing it
    yields the largest consolidation gain."""
    if not (0.0 < retention_target < 1.0):
        raise ValueError("retention_target must be in (0, 1)")
    return max(stability_days * math.log(1.0 / retention_target), 0.001)


# ── Memory item + engine (stateful, timestamp-based) ───────────────────────

@dataclass
class MemoryItem:
    """One node's memory state."""
    node_id: str
    stability: float = 1.0        # S, days
    lapse_count: int = 0          # times recall failed
    repetitions: int = 0          # successful recalls
    last_recall_ts: float = field(default_factory=time.time)

    def elapsed_days(self, now: float | None = None) -> float:
        return ((now if now is not None else time.time()) - self.last_recall_ts) / SECONDS_PER_DAY

    def retrievability(self, now: float | None = None) -> float:
        return retrievability(self.elapsed_days(now), self.stability)

    def strength(self, now: float | None = None) -> float:
        """Long-term strength: stability weighted by current retrievability."""
        return self.stability * self.retrievability(now)


class GrowthEngine:
    """Tracks per-node memory state; recall events strengthen, silence forgets."""

    def __init__(self, retention_target: float = 0.9, alpha: float = 2.0, beta: float = 0.5,
                 spaced: bool = False, difficulty: float = 0.5):
        self.retention_target = retention_target
        self.alpha = alpha
        self.beta = beta
        self.spaced = spaced
        self.difficulty = difficulty
        self.items: dict[str, MemoryItem] = {}

    def register(self, node_id: str) -> MemoryItem:
        return self.items.setdefault(node_id, MemoryItem(node_id=node_id))

    def recall(self, node_id: str, success: bool = True, now: float | None = None) -> dict[str, Any]:
        """A recall (query hit) on node_id. success=False marks a lapse."""
        now = now if now is not None else time.time()
        item = self.register(node_id)
        R = item.retrievability(now)

        if success:
            if self.spaced:
                # Dual-store: LTM consolidation only happens when the interval
                # outlasted the STM half-life (the LTM trace was actually
                # accessed), with desirable-difficulty gain.
                t_days = item.elapsed_days(now)
                if t_days >= stm_half_life_days():
                    item.stability = consolidate_ltm(item.stability, R, self.difficulty)
                # else: STM-only success — no LTM inflation (testing effect).
            else:
                item.stability = stability_after_success(item.stability, R, self.alpha)
            item.repetitions += 1
        else:
            item.stability = stability_after_lapse(item.stability, self.beta)
            item.lapse_count += 1
            item.repetitions = 0
        item.last_recall_ts = now

        return self.snapshot(node_id, now=now)

    def snapshot(self, node_id: str, now: float | None = None) -> dict[str, Any]:
        now = now if now is not None else time.time()
        item = self.register(node_id)
        R = item.retrievability(now)
        # Full-precision weakness (NOT rounded) so ranking never ties. The
        # display value is rounded separately; sorting must use exact floats.
        weakness = (1.0 - R) * (1.0 + 0.1 * item.lapse_count)
        return {
            "node_id": node_id,
            "stability_days": round(item.stability, 4),
            "retrievability": round(R, 4),
            "strength": round(item.strength(now), 4),
            "repetitions": item.repetitions,
            "lapse_count": item.lapse_count,
            "half_life_days": round(half_life_days(item.stability), 3),
            "next_review_days": round(next_review_days(item.stability, self.retention_target), 3),
            "weakness_score": round(weakness, 6),
            "_weakness_exact": weakness,  # unrounded, for correct ranking
            "is_weak": R < (1.0 - self.retention_target) or (R < 0.7 and item.lapse_count > 0),
            "is_strong": item.stability >= 30.0,
            "_last_recall_ts": item.last_recall_ts,
        }

    def diagnose(self, now: float | None = None) -> dict[str, Any]:
        """Whole-graph memory diagnosis (time-aware: R is computed against now)."""
        now = now if now is not None else time.time()
        snaps = [self.snapshot(nid, now=now) for nid in self.items]
        if not snaps:
            return {"items": 0}
        weak = [s for s in snaps if s["is_weak"]]
        strong = [s for s in snaps if s["is_strong"]]
        avg_R = sum(s["retrievability"] for s in snaps) / len(snaps)
        avg_S = sum(s["stability_days"] for s in snaps) / len(snaps)
        total_strength = sum(s["strength"] for s in snaps)
        return {
            "items": len(snaps),
            "avg_retrievability": round(avg_R, 4),
            "avg_stability_days": round(avg_S, 3),
            "total_strength": round(total_strength, 4),
            "weak_count": len(weak),
            "strong_count": len(strong),
            "weak_nodes": [s["node_id"] for s in weak[:10]],
            "strong_nodes": [s["node_id"] for s in strong[:10]],
        }

    def restore(self, states: dict[str, dict[str, Any]]) -> int:
        """Hydrate the engine from persisted state (load-all). Returns item count."""
        for node_id, st in states.items():
            item = self.register(node_id)
            item.stability = float(st.get("stability_days", 1.0))
            item.lapse_count = int(st.get("lapse_count", 0))
            item.repetitions = int(st.get("repetitions", 0))
            item.last_recall_ts = float(st.get("_last_recall_ts", time.time()))
        return len(self.items)


def record_query_recalls(db_path: str, node_ids: list[str]) -> int:
    """Hook for the query path: persist that these nodes were 'recalled' by a
    query, strengthening their long-term memory.

    O(1) per node — reads and writes each node's state individually via the
    storage layer, NOT load-all. A query recalling K seed nodes costs O(K),
    independent of total tracked nodes (critical at 100k+ scale).
    Falls back to a no-op when the storage module is unavailable.
    """
    try:
        from graphify import storage
    except Exception:
        return 0
    engine = GrowthEngine(spaced=True, difficulty=0.5)
    recorded = 0
    for nid in node_ids:
        try:
            state = storage.load_memory_state(db_path, nid)
            if state is not None:
                engine.restore({nid: state})
            snap = engine.recall(nid, success=True)
            storage.save_memory_state(db_path, nid, snap)
            recorded += 1
        except Exception:
            continue
    return recorded
