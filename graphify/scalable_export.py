"""Scalable export with automatic threshold (Fase 10: closes Fase 5 gaps).

The honest trade-off from the x16 benchmark: streaming export is ~16x more
memory-efficient but ~2.5x slower per-item (json.dumps per node). The right
engineering answer is a THRESHOLD: small graphs use the fast materialized path
(node_link_data), large graphs use the memory-bounded streaming path.

This module exposes `export_auto()` — one entry point that picks the correct
path by graph size, so callers get the best of both without thinking about it.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph


# Default: graphs above this many nodes use streaming (memory-bounded). Below
# it, the materialized path is faster and the memory cost is negligible.
DEFAULT_THRESHOLD = 20_000


def export_auto(G: nx.Graph, output_path: str | Path,
                threshold: int = DEFAULT_THRESHOLD) -> int:
    """Write graph.json, choosing materialized vs streaming by node count.

    Returns the number of links written. Output is byte-compatible either way
    (same node-link shape), so downstream readers cannot tell the difference.
    """
    from graphify.streaming import stream_export

    if G.number_of_nodes() <= threshold:
        # Fast path: materialized node_link_data (no per-item overhead).
        data = json_graph.node_link_data(G, edges="links")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        import json
        out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        return G.number_of_edges()
    # Memory-bounded path for large graphs.
    return stream_export(G, output_path)
