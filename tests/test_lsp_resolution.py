"""Test the registry adapter: resolve_python_instance_member_calls.

End-to-end against graphify's real extract() pipeline, verifying the emitted
edge lands on the extractor's real node (not a re-derived id).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from graphify import lsp_resolution
from graphify.extract import extract


def _jedi_missing():
    return not lsp_resolution._jedi_available()


@pytest.fixture()
def pyproject(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "models.py").write_text(
        "class User:\n    def save(self):\n        return 'saved'\n"
    )
    (pkg / "main.py").write_text(
        "from pkg.models import User\n\n"
        "def run():\n    u = User()\n    return u.save()\n"
    )
    return tmp_path


@pytest.mark.skipif(_jedi_missing(), reason="jedi not installed")
def test_end_to_end_edge_lands_on_real_node(pyproject):
    r = extract([pyproject / "pkg" / "models.py", pyproject / "pkg" / "main.py"],
                root=pyproject)
    nodes = {n["id"]: n for n in r.get("nodes", [])}
    # The save node must exist.
    save_nodes = [nid for nid, n in nodes.items() if "save" in str(n.get("label", "")).lower()]
    assert save_nodes, "extractor did not emit the save method node"

    jedi_edges = [e for e in r.get("edges", []) if (e.get("metadata") or {}).get("resolver") == "jedi_lsp"]
    assert jedi_edges, "jedi resolver produced no edges"
    edge = jedi_edges[0]
    # target must be a REAL node id (no dangling edge)
    assert edge["target"] in nodes
    assert nodes[edge["target"]]["label"] == ".save()"
    assert edge["confidence"] == "EXTRACTED"


def test_no_crash_without_jedi(monkeypatch):
    monkeypatch.setattr(lsp_resolution, "_jedi_available", lambda: False)
    lsp_resolution.resolve_python_instance_member_calls([], [], [])  # must not raise


def test_line_from_source_location():
    assert lsp_resolution._line_from_source_location("L12") == 12
    assert lsp_resolution._line_from_source_location(None) is None


def test_norm_label():
    assert lsp_resolution._norm_label(".save()") == "save"
    assert lsp_resolution._norm_label("User") == "user"
    # underscores are preserved (dunder/method names), punctuation stripped
    assert lsp_resolution._norm_label("Foo.Bar__baz") == "foobar__baz"
