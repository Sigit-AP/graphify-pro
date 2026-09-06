"""Tests for the AST-native Python instance member-call resolver.

Replaces the old jedi-based resolver. The extractor now stamps `receiver_type`
from local `var = ClassName(...)` bindings; this resolver resolves `o.method()`
to the true method node by that type — no jedi, ~10x faster.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from graphify.extract import extract


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


def test_resolves_instance_member_call(pyproject):
    r = extract([pyproject / "pkg" / "models.py", pyproject / "pkg" / "main.py"],
                root=pyproject)
    nodes = {n["id"]: n for n in r.get("nodes", [])}
    resolved = [e for e in r.get("edges", [])
                if (e.get("metadata") or {}).get("resolver") == "python_receiver_type"]
    assert resolved, "instance member call should resolve via receiver_type"
    edge = resolved[0]
    assert edge["target"] in nodes
    assert nodes[edge["target"]]["label"] == ".save()"
    assert edge["confidence"] == "EXTRACTED"


def test_ambiguous_receiver_not_resolved(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("class A:\n    def go(self):\n        return 1\n")
    (pkg / "b.py").write_text("class B:\n    def go(self):\n        return 2\n")
    (pkg / "main.py").write_text(
        "from pkg.a import A\nfrom pkg.b import B\n\n"
        "def f(flag):\n    x = A() if flag else B()\n    return x.go()\n"
    )
    r = extract([pkg / "a.py", pkg / "b.py", pkg / "main.py"], root=tmp_path)
    resolved = [e for e in r.get("edges", [])
                if (e.get("metadata") or {}).get("resolver") == "python_receiver_type"]
    # x is assigned to two different types -> poisoned -> must NOT resolve
    assert resolved == []
