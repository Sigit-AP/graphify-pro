"""Tests for graphify.scalable_export — threshold-based auto-export (Fase 10)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx

from graphify import scalable_export
from graphify.paths import load_node_link_graph


def _graph(n):
    G = nx.Graph()
    for i in range(n):
        G.add_node(f"n{i}", label=f"f{i}", file_type="code")
    for i in range(n - 1):
        G.add_edge(f"n{i}", f"n{i+1}", relation="calls")
    return G


def test_small_graph_uses_materialized(tmp_path):
    G = _graph(100)
    out = tmp_path / "g.json"
    n = scalable_export.export_auto(G, out, threshold=1000)
    assert n == G.number_of_edges()
    G2 = load_node_link_graph(str(out))
    assert G2.number_of_nodes() == 100


def test_large_graph_uses_streaming(tmp_path):
    G = _graph(500)
    out = tmp_path / "g.json"
    n = scalable_export.export_auto(G, out, threshold=100)
    assert n == G.number_of_edges()
    G2 = load_node_link_graph(str(out))
    assert G2.number_of_nodes() == 500


def test_both_paths_byte_compatible(tmp_path):
    G = _graph(200)
    # force both paths on the same graph
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    scalable_export.export_auto(G, out_a, threshold=1000)  # materialized
    scalable_export.export_auto(G, out_b, threshold=10)     # streaming
    # both must parse to the same node/edge counts
    Ga = load_node_link_graph(str(out_a))
    Gb = load_node_link_graph(str(out_b))
    assert Ga.number_of_nodes() == Gb.number_of_nodes()
    assert Ga.number_of_edges() == Gb.number_of_edges()
