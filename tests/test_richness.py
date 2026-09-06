"""Tests for graphify.richness — edge-type analytics (Fase 6)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx

from graphify import richness


def _inheritance_graph():
    """A <- B <- C (chain depth 2), D <- B (width 2). B has m, C overrides m."""
    G = nx.Graph()
    for nid in ["A", "B", "C", "D"]:
        G.add_node(nid, label=nid, file_type="code")
    # inheritance: child -> parent, with _src/_tgt markers (like the real build)
    G.add_edge("B", "A", relation="inherits", _src="B", _tgt="A")
    G.add_edge("C", "B", relation="inherits", _src="C", _tgt="B")
    G.add_edge("D", "B", relation="inherits", _src="D", _tgt="B")
    # methods
    G.add_node("B.m", label=".m()")
    G.add_node("C.m", label=".m()")
    G.add_node("B.other", label=".other()")
    G.add_edge("B", "B.m", relation="method")
    G.add_edge("C", "C.m", relation="method")
    G.add_edge("B", "B.other", relation="method")
    return G


def test_inheritance_depth_chain():
    G = _inheritance_graph()
    d = richness.inheritance_depth(G)
    assert d["max_depth"] == 2  # C -> B -> A
    assert d["nodes_with_supertypes"] == 3


def test_inheritance_width():
    G = _inheritance_graph()
    w = richness.inheritance_width(G)
    assert w["max_width"] == 2  # B has 2 direct children (C, D)


def test_detect_overrides():
    G = _inheritance_graph()
    ov = richness.detect_overrides(G)
    # C.m overrides B.m (both have label '.m()')
    assert any(o["subclass"] == "C" and o["ancestor"] == "B" for o in ov)


def test_typed_edge_counts_and_coverage():
    G = _inheritance_graph()
    counts = richness.typed_edge_counts(G)
    assert counts.get("inherits") == 3
    assert counts.get("method") == 3
    cov = richness.typed_edge_coverage(G)
    assert cov == 1.0  # all edges are specific (inherits/method)


def test_empty_graph_safe():
    G = nx.Graph()
    assert richness.inheritance_depth(G)["max_depth"] == 0
    assert richness.inheritance_width(G)["max_width"] == 0
    assert richness.detect_overrides(G) == []
    assert richness.typed_edge_coverage(G) == 0.0


def test_cycle_guard():
    G = nx.Graph()
    G.add_edge("A", "B", relation="inherits", _src="A", _tgt="B")
    G.add_edge("B", "A", relation="inherits", _src="B", _tgt="A")
    d = richness.inheritance_depth(G)
    assert d["max_depth"] >= 1  # terminates despite cycle
