"""Tests for graphify.agent_query — structured agent-native query (Fase 7)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx

from graphify import agent_query


def _graph():
    G = nx.Graph()
    for nid in ["main", "auth", "db", "cache", "User", "Admin"]:
        G.add_node(nid, label=nid, file_type="code")
    # main calls auth, auth calls db, main calls cache
    G.add_edge("main", "auth", relation="calls", _src="main", _tgt="auth")
    G.add_edge("auth", "db", relation="calls", _src="auth", _tgt="db")
    G.add_edge("main", "cache", relation="calls", _src="main", _tgt="cache")
    # Admin inherits User
    G.add_edge("Admin", "User", relation="inherits", _src="Admin", _tgt="User")
    return G


def test_consumers():
    G = _graph()
    c = agent_query.consumers(G, "db")
    assert len(c) == 1
    assert c[0]["consumer"] == "auth"
    assert c[0]["relation"] == "calls"


def test_impact_transitive():
    G = _graph()
    imp = agent_query.impact(G, "db")
    assert imp["direct_consumers"] == 1  # auth
    assert imp["transitive_consumers"] == 2  # auth + main (main->auth->db)


def test_typed_path():
    G = _graph()
    p = agent_query.typed_path(G, "main", "db", "calls")
    assert p["found"] is True
    assert p["path"] == ["main", "auth", "db"]
    assert p["length"] == 2


def test_typed_path_not_found():
    G = _graph()
    # no 'inherits' path from main to db
    p = agent_query.typed_path(G, "main", "db", "inherits")
    assert p["found"] is False


def test_typed_path_self():
    G = _graph()
    p = agent_query.typed_path(G, "main", "main", "calls")
    assert p["found"] is True
    assert p["length"] == 0


def test_consumers_respects_relation_filter():
    G = _graph()
    # Only inheritance consumers of User
    c = agent_query.consumers(G, "User", relations={"inherits"})
    assert len(c) == 1
    assert c[0]["consumer"] == "Admin"
