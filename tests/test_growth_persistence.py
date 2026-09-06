"""End-to-end test: Growth v2 + SQLite persistence (partial memory, long/short term)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graphify import growth, storage


def test_save_load_roundtrip(tmp_path):
    db = tmp_path / "g.db"
    eng = growth.GrowthEngine()
    eng.register("alpha")
    for i in range(4):
        eng.items["alpha"].last_recall_ts -= (i + 1) * 86400.0
        snap = eng.recall("alpha", success=True)
    storage.save_memory_state(db, "alpha", snap)

    loaded = storage.load_memory_state(db, "alpha")
    assert loaded is not None
    assert loaded["stability_days"] > 1.0
    assert loaded["repetitions"] == 4
    assert "lapse_count" in loaded


def test_load_all_survives_restart(tmp_path):
    db = tmp_path / "g.db"
    eng = growth.GrowthEngine()
    eng.register("keep_me")
    eng.items["keep_me"].stability = 12.0
    eng.items["keep_me"].repetitions = 6
    storage.save_memory_state(db, "keep_me", eng.snapshot("keep_me"))

    # Fresh engine, same db -> long-term memory survives.
    states = storage.load_all_memory_state(db)
    eng2 = growth.GrowthEngine()
    n = eng2.restore(states)
    assert n == 1
    assert eng2.snapshot("keep_me")["stability_days"] == 12.0


def test_weak_nodes_time_aware(tmp_path):
    db = tmp_path / "g.db"
    now = time.time()
    # node A: recalled long ago (decayed) -> weak NOW
    storage.save_memory_state(db, "A", {"stability_days": 1.0, "lapse_count": 0,
                                        "repetitions": 1, "_last_recall_ts": now - 30 * 86400.0})
    # node B: recalled just now -> strong NOW
    storage.save_memory_state(db, "B", {"stability_days": 1.0, "lapse_count": 0,
                                        "repetitions": 1, "_last_recall_ts": now})
    weak = storage.weak_nodes(db, limit=5, now=now)
    assert weak[0]["node_id"] == "A"  # decayed node is weaker than fresh one
    assert weak[0]["retrievability"] < 0.1


def test_record_query_recalls_persists(tmp_path):
    db = tmp_path / "g.db"
    n = growth.record_query_recalls(str(db), ["seed1", "seed2"])
    assert n == 2
    # both nodes now have a persisted state with 1 repetition
    assert storage.load_memory_state(db, "seed1")["repetitions"] == 1
    assert storage.load_memory_state(db, "seed2")["repetitions"] == 1
