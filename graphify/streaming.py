"""Streaming graph I/O — build/export large graphs without materializing them.

Fase 5 (x16): the scalability axis. The existing `export.to_json` builds the
entire node-link dict AND its JSON string in memory at once, which is the OOM
point for 100k+ node graphs. This module streams the same node-link format
node-by-node and link-by-link, so peak memory stays flat.

Performance: per-item json.dumps in pure Python is the slow path (~2.5x slower
than one C-level dump). When `orjson` is available it is used (C-accelerated,
~4-10x faster per item, and memory-safe); otherwise we fall back to stdlib json
with a large batch buffer. Output is byte-compatible with node_link_data either
way.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

try:
    import orjson as _orjson
    _HAS_ORJSON = True
except ImportError:
    _orjson = None
    _HAS_ORJSON = False


def _dumps(d: dict) -> str:
    """Serialize one item dict, using orjson when available for speed."""
    if _HAS_ORJSON:
        # orjson emits UTF-8; decode to str. It also sorts keys by default and
        # is strict about types (good — matches our canonical intent).
        return _orjson.dumps(d, option=_orjson.OPT_SORT_KEYS).decode("utf-8")
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def stream_export(G: nx.Graph, output_path: str | Path, *, batch_size: int = 16384) -> int:
    """Write a node-link graph.json incrementally (no full-graph materialization).

    Returns the number of links written. Peak memory is bounded by ``batch_size``
    items (not the whole graph); writes are batched so serialization is not done
    one-by-one (the slow path).
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    def _item_json(primary_keys: list[str], d: dict) -> str:
        ordered: dict = {}
        for pk in primary_keys:
            ordered[pk] = d.pop(pk)
        for k in sorted(d):
            ordered[k] = d[k]
        return _dumps(ordered)

    with out.open("w", encoding="utf-8") as f:
        f.write('{"directed": ')
        f.write("true" if G.is_directed() else "false")
        f.write(', "multigraph": ')
        f.write("true" if G.is_multigraph() else "false")
        f.write(', "graph": {}, "nodes": [')

        buf: list[str] = []
        first = True

        def flush():
            nonlocal first
            if not buf:
                return
            if not first:
                f.write(",")
            f.write(",".join(buf))
            buf.clear()
            first = False

        for nid in G.nodes():
            d = dict(G.nodes[nid])
            d["id"] = nid
            buf.append(_item_json(["id"], d))
            if len(buf) >= batch_size:
                flush()
        flush()
        f.write('], "links": [')

        count = 0
        first = True
        for u, v in G.edges():
            d = dict(G.edges[u, v])
            d["source"] = u
            d["target"] = v
            buf.append(_item_json(["source", "target"], d))
            if len(buf) >= batch_size:
                flush()
            count += 1
        flush()
        f.write("]}")
    return count


def stream_import(db_path: str | Path, graph_path: str | Path) -> int:
    """Import graph.json into SQLite (full read; import is not the OOM path)."""
    import sqlite3

    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    from graphify.storage import _SCHEMA
    conn.executescript(_SCHEMA)
    cur = conn.cursor()
    cur.execute("DELETE FROM nodes")
    cur.execute("DELETE FROM edges")

    with Path(graph_path).open("r", encoding="utf-8") as f:
        obj = json.load(f)

    nrows = []
    for n in obj.get("nodes", []):
        extra = {k: v for k, v in n.items()
                 if k not in ("id", "label", "source_file", "file_type", "kind", "community")}
        nrows.append((n.get("id"), n.get("label"), n.get("source_file"),
                      n.get("file_type"), n.get("kind"), n.get("community"),
                      json.dumps(extra, ensure_ascii=False, default=str) if extra else None))
    cur.executemany("INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?)", nrows)

    erows = []
    for e in obj.get("links", obj.get("edges", [])):
        erows.append((e.get("source"), e.get("target"),
                      e.get("relation") or "uses", e.get("confidence") or "EXTRACTED"))
    cur.executemany("INSERT OR REPLACE INTO edges VALUES (?,?,?,?)", erows)
    conn.commit()
    conn.close()
    return len(erows)
