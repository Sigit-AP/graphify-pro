"""Diff-aware graph analysis (Fase 8, x32).

Compare two graph.json snapshots (e.g. two commits, or before/after a change)
and report what changed — added/removed/changed nodes and edges — plus the
impact of those changes (which existing consumers are now affected by a removed
or changed symbol).

Pure functions, deterministic, no LLM.
"""
from __future__ import annotations

from typing import Any

import networkx as nx


def _node_sig(data: dict) -> tuple:
    """A stable signature of a node's identity-relevant attributes."""
    return (
        data.get("label"),
        data.get("source_file"),
        data.get("file_type"),
        data.get("kind"),
    )


def _edge_sig(data: dict) -> tuple:
    return (
        data.get("source"),
        data.get("target"),
        data.get("relation"),
    )


def diff_graphs(before: nx.Graph, after: nx.Graph) -> dict[str, Any]:
    """Structural diff between two graphs.

    Returns added/removed/changed nodes and edges, keyed by node id / edge key.
    """
    before_nodes = {nid: dict(before.nodes[nid]) for nid in before.nodes()}
    after_nodes = {nid: dict(after.nodes[nid]) for nid in after.nodes()}

    added_nodes = sorted(set(after_nodes) - set(before_nodes))
    removed_nodes = sorted(set(before_nodes) - set(after_nodes))
    changed_nodes = []
    for nid in sorted(set(before_nodes) & set(after_nodes)):
        if _node_sig(before_nodes[nid]) != _node_sig(after_nodes[nid]):
            changed_nodes.append(nid)

    def _edges_keyed(G: nx.Graph) -> dict[tuple, dict]:
        out = {}
        for u, v, d in G.edges(data=True):
            s = d.get("_src", u)
            t = d.get("_tgt", v)
            key = (str(s), str(t), str(d.get("relation") or "uses"))
            out[key] = d
        return out

    before_edges = _edges_keyed(before)
    after_edges = _edges_keyed(after)

    added_edges = [k for k in sorted(after_edges) if k not in before_edges]
    removed_edges = [k for k in sorted(before_edges) if k not in after_edges]

    return {
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "changed_nodes": changed_nodes,
        "added_edges": [list(k) for k in added_edges],
        "removed_edges": [list(k) for k in removed_edges],
        "node_delta": len(after_nodes) - len(before_nodes),
        "edge_delta": len(after_edges) - len(before_edges),
    }


def impact_of_removed(before: nx.Graph, removed_nodes: list[str]) -> dict[str, Any]:
    """Impact of removing nodes: which surviving consumers depended on them.

    Uses the reverse-dependency walk (who called/imported/referenced a removed
    symbol), restricted to nodes that still exist in `after`.
    """
    from graphify.agent_query import impact

    result: dict[str, Any] = {}
    for nid in removed_nodes:
        imp = impact(before, nid)
        # Only count consumers that are NOT themselves removed.
        survivors = [c for c in imp["blast_radius"] if c in before.nodes]
        result[nid] = {
            "direct_consumers": imp["direct_consumers"],
            "transitive_consumers": len(survivors),
            "surviving_consumers": survivors,
        }
    return result
