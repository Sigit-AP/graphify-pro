"""Edge-type richness analytics (Fase 6, x20).

Graphify already EXTRACTS typed edges (inherits/extends/implements/mixes_in/
calls/imports/contains/method). This module adds the ANALYTICS layer that turns
those typed edges into measurable signal:

  * inheritance depth (longest extends/inherits chain)
  * inheritance width (max children of any class)
  * override detection (a method that redefines a same-named method on an ancestor)
  * typed-edge coverage (what fraction of edges carry a specific relation)

Pure functions over NetworkX graphs (or node/edge dicts), no I/O.
"""
from __future__ import annotations

from typing import Any

import networkx as nx

_SUPERTYPE_RELATIONS = {"inherits", "extends", "implements", "mixes_in"}


def _directed_endpoints(G: nx.Graph, u, v, d: dict) -> tuple[str, str]:
    """True (source, target) of a directional edge.

    Undirected NetworkX storage canonicalizes endpoint order, so direction is
    stashed in `_src`/`_tgt` (build path, #563). Fall back to iteration order
    only when those markers are absent.
    """
    src = d.get("_src")
    tgt = d.get("_tgt")
    if src is not None and tgt is not None:
        return str(src), str(tgt)
    return str(u), str(v)


def typed_edge_counts(G: nx.Graph) -> dict[str, int]:
    """Count edges per relation type."""
    counts: dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        rel = d.get("relation") or "uses"
        counts[rel] = counts.get(rel, 0) + 1
    return counts


def typed_edge_coverage(G: nx.Graph) -> float:
    """Fraction of edges that carry a non-generic relation (specific beats generic)."""
    total = G.number_of_edges()
    if not total:
        return 0.0
    specific = 0
    for _, _, d in G.edges(data=True):
        if (d.get("relation") or "uses") not in ("references", "uses", "mentions"):
            specific += 1
    return specific / total


def inheritance_depth(G: nx.Graph) -> dict[str, Any]:
    """Longest supertype chain (max depth) over inherits/extends/implements edges.

    Returns depth (0 = no inheritance), the longest chain, and per-node depth.
    """
    # Build child -> parent adjacency for supertype relations.
    parents: dict[str, set[str]] = {}
    for u, v, d in G.edges(data=True):
        if (d.get("relation") or "") in _SUPERTYPE_RELATIONS:
            child, parent = _directed_endpoints(G, u, v, d)
            parents.setdefault(child, set()).add(parent)

    depth_of: dict[str, int] = {}

    def dfs(node: str, visiting: set[str]) -> int:
        if node in depth_of:
            return depth_of[node]
        if node in visiting:
            return 0  # cycle guard
        visiting.add(node)
        best = 0
        for p in parents.get(node, ()):
            best = max(best, 1 + dfs(p, visiting))
        visiting.discard(node)
        depth_of[node] = best
        return best

    for n in parents:
        dfs(n, set())

    max_depth = max(depth_of.values()) if depth_of else 0
    return {
        "max_depth": max_depth,
        "nodes_with_supertypes": len(parents),
        "per_node_depth": depth_of,
    }


def inheritance_width(G: nx.Graph) -> dict[str, Any]:
    """Max number of direct children any single class has."""
    child_counts: dict[str, int] = {}
    for u, v, d in G.edges(data=True):
        if (d.get("relation") or "") in _SUPERTYPE_RELATIONS:
            child, parent = _directed_endpoints(G, u, v, d)
            child_counts[parent] = child_counts.get(parent, 0) + 1
    max_width = max(child_counts.values()) if child_counts else 0
    return {
        "max_width": max_width,
        "bases_with_children": len(child_counts),
        "per_base_children": child_counts,
    }


def detect_overrides(G: nx.Graph) -> list[dict[str, str]]:
    """Find methods that redefine a same-named method on an ancestor (override).

    Returns list of {subclass_method, ancestor_method, class_pair}.
    """
    # Build method index: class -> set of NORMALIZED method names (labels), and
    # keep a node-id map so an override can report which node redefines which.
    class_methods: dict[str, set[str]] = {}
    method_label_node: dict[tuple[str, str], str] = {}  # (class, label) -> node id
    for u, v, d in G.edges(data=True):
        if (d.get("relation") or "") == "method":
            owner, method = _directed_endpoints(G, u, v, d)
            label = str(G.nodes.get(method, {}).get("label", method))
            norm = label.strip(".").strip("()").lower()
            class_methods.setdefault(owner, set()).add(norm)
            method_label_node[(owner, norm)] = method

    # Supertype adjacency (child -> parent).
    parents: dict[str, set[str]] = {}
    for u, v, d in G.edges(data=True):
        if (d.get("relation") or "") in _SUPERTYPE_RELATIONS:
            child, parent = _directed_endpoints(G, u, v, d)
            parents.setdefault(child, set()).add(parent)

    overrides: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for child, ps in parents.items():
        cmethods = class_methods.get(child, set())
        for p in ps:
            pmethods = class_methods.get(p, set())
            for shared in cmethods & pmethods:
                key = (child, p, shared)
                if key in seen:
                    continue
                seen.add(key)
                overrides.append({
                    "subclass": child,
                    "ancestor": p,
                    "method": method_label_node.get((child, shared), shared),
                })
    return overrides
