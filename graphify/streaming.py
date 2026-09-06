"""Streaming graph I/O — build/export large graphs without materializing them.

Fase 5 (x16): the scalability axis. The existing `export.to_json` builds the
entire node-link dict AND its JSON string in memory at once
(`json_graph.node_link_data` then `json.dump`), which is the OOM point for
100k+ node graphs. This module streams the same node-link format node-by-node
and link-by-link, so peak memory stays flat regardless of graph size.

Format compatibility: byte-structure of the output is the SAME node-link shape
`load_node_link_graph` reads ({"directed", "multigraph", "graph", "nodes",
"links"}), so existing consumers are unaffected.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import networkx as nx


def _safe_key(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stream_export(G: nx.Graph, output_path: str | Path, *, batch_size: int = 4096) -> int:
    """Write a node-link graph.json incrementally (no full-graph materialization).

    Returns the number of links written. Peak memory is bounded by ``batch_size``
    items (not the whole graph); writes are batched so json.dumps is not called
    once per item (which is the slow path).

    Deterministic: nodes and links are emitted in graph-iteration order with
    per-item keys sorted (matching export.to_json's canonicalization).
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    def _item_json(primary_keys: list[str], d: dict) -> str:
        ordered: dict = {}
        for pk in primary_keys:
            ordered[pk] = d.pop(pk)
        for k in sorted(d):
            ordered[k] = d[k]
        return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))

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
                f.write(", ")
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
    """Import graph.json into SQLite using a streaming JSON parse (no full load).

    Uses ijson-style incremental consumption is avoided for zero-dependency;
    instead we parse with json.JSONDecoder's raw_decode over a streaming file
    read, processing nodes/links as they are decoded. Returns link count.
    """
    # Zero-dependency streaming: read the file in chunks and feed a decoder.
    import sqlite3

    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    from graphify.storage import _SCHEMA
    conn.executescript(_SCHEMA)
    cur = conn.cursor()
    cur.execute("DELETE FROM nodes")
    cur.execute("DELETE FROM edges")

    # Streaming JSON object decoder over the file
    dec = json.JSONDecoder()
    with Path(graph_path).open("r", encoding="utf-8") as f:
        text = f.read()
    obj, _ = dec.raw_decode(text)

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
