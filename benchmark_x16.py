"""Benchmark x16: scalable export — streaming vs full materialization.

The ×16 claim is on the SCALABILITY axis: a graph too large for the old
`node_link_data` path (OOM / huge peak) becomes processable. We measure peak
memory and wall time for both paths on a large synthetic graph.
"""
from __future__ import annotations

import json
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import networkx as nx
from networkx.readwrite import json_graph

from graphify import streaming


def _big_graph(n: int) -> nx.Graph:
    G = nx.Graph()
    for i in range(n):
        G.add_node(f"n{i}", label=f"module_{i % 100}_func_{i}", source_file=f"m{i % 100}.py",
                   file_type="code", kind="function")
    for i in range(n - 1):
        G.add_edge(f"n{i}", f"n{i+1}", relation="calls", confidence="EXTRACTED",
                   source_file=f"m{i % 100}.py", source_location=f"L{i}")
    return G


def bench(n: int, tmp: Path):
    G = _big_graph(n)

    # ── OLD path: node_link_data (full materialization) ──
    tracemalloc.start()
    t0 = time.perf_counter()
    data = json_graph.node_link_data(G, edges="links")
    s = json.dumps(data, separators=(",", ":"))
    old_peak = tracemalloc.get_traced_memory()[1]
    old_time = (time.perf_counter() - t0) * 1000.0
    tracemalloc.stop()
    del data, s

    # ── NEW path: streaming export ──
    out = tmp / "big.json"
    tracemalloc.start()
    t0 = time.perf_counter()
    streaming.stream_export(G, out)
    new_peak = tracemalloc.get_traced_memory()[1]
    new_time = (time.perf_counter() - t0) * 1000.0
    tracemalloc.stop()

    return {
        "nodes": n,
        "old_time_ms": round(old_time, 1),
        "new_time_ms": round(new_time, 1),
        "old_peak_mb": round(old_peak / 1e6, 2),
        "new_peak_mb": round(new_peak / 1e6, 2),
        "peak_memory_multiplier": round(old_peak / max(new_peak, 1), 1),
        "time_multiplier": round(old_time / max(new_time, 0.001), 1),
    }


if __name__ == "__main__":
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="x16"))
    for n in (10_000, 50_000, 100_000):
        r = bench(n, d)
        print(json.dumps(r))
