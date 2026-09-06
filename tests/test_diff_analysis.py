"""Tests for graphify.diff_analysis — diff-aware impact (Fase 8)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx

from graphify import diff_analysis


def _base_graph():
    G = nx.Graph()
    for nid in ["main", "auth", "db", "cache"]:
        G.add_node(nid, label=nid, file_type="code")
    G.add_edge("main", "auth", relation="calls", _src="main", _tgt="auth")
    G.add_edge("auth", "db", relation="calls", _src="auth", _tgt="db")
    G.add_edge("main", "cache", relation="calls", _src="main", _tgt="cache")
    return G


def test_diff_detects_added_and_removed():
    before = _base_graph()
    after = _base_graph()
    after.add_node("new_svc", label="new_svc", file_type="code")
    after.add_edge("main", "new_svc", relation="calls", _src="main", _tgt="new_svc")
    after.remove_node("cache")

    d = diff_analysis.diff_graphs(before, after)
    assert d["added_nodes"] == ["new_svc"]
    assert d["removed_nodes"] == ["cache"]
    assert d["node_delta"] == 0  # +1 -1


def test_diff_detects_changed_node():
    before = _base_graph()
    after = _base_graph()
    after.nodes["db"]["label"] = "db_v2"

    d = diff_analysis.diff_graphs(before, after)
    assert "db" in d["changed_nodes"]


def test_diff_edge_delta():
    before = _base_graph()
    after = _base_graph()
    after.remove_edge("main", "cache")
    d = diff_analysis.diff_graphs(before, after)
    assert d["edge_delta"] == -1
    assert any(k[0] == "main" and k[1] == "cache" for k in d["removed_edges"])


def test_impact_of_removed():
    before = _base_graph()
    # removing 'db' should report 'auth' and 'main' as affected consumers
    imp = diff_analysis.impact_of_removed(before, ["db"])
    assert "db" in imp
    assert imp["db"]["transitive_consumers"] >= 2  # auth + main
    assert "auth" in imp["db"]["surviving_consumers"]


def test_empty_diff():
    G = _base_graph()
    d = diff_analysis.diff_graphs(G, G.copy())
    assert d["added_nodes"] == []
    assert d["removed_nodes"] == []
    assert d["changed_nodes"] == []
    assert d["edge_delta"] == 0
