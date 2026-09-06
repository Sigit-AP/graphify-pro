"""Confidence calibration (Fase 9): EXTRACTED/INFERRED provenance rules.

EXTRACTED edges come from deterministic evidence (AST, import, receiver_type).
INFERRED edges come from heuristics. Verifies the receiver_type resolver emits
EXTRACTED, never INFERRED, and that import-guided calls stay EXTRACTED.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graphify.extract import extract


def test_receiver_type_resolver_emits_extracted():
    d = Path(tempfile.mkdtemp(prefix="calib"))
    pkg = d / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "models.py").write_text(
        "class User:\n    def save(self):\n        return 'ok'\n"
    )
    (pkg / "main.py").write_text(
        "from pkg.models import User\n"
        "\n"
        "def run():\n"
        "    u = User()\n"
        "    return u.save()\n"
    )
    r = extract([pkg / "models.py", pkg / "main.py"], root=d)
    edges = r.get("edges", [])

    for e in edges:
        md = e.get("metadata") or {}
        if md.get("resolver") == "python_receiver_type":
            assert e.get("confidence") == "EXTRACTED", \
                f"receiver_type edge must be EXTRACTED, got {e.get('confidence')}"

    # import-guided calls are deterministic -> EXTRACTED
    for e in edges:
        if e.get("context") == "import_guided_call":
            assert e.get("confidence") == "EXTRACTED"


def test_member_call_resolution_present():
    d = Path(tempfile.mkdtemp(prefix="calib2"))
    pkg = d / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("class C:\n    def go(self):\n        return 1\n")
    (pkg / "main.py").write_text("from pkg.m import C\n\ndef f():\n    c = C()\n    return c.go()\n")
    r = extract([pkg / "m.py", pkg / "main.py"], root=d)
    resolved = [e for e in r.get("edges", [])
                if (e.get("metadata") or {}).get("resolver") == "python_receiver_type"]
    assert resolved, "member call should resolve via receiver_type"
    assert all(e["confidence"] == "EXTRACTED" for e in resolved)
