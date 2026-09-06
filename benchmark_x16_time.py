"""Benchmark x16 time-only (no tracemalloc, fair wall-clock) + memory."""
from __future__ import annotations
import json, sys, time, tracemalloc
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import networkx as nx
from networkx.readwrite import json_graph
from graphify import streaming

def _big(n):
    G = nx.Graph()
    for i in range(n):
        G.add_node(f"n{i}", label=f"module_{i%100}_func_{i}", source_file=f"m{i%100}.py", file_type="code", kind="function")
    for i in range(n-1):
        G.add_edge(f"n{i}", f"n{i+1}", relation="calls", confidence="EXTRACTED", source_location=f"L{i}")
    return G

for n in (100_000, 200_000):
    G = _big(n)
    # OLD: pure time
    t0=time.perf_counter(); data=json_graph.node_link_data(G, edges="links"); s=json.dumps(data, separators=(",",":")); old_t=(time.perf_counter()-t0)*1000
    del data, s
    # NEW: pure time
    out=Path(f"/tmp/x16_{n}.json")
    t0=time.perf_counter(); streaming.stream_export(G, out, batch_size=2048); new_t=(time.perf_counter()-t0)*1000
    print(json.dumps({"nodes":n,"old_ms":round(old_t,1),"new_ms":round(new_t,1),"time_mult":round(old_t/new_t,2)}))
