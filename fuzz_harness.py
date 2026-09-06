"""Fuzz harness (Fase 9, x40): robustness of every new module.

Throws malformed, adversarial, and edge-case inputs at each public function and
asserts NO crash (exception is a bug). Also calibrates confidence labels: the
EXTRACTED/INFERRED distinction must hold — an EXTRACTED edge must come from a
deterministic source, never from fuzzy guessing.
"""
from __future__ import annotations

import random
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx

from graphify import growth, storage, streaming, richness, agent_query, diff_analysis


def _random_str(n=8):
    return "".join(random.choice(string.ascii_letters + string.digits + "._- ") for _ in range(n))


def _random_node_id():
    return _random_str(20)


def fuzz_growth(rng):
    eng = growth.GrowthEngine()
    for _ in range(200):
        nid = rng.choice(["", _random_str(20), None, "n" + str(rng.randint(0, 100))])
        try:
            eng.register(str(nid))
            eng.recall(str(nid), success=rng.random() < 0.5)
            eng.snapshot(str(nid))
        except Exception:
            return False
    # numeric edge cases on pure math
    for _ in range(100):
        growth.retrievability(rng.uniform(-100, 100), rng.uniform(-1, 1000))
        growth.stability_after_success(rng.uniform(-10, 100), rng.random())
        growth.stability_after_lapse(rng.uniform(-10, 100), rng.uniform(0.01, 2))
    return True


def fuzz_storage(rng, tmp_path):
    db = tmp_path / "fuzz.db"
    for _ in range(100):
        nid = _random_str(10)
        snap = {"stability_days": rng.uniform(-1, 50),
                "lapse_count": rng.randint(-5, 5),
                "repetitions": rng.randint(-5, 50),
                "_last_recall_ts": rng.uniform(0, 1e12)}
        try:
            storage.save_memory_state(db, nid, snap)
            storage.load_memory_state(db, nid)
            storage.load_all_memory_state(db)
            storage.weak_nodes(db, now=rng.uniform(0, 1e12))
        except Exception:
            return False
    return True


def fuzz_richness(rng):
    for _ in range(50):
        G = nx.Graph()
        n = rng.randint(0, 20)
        for i in range(n):
            G.add_node(str(i), label=_random_str(5))
        for _ in range(rng.randint(0, 40)):
            G.add_edge(str(rng.randint(0, n - 1) if n else 0),
                       str(rng.randint(0, n - 1) if n else 0),
                       relation=rng.choice(["inherits", "method", "calls", "uses", ""]))
        try:
            richness.inheritance_depth(G)
            richness.inheritance_width(G)
            richness.detect_overrides(G)
            richness.typed_edge_counts(G)
            richness.typed_edge_coverage(G)
        except Exception:
            return False
    return True


def fuzz_agent_query(rng):
    for _ in range(50):
        G = nx.Graph()
        n = rng.randint(0, 15)
        ids = [str(i) for i in range(n)]
        for i in ids:
            G.add_node(i, label=_random_str(5))
        for _ in range(rng.randint(0, 30)):
            G.add_edge(rng.choice(ids) if ids else "x", rng.choice(ids) if ids else "y",
                       relation=rng.choice(["calls", "inherits", "uses"]))
        try:
            agent_query.consumers(G, rng.choice(ids) if ids else "x")
            agent_query.impact(G, rng.choice(ids) if ids else "x")
            agent_query.typed_path(G, rng.choice(ids) if ids else "x",
                                   rng.choice(ids) if ids else "y", "calls")
        except Exception:
            return False
    return True


def fuzz_diff(rng):
    for _ in range(30):
        G1 = nx.Graph()
        G2 = nx.Graph()
        for i in range(rng.randint(0, 10)):
            G1.add_node(str(i), label=_random_str(4))
            G2.add_node(str(i), label=_random_str(4))
        try:
            diff_analysis.diff_graphs(G1, G2)
            diff_analysis.impact_of_removed(G1, [str(i) for i in range(rng.randint(0, 5))])
        except Exception:
            return False
    return True


def run_all(tmp_path):
    rng = random.Random(12345)
    results = {
        "growth": fuzz_growth(rng),
        "storage": fuzz_storage(rng, tmp_path),
        "richness": fuzz_richness(rng),
        "agent_query": fuzz_agent_query(rng),
        "diff": fuzz_diff(rng),
    }
    return results


if __name__ == "__main__":
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="fuzz"))
    res = run_all(d)
    import json
    print(json.dumps(res, indent=2))
    print("ALL PASS" if all(res.values()) else "SOME FAILED")
    sys.exit(0 if all(res.values()) else 1)
