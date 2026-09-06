"""Agent-native structured query (Fase 7, x25).

The existing query path returns prose subgraph text (good for humans, wasteful
for agents). This module returns strict JSON the way an agent wants it:

  * `consumers(node)` — every node that calls/uses/implements a symbol
  * `impact(node)` — blast radius: consumers + descendants (inheritance)
  * `typed_path(src, dst, relation)` — shortest path restricted to one relation

Deterministic, no LLM. Returns plain dicts (JSON-serializable). This is what
lets an agent ask "who uses X" and get a machine-readable answer instead of
re-parsing prose.
"""
from __future__ import annotations

from typing import Any

import networkx as nx


def _src_tgt(G: nx.Graph, u, v, d: dict) -> tuple[str, str]:
    src = d.get("_src")
    tgt = d.get("_tgt")
    if src is not None and tgt is not None:
        return str(src), str(tgt)
    return str(u), str(v)


def consumers(G: nx.Graph, node: str, relations: set[str] | None = None) -> list[dict[str, Any]]:
    """All nodes that point AT `node` via a directional relation (who depends on it).

    Default relations: calls, uses, imports, imports_from, references, inherits,
    extends, implements, mixes_in.
    """
    rels = relations or {"calls", "uses", "imports", "imports_from", "references",
                         "inherits", "extends", "implements", "mixes_in"}
    out: list[dict[str, Any]] = []
    for u, v, d in G.edges(data=True):
        src, tgt = _src_tgt(G, u, v, d)
        if tgt != node:
            continue
        rel = d.get("relation") or "uses"
        if rel in rels:
            out.append({
                "consumer": src,
                "relation": rel,
                "consumer_label": G.nodes.get(src, {}).get("label", src),
                "source_file": G.nodes.get(src, {}).get("source_file"),
            })
    return out


def impact(G: nx.Graph, node: str) -> dict[str, Any]:
    """Blast radius of a node: direct consumers + transitive consumers (BFS up
    the reverse dependency direction) + inheritance descendants."""
    reverse: dict[str, set[str]] = {}
    deps = {"calls", "uses", "imports", "imports_from", "references",
            "inherits", "extends", "implements", "mixes_in"}
    for u, v, d in G.edges(data=True):
        src, tgt = _src_tgt(G, u, v, d)
        if (d.get("relation") or "uses") in deps:
            reverse.setdefault(tgt, set()).add(src)

    # BFS over reverse adjacency (who depends on me, transitively)
    visited: set[str] = set()
    frontier = {node}
    while frontier:
        nxt: set[str] = set()
        for n in frontier:
            for dep in reverse.get(n, ()):
                if dep not in visited and dep != node:
                    nxt.add(dep)
        visited.update(nxt)
        frontier = nxt

    direct = reverse.get(node, set())
    return {
        "node": node,
        "direct_consumers": len(direct),
        "transitive_consumers": len(visited),
        "blast_radius": sorted(visited),
        "direct_consumer_list": sorted(direct),
    }


def typed_path(G: nx.Graph, src: str, tgt: str, relation: str,
               max_depth: int = 10) -> dict[str, Any]:
    """Shortest path from src to tgt using ONLY edges of the given relation."""
    from collections import deque

    if src == tgt:
        return {"found": True, "path": [src], "length": 0, "relation": relation}

    # Build directed adjacency restricted to `relation`.
    adj: dict[str, list[str]] = {}
    for u, v, d in G.edges(data=True):
        if (d.get("relation") or "") != relation:
            continue
        s, t = _src_tgt(G, u, v, d)
        adj.setdefault(s, []).append(t)

    # BFS shortest path
    q = deque([src])
    prev: dict[str, str | None] = {src: None}
    while q:
        cur = q.popleft()
        if cur == tgt:
            break
        for nxt in adj.get(cur, ()):
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
        if len(prev) > max_depth * 10:
            break  # safety

    if tgt not in prev:
        return {"found": False, "path": [], "length": 0, "relation": relation}

    # Reconstruct path
    path = []
    cur: str | None = tgt
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()
    return {"found": True, "path": path, "length": len(path) - 1, "relation": relation}
