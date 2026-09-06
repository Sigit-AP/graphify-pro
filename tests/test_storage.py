"""Tests for graphify.storage — SQLite store + incremental update (Fase 2)."""
from __future__ import annotations

import json

import networkx as nx
import pytest

from graphify import storage


def _write_graph(tmp_path, edges, labels=None):
    G = nx.Graph()
    for u, v in edges:
        G.add_edge(u, v, relation="calls", confidence="EXTRACTED")
    for n in G.nodes:
        G.nodes[n]["label"] = labels.get(n, n) if labels else n
        G.nodes[n]["source_file"] = "src/mod.py"
    data = nx.node_link_data(G)
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_import_and_stats(tmp_path):
    g = _write_graph(tmp_path, [("a.f", "b.g"), ("a.f", "c.h")])
    db = tmp_path / "store.db"
    n = storage.import_graph(db, g)
    assert n == 2
    s = storage.stats(db)
    assert s["nodes"] == 3
    assert s["edges"] == 2


def test_lookup_finds_by_substring(tmp_path):
    g = _write_graph(tmp_path, [("a.auth_user", "b.auth_token")],
                     labels={"a.auth_user": "authenticate", "b.auth_token": "auth_token"})
    db = tmp_path / "store.db"
    storage.import_graph(db, g)
    hits = storage.lookup(db, "auth")
    assert len(hits) == 2


def test_neighbors_khop(tmp_path):
    g = _write_graph(tmp_path, [("a", "b"), ("b", "c"), ("c", "d")])
    db = tmp_path / "store.db"
    storage.import_graph(db, g)
    nh = storage.neighbors(db, "a", k=2)
    ids = {x["id"] for x in nh}
    assert ids == {"a", "b", "c"}  # k=2 reaches c, not d


def test_mark_file_changed_invalidates(tmp_path):
    g = _write_graph(tmp_path, [("a.f", "b.g")])
    db = tmp_path / "store.db"
    storage.import_graph(db, g)
    # first mark with a fresh hash removes the 2 nodes of src/mod.py
    assert storage.mark_file_changed(db, "src/mod.py", "hash1") == 2
    # same hash -> no-op (0 nodes removed)
    assert storage.mark_file_changed(db, "src/mod.py", "hash1") == 0
    s = storage.stats(db)
    assert s["nodes"] == 0  # both nodes share src/mod.py, both removed

    # re-import to restore, then change hash -> 2 nodes removed again
    storage.import_graph(db, g)
    assert storage.mark_file_changed(db, "src/mod.py", "hash2") == 2
    s = storage.stats(db)
    assert s["nodes"] == 0
    assert s["edges"] == 0


def test_subgraph_terms(tmp_path):
    g = _write_graph(tmp_path, [("authenticate", "verify_token")])
    db = tmp_path / "store.db"
    storage.import_graph(db, g)
    r = storage.subgraph_terms(db, ["auth", "token"], depth=1)
    assert r["reached_nodes"] >= 1
