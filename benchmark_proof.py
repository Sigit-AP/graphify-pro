"""Benchmark pembuktian label x2..x12 — angka nyata before/after per fase.

Setiap fase diukur pada sumbu objektif. 'before' = perilaku baseline (resolver
lama / load-penuh / rebuild-penuh); 'after' = kode yang sudah saya bangun.
Output hanya angka dari run nyata, tidak ada yang dikarang.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def build_corpus(n_modules: int = 20) -> Path:
    """Synthetic Python project: N modules, each 1 class with 2 methods;
    main.py calls an instance method on each imported class."""
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="gfbench"))
    pkg = d / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for i in range(n_modules):
        (pkg / f"m{i}.py").write_text(
            f"class C{i}:\n    def run(self):\n        return {i}\n"
            f"    def stop(self):\n        return None\n"
        )
    lines = [f"from pkg.m{i} import C{i}" for i in range(n_modules)]
    lines += ["", "def main():", "    total = 0"]
    for i in range(n_modules):
        lines.append(f"    o{i} = C{i}()")
        lines.append(f"    total += o{i}.run()")
    lines.append("    return total")
    (pkg / "main.py").write_text("\n".join(lines))
    return d


def measure_member_calls(corpus: Path):
    """Fase 3: instance member-call edges resolved, baseline vs jedi."""
    from graphify.extract import extract
    from graphify import lsp_resolution

    files = sorted((corpus / "pkg").glob("*.py"))

    # AFTER: jedi active
    r_after = extract(files, root=corpus)
    jedi_edges = [e for e in r_after.get("edges", [])
                  if (e.get("metadata") or {}).get("resolver") == "jedi_lsp"]

    # BEFORE: jedi disabled (the shared resolver skips instance calls)
    real_check = lsp_resolution._jedi_available
    lsp_resolution._jedi_available = lambda: False
    try:
        r_before = extract(files, root=corpus)
    finally:
        lsp_resolution._jedi_available = real_check
    before_edges = [e for e in r_before.get("edges", [])
                    if (e.get("metadata") or {}).get("resolver") == "jedi_lsp"]

    return {
        "instance_member_call_edges_before": len(before_edges),
        "instance_member_call_edges_after": len(jedi_edges),
        "total_call_sites": len([l for l in (corpus/"pkg"/"main.py").read_text().splitlines()
                                 if ".run()" in l]),
    }


def measure_query(corpus: Path, graph_path: str):
    """Fase 2: query latency — full-graph load+scan vs SQLite lookup."""
    from graphify.paths import load_node_link_graph
    from graphify import storage

    # BEFORE: load full graph + linear label scan (what a naive consumer does)
    t0 = time.perf_counter()
    G = load_node_link_graph(graph_path)
    hits_before = 0
    for nid, d in G.nodes(data=True):
        if "run" in str(d.get("label", "")).lower():
            hits_before += 1
    load_ms = (time.perf_counter() - t0) * 1000.0

    # AFTER: SQLite lookup
    db = str(Path(graph_path).with_suffix(".bench.db"))
    storage.import_graph(db, graph_path)
    t0 = time.perf_counter()
    hits_after = storage.lookup(db, "run", limit=500)
    sql_ms = (time.perf_counter() - t0) * 1000.0

    return {"full_load_scan_ms": round(load_ms, 2),
            "sqlite_lookup_ms": round(sql_ms, 2),
            "hits_full_scan": hits_before,
            "hits_sqlite": len(hits_after)}


def measure_incremental(corpus: Path):
    """Fase 2: incremental — re-extract 1 changed file vs full re-extract."""
    from graphify.extract import extract

    files = sorted((corpus / "pkg").glob("*.py"))
    t0 = time.perf_counter()
    extract(files, root=corpus)  # full
    full_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    extract([corpus / "pkg" / "m0.py"], root=corpus)  # single changed file
    single_ms = (time.perf_counter() - t0) * 1000.0

    return {"full_extract_ms": round(full_ms, 2),
            "single_file_extract_ms": round(single_ms, 2),
            "total_files": len(files)}


def measure_growth_precision():
    """Fase 4: weakness ranking precision — decayed nodes ranked first."""
    from graphify import growth
    import time as _time
    now = _time.time()
    eng = growth.GrowthEngine()
    # 10 nodes: node i decayed i*10 days ago (larger i = more decayed)
    for i in range(10):
        nid = f"n{i}"
        eng.register(nid)
        eng.items[nid].stability = 10.0
        eng.items[nid].last_recall_ts = now - i * 10 * 86400.0
    snaps = [eng.snapshot(f"n{i}", now=now) for i in range(10)]
    # correct: n9 (most decayed) should have highest weakness_score
    snaps_sorted = sorted(snaps, key=lambda s: s["weakness_score"], reverse=True)
    correct_top = snaps_sorted[0]["node_id"] == "n9"
    correct_order = all(
        snaps_sorted[i]["node_id"] == f"n{9 - i}" for i in range(10))
    return {"correct_top": correct_top, "correct_full_order": correct_order,
            "weakness_scores": [s["weakness_score"] for s in snaps_sorted]}


def main():
    import tempfile
    corpus = build_corpus(20)

    # Build a graph once for query measurement
    from graphify.extract import extract
    files = sorted((corpus / "pkg").glob("*.py"))
    r = extract(files, root=corpus)
    import networkx as nx
    from graphify.paths import write_json_atomic
    # build node-link graph.json
    G = nx.Graph()
    for n in r.get("nodes", []):
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in r.get("edges", []):
        G.add_edge(e["source"], e["target"], **{k: v for k, v in e.items()
                                                 if k not in ("source", "target")})
    data = nx.node_link_data(G)
    gp = corpus / "graph.json"
    write_json_atomic(gp, data)

    mc = measure_member_calls(corpus)
    q = measure_query(corpus, str(gp))
    inc = measure_incremental(corpus)
    gr = measure_growth_precision()

    report = {
        "fase3_member_calls": mc,
        "fase2_query": q,
        "fase2_incremental": inc,
        "fase4_growth_precision": gr,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
