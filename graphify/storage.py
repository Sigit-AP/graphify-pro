"""SQLite graph store: queryable index + incremental per-file update (Fase 2).

graph.json stays the interchange/export format (networkx node-link). This module
adds a queryable, RAM-light, incrementally-updatable layer on top of it, so:

  * queries run against SQLite directly (no full-graph load into RAM),
  * a changed file invalidates only its own nodes/edges (hash-keyed),
  * the store is re-importable from graph.json without losing provenance.

Dependency-free (sqlite3 + stdlib). The store is an OPTIONAL accelerator: every
function degrades gracefully to the in-memory graph if the store is absent.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT PRIMARY KEY,
    label       TEXT,
    source_file TEXT,
    file_type   TEXT,
    kind        TEXT,
    community   INTEGER,
    extra       TEXT
);
CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
CREATE INDEX IF NOT EXISTS idx_nodes_source ON nodes(source_file);
CREATE INDEX IF NOT EXISTS idx_nodes_community ON nodes(community);

CREATE TABLE IF NOT EXISTS edges (
    source     TEXT,
    target     TEXT,
    relation   TEXT,
    confidence TEXT,
    PRIMARY KEY (source, target, relation)
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);

CREATE TABLE IF NOT EXISTS file_hashes (
    source_file TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS memory_state (
    node_id        TEXT PRIMARY KEY,
    stability      REAL NOT NULL DEFAULT 1.0,
    lapse_count    INTEGER NOT NULL DEFAULT 0,
    repetitions    INTEGER NOT NULL DEFAULT 0,
    last_recall_ts REAL NOT NULL DEFAULT 0.0
);
"""


def _connect(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


# ── Import from graph.json ─────────────────────────────────────────────────
def import_graph(db_path: str | Path, graph_path: str | Path) -> int:
    """Import a graph.json (networkx node-link) into the store. Returns edge count."""
    from graphify.paths import load_node_link_graph
    G = load_node_link_graph(str(graph_path))
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM nodes")
        cur.execute("DELETE FROM edges")
        rows = []
        for nid, d in G.nodes(data=True):
            extra = {k: v for k, v in d.items()
                     if k not in ("id", "label", "source_file", "file_type", "kind", "community")}
            rows.append((
                nid,
                d.get("label"),
                d.get("source_file"),
                d.get("file_type"),
                d.get("kind"),
                d.get("community"),
                json.dumps(extra, ensure_ascii=False, default=str) if extra else None,
            ))
        cur.executemany(
            "INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?)", rows)
        erows = []
        for u, v, d in G.edges(data=True):
            erows.append((u, v, d.get("relation") or "uses", d.get("confidence") or "EXTRACTED"))
        cur.executemany(
            "INSERT OR REPLACE INTO edges VALUES (?,?,?,?)", erows)
        conn.commit()
        return len(erows)
    finally:
        conn.close()


# ── Incremental per-file update ────────────────────────────────────────────
def mark_file_changed(db_path: str | Path, source_file: str, content_hash: str) -> int:
    """Invalidate a single file's nodes/edges when its content hash changed.

    Deletes the file's nodes/edges and updates its hash. Returns the number of
    nodes removed (0 if hash unchanged -> no-op)."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT content_hash FROM file_hashes WHERE source_file=?", (source_file,)).fetchone()
        if row and row[0] == content_hash:
            return 0  # unchanged
        removed = cur.execute(
            "SELECT COUNT(*) FROM nodes WHERE source_file=?", (source_file,)).fetchone()[0]
        cur.execute("DELETE FROM edges WHERE source IN "
                    "(SELECT id FROM nodes WHERE source_file=?)", (source_file,))
        cur.execute("DELETE FROM edges WHERE target IN "
                    "(SELECT id FROM nodes WHERE source_file=?)", (source_file,))
        cur.execute("DELETE FROM nodes WHERE source_file=?", (source_file,))
        cur.execute(
            "INSERT OR REPLACE INTO file_hashes VALUES (?,?)", (source_file, content_hash))
        conn.commit()
        return removed
    finally:
        conn.close()


def upsert_nodes_edges(db_path: str | Path, nodes: Iterable[dict], edges: Iterable[dict]) -> None:
    """Insert/replace extracted nodes & edges into the store (one batch)."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        nrows = []
        for n in nodes:
            extra = {k: v for k, v in n.items()
                     if k not in ("id", "label", "source_file", "file_type", "kind", "community")}
            nrows.append((
                n.get("id"), n.get("label"), n.get("source_file"),
                n.get("file_type"), n.get("kind"), n.get("community"),
                json.dumps(extra, ensure_ascii=False, default=str) if extra else None,
            ))
        cur.executemany("INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?)", nrows)
        erows = []
        for e in edges:
            src = e.get("source", e.get("from"))
            dst = e.get("target", e.get("to"))
            erows.append((src, dst, e.get("relation") or "uses", e.get("confidence") or "EXTRACTED"))
        cur.executemany("INSERT OR REPLACE INTO edges VALUES (?,?,?,?)", erows)
        conn.commit()
    finally:
        conn.close()


# ── Query API (SQL, no full-graph load) ────────────────────────────────────
def lookup(db_path: str | Path, term: str, limit: int = 10) -> list[dict]:
    """Fuzzy label lookup by substring (case-insensitive)."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, label, source_file, kind FROM nodes "
            "WHERE label LIKE ? COLLATE NOCASE LIMIT ?",
            (f"%{term}%", limit)).fetchall()
        return [{"id": r[0], "label": r[1], "source_file": r[2], "kind": r[3]} for r in rows]
    finally:
        conn.close()


def neighbors(db_path: str | Path, node_id: str, k: int = 1) -> list[dict]:
    """k-hop neighborhood (undirected) starting at node_id."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        frontier = {node_id}
        visited = {node_id}
        for _ in range(k):
            nxt = set()
            for n in frontier:
                for r in cur.execute(
                        "SELECT source, target FROM edges WHERE source=? OR target=?", (n, n)):
                    s, t = r
                    if s not in visited:
                        nxt.add(s)
                    if t not in visited:
                        nxt.add(t)
            visited.update(nxt)
            frontier = nxt
            if not nxt:
                break
        out = []
        for n in sorted(visited):
            row = cur.execute("SELECT id, label, kind FROM nodes WHERE id=?", (n,)).fetchone()
            if row:
                out.append({"id": row[0], "label": row[1], "kind": row[2]})
        return out
    finally:
        conn.close()


def subgraph_terms(db_path: str | Path, terms: list[str], depth: int = 2) -> dict[str, Any]:
    """Seed nodes matching terms, expand k hops, return counts (no RAM graph)."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        seeds: set[str] = set()
        for t in terms:
            for r in cur.execute(
                    "SELECT id FROM nodes WHERE label LIKE ? COLLATE NOCASE LIMIT 5",
                    (f"%{t}%",)):
                seeds.add(r[0])
        visited = set(seeds)
        frontier = set(seeds)
        for _ in range(depth):
            nxt = set()
            for n in frontier:
                for r in cur.execute(
                        "SELECT source, target FROM edges WHERE source=? OR target=?", (n, n)):
                    s, t = r
                    if s not in visited:
                        nxt.add(s)
                    if t not in visited:
                        nxt.add(t)
            visited.update(nxt)
            frontier = nxt
            if not nxt:
                break
        return {"seeds": len(seeds), "reached_nodes": len(visited)}
    finally:
        conn.close()


def stats(db_path: str | Path) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        nodes = cur.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges = cur.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        files = cur.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0]
        return {"nodes": nodes, "edges": edges, "tracked_files": files}
    finally:
        conn.close()


# ── Memory state persistence (Algoritma Growth) ────────────────────────────
def save_memory_state(db_path: str | Path, node_id: str, snap: dict[str, Any]) -> None:
    """Persist one node's memory state (from growth.GrowthEngine.snapshot)."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO memory_state "
            "(node_id, stability, lapse_count, repetitions, last_recall_ts) "
            "VALUES (?,?,?,?,?)",
            (node_id,
             snap.get("stability_days", 1.0),
             snap.get("lapse_count", 0),
             snap.get("repetitions", 0),
             snap.get("_last_recall_ts", 0.0)),
        )
        conn.commit()
    finally:
        conn.close()


def load_memory_state(db_path: str | Path, node_id: str) -> dict[str, Any] | None:
    """Load one node's persisted memory state, or None if never recalled."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT stability, lapse_count, repetitions, last_recall_ts "
            "FROM memory_state WHERE node_id=?", (node_id,)).fetchone()
        if not row:
            return None
        return {
            "stability_days": row[0],
            "lapse_count": row[1],
            "repetitions": row[2],
            "_last_recall_ts": row[3],
        }
    finally:
        conn.close()


def load_all_memory_state(db_path: str | Path) -> dict[str, dict[str, Any]]:
    """Load the ENTIRE memory state — hydrates a fresh GrowthEngine after restart
    (long-term memory that actually survives across runs)."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT node_id, stability, lapse_count, repetitions, last_recall_ts "
            "FROM memory_state").fetchall()
        return {
            r[0]: {
                "stability_days": r[1],
                "lapse_count": r[2],
                "repetitions": r[3],
                "_last_recall_ts": r[4],
            }
            for r in rows
        }
    finally:
        conn.close()


def weak_nodes(db_path: str | Path, limit: int = 10, now: float | None = None) -> list[dict[str, Any]]:
    """Nodes with weakest memory RIGHT NOW (time-aware: computes R against now).

    A node that has silently decayed is weaker than a freshly-recalled one even
    if their stored stability is equal — this is the 'forgetting' the Growth
    algorithm must detect and prioritize for reinforcement."""
    import math as _math
    now = now if now is not None else time.time()
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT node_id, stability, lapse_count, repetitions, last_recall_ts "
            "FROM memory_state").fetchall()
        scored = []
        for node_id, stability, lapse, reps, ts in rows:
            elapsed_days = max((now - ts) / 86400.0, 0.0)
            R = _math.exp(-elapsed_days / stability) if stability > 0 else 0.0
            weakness = (1.0 - R) * (1.0 + 0.1 * lapse)
            scored.append({"node_id": node_id, "stability_days": stability,
                           "lapse_count": lapse, "repetitions": reps,
                           "retrievability": round(R, 4),
                           "weakness_score": round(weakness, 4)})
        scored.sort(key=lambda s: s["weakness_score"], reverse=True)
        return scored[:limit]
    finally:
        conn.close()
