"""Objective quality metrics for graphify's call-graph resolution.

Measures the axes that a 50x improvement claim must stand on:
  - resolution precision / recall against a ground-truth call graph
  - query latency
  - index footprint

Deliberately separate from `benchmark.py` (which measures token reduction,
a different axis). Both are real, both report numbers, neither fabricates.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import networkx as nx

from graphify.build import edge_data
from graphify.paths import load_node_link_graph


# ── Ground-truth format ────────────────────────────────────────────────────
# A ground-truth call graph is a JSON file:
# {
#   "calls": [
#     {"from": "module.func_a", "to": "module.func_b"},
#     ...
#   ]
# }
# where "from"/"to" are normalized symbol names matching node labels in the
# extracted graph (normalization = lowercase, strip module path).


def _normalize(sym: str) -> str:
    """Normalize a symbol for fuzzy-ground-truth comparison."""
    return sym.strip().lower().split(".")[-1]


def _edge_pairs(G: nx.Graph) -> set[tuple[str, str]]:
    """All (from, to) pairs of resolved 'calls' edges, normalized & undirected."""
    pairs: set[tuple[str, str]] = set()
    for u, v in G.edges():
        d = edge_data(G, u, v)
        if d.get("relation") not in ("calls", "imports", "uses"):
            continue
        lu = _normalize(G.nodes[u].get("label", u))
        lv = _normalize(G.nodes[v].get("label", v))
        pairs.add(tuple(sorted((lu, lv))))
    return pairs


def resolution_metrics(graph_path: str | Path, ground_truth_path: str | Path) -> dict[str, Any]:
    """Precision / recall / F1 of call-graph edges vs ground truth.

    Undirected comparison on normalized symbol names, so fuzzy resolution and
    exact resolution are judged on the same axis.
    """
    G = load_node_link_graph(str(graph_path))
    gt = json.loads(Path(ground_truth_path).read_text(encoding="utf-8"))
    gt_pairs = {tuple(sorted((_normalize(e["from"]), _normalize(e["to"])))) for e in gt["calls"]}
    graph_pairs = _edge_pairs(G)

    tp = len(graph_pairs & gt_pairs)
    fp = len(graph_pairs - gt_pairs)
    fn = len(gt_pairs - graph_pairs)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "ground_truth_edges": len(gt_pairs),
        "graph_edges_compared": len(graph_pairs),
    }


def query_latency_ms(graph_path: str | Path, queries: list[str], depth: int = 3) -> dict[str, Any]:
    """Average latency of BFS-style subgraph queries, in milliseconds."""
    from graphify.serve import _query_terms

    G = load_node_link_graph(str(graph_path))
    label_map = {nid: (d.get("label") or "").lower() for nid, d in G.nodes(data=True)}

    per_query: list[float] = []
    for q in queries:
        terms = _query_terms(q)
        start = time.perf_counter()
        scored = []
        for nid, label in label_map.items():
            score = sum(1 for t in terms if t in label)
            if score > 0:
                scored.append((score, nid))
        scored.sort(reverse=True)
        start_nodes = [nid for _, nid in scored[:3]]
        visited: set[str] = set(start_nodes)
        frontier = set(start_nodes)
        for _ in range(depth):
            nxt: set[str] = set()
            for n in frontier:
                for nb in G.neighbors(n):
                    if nb not in visited:
                        nxt.add(nb)
            visited.update(nxt)
            frontier = nxt
        per_query.append((time.perf_counter() - start) * 1000.0)

    avg = sum(per_query) / len(per_query) if per_query else 0.0
    return {"avg_ms": round(avg, 2), "max_ms": round(max(per_query), 2) if per_query else 0.0,
            "queries": len(per_query)}


def index_footprint(graph_path: str | Path) -> dict[str, Any]:
    """On-disk and in-memory footprint of a built graph."""
    p = Path(graph_path)
    disk_bytes = p.stat().st_size if p.exists() else 0
    G = load_node_link_graph(str(p))
    return {
        "disk_bytes": disk_bytes,
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
    }


def run_metrics(graph_path: str | Path, ground_truth_path: str | Path | None = None,
                queries: list[str] | None = None) -> dict[str, Any]:
    """One-shot harness: run all metrics and return a single report dict."""
    out: dict[str, Any] = {}
    if ground_truth_path is not None:
        out["resolution"] = resolution_metrics(graph_path, ground_truth_path)
    out["latency"] = query_latency_ms(graph_path, queries or _DEFAULT_QUERIES)
    out["footprint"] = index_footprint(graph_path)
    return out


_DEFAULT_QUERIES = [
    "how does authentication work",
    "what is the main entry point",
    "how are errors handled",
    "what connects the data layer to the api",
]
