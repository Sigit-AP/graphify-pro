"""Tests for graphify.metrics — the objective quality harness."""
from __future__ import annotations

import json

import networkx as nx
import pytest

from graphify import metrics


def _write_graph(tmp_path, edges, labels=None):
    """Write a minimal node-link graph.json for metrics to load."""
    G = nx.Graph()
    nodes = set()
    for u, v in edges:
        G.add_edge(u, v, relation="calls", confidence="EXTRACTED")
        nodes.add(u)
        nodes.add(v)
    for n in nodes:
        G.nodes[n]["label"] = labels.get(n, n) if labels else n
    data = nx.node_link_data(G)
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _write_gt(tmp_path, calls):
    p = tmp_path / "gt.json"
    p.write_text(json.dumps({"calls": calls}), encoding="utf-8")
    return p


def test_perfect_resolution(tmp_path):
    calls = [{"from": "a.f", "to": "b.g"}, {"from": "a.f", "to": "c.h"}]
    g = _write_graph(tmp_path, [("a.f", "b.g"), ("a.f", "c.h")])
    gt = _write_gt(tmp_path, calls)
    r = metrics.resolution_metrics(g, gt)
    assert r["precision"] == 1.0
    assert r["recall"] == 1.0
    assert r["f1"] == 1.0


def test_missed_edge_penalizes_recall(tmp_path):
    calls = [{"from": "a.f", "to": "b.g"}, {"from": "a.f", "to": "c.h"}]
    g = _write_graph(tmp_path, [("a.f", "b.g")])  # missing c.h
    gt = _write_gt(tmp_path, calls)
    r = metrics.resolution_metrics(g, gt)
    assert r["recall"] == 0.5
    assert r["precision"] == 1.0  # no false positive


def test_false_edge_penalizes_precision(tmp_path):
    calls = [{"from": "a.f", "to": "b.g"}]
    g = _write_graph(tmp_path, [("a.f", "b.g"), ("a.f", "z.zz")])  # extra wrong edge
    gt = _write_gt(tmp_path, calls)
    r = metrics.resolution_metrics(g, gt)
    assert r["precision"] == 0.5
    assert r["recall"] == 1.0


def test_normalization_matches_short_names(tmp_path):
    """Normalization matches on the trailing symbol name, so 'db.lookup_user'
    and 'lookup_user' resolve to the same pair."""
    calls = [{"from": "auth.authenticate", "to": "db.lookup_user"}]
    g = _write_graph(tmp_path, [("authenticate", "lookup_user")])
    gt = _write_gt(tmp_path, calls)
    r = metrics.resolution_metrics(g, gt)
    assert r["f1"] == 1.0


def test_query_latency_returns_numbers(tmp_path):
    g = _write_graph(tmp_path, [("a.f", "b.g")], labels={"a.f": "authenticate", "b.g": "verify_token"})
    r = metrics.query_latency_ms(g, ["authenticate"])
    assert r["queries"] == 1
    assert r["avg_ms"] >= 0.0


def test_index_footprint(tmp_path):
    g = _write_graph(tmp_path, [("a.f", "b.g")])
    r = metrics.index_footprint(g)
    assert r["nodes"] == 2
    assert r["edges"] == 1
    assert r["disk_bytes"] > 0
