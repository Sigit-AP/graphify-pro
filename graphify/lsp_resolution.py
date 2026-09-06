"""Registry adapter: resolve Python instance member calls (``obj.method()``) via jedi.

This is the pipeline integration point. Unlike the test-bed helper, it maps a
jedi definition to the EXISTING graphify node by matching (resolved source file,
normalized method label) — never by re-deriving a node id, which would drift
from the extractor's own id recipe (absolute-path stems, namespace prefixes).

Signature matches the resolver registry contract: (per_file, all_nodes,
all_edges) -> None, mutating all_edges in place. Registered for .py files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


def _jedi_available() -> bool:
    try:
        import jedi  # noqa: F401
        return True
    except Exception:
        return False


def _norm_label(label: Any) -> str:
    """Normalize a node label to a comparison key: strip `.()`, lowercase."""
    return re.sub(r"[^a-zA-Z0-9_]+", "", str(label or "")).lower()


def _line_from_source_location(loc: Any) -> int | None:
    if not loc:
        return None
    try:
        return int(str(loc).lstrip("L"))
    except ValueError:
        return None


def resolve_python_instance_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve instance member calls to their true definition via jedi inference.

    The shared call pass skips instance calls (``obj.method()``) because a bare
    method name collides across the corpus. This resolver closes that gap using
    jedi's static type inference, then matches the definition to the EXISTING
    node (resolved source file + normalized method label), so the emitted edge
    always lands on the extractor's real node — never a re-derived id.
    """
    if not _jedi_available():
        return
    import jedi

    # Index existing nodes: resolved source_file -> (label_key -> node_id).
    by_file: dict[str, dict[str, str]] = {}
    node_ids: set[str] = set()
    for n in all_nodes:
        nid = n.get("id")
        if not nid:
            continue
        node_ids.add(nid)
        sf = n.get("source_file")
        if not sf:
            continue
        try:
            key = str(Path(sf).resolve())
        except (OSError, RuntimeError):
            key = str(sf)
        by_file.setdefault(key, {})[_norm_label(n.get("label"))] = str(nid)

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}

    # Gather python instance member calls from per_file.
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for rc in result.get("raw_calls", []):
            if not isinstance(rc, dict):
                continue
            sf = str(rc.get("source_file", ""))
            if not sf.endswith(".py"):
                continue
            if not rc.get("is_member_call"):
                continue
            receiver = rc.get("receiver")
            if isinstance(receiver, str) and receiver[:1].isupper():
                continue  # class-qualified — handled elsewhere
            callee = str(rc.get("callee", "")).strip()
            caller = str(rc.get("caller_nid", "")).strip()
            if not callee or not caller or caller not in node_ids:
                continue
            line_no = _line_from_source_location(rc.get("source_location"))
            if not line_no:
                continue
            path = Path(sf)
            if not path.is_file():
                continue
            try:
                code = path.read_text(encoding="utf-8", errors="ignore")
                script = jedi.Script(code=code, path=str(path))
            except Exception:
                continue
            method_name = callee.split(".")[-1]
            try:
                lines = code.splitlines()
                if line_no - 1 >= len(lines):
                    continue
                col = lines[line_no - 1].find(method_name)
                if col < 0:
                    continue
                defs = script.goto(line_no, col + len(method_name))
            except Exception:
                continue
            # Map the jedi definition to an existing node.
            target_id = None
            for d in defs:
                if getattr(d, "type", None) not in ("function", "def", "instance"):
                    continue
                mp = str(d.module_path) if d.module_path else None
                if not mp:
                    continue
                try:
                    key = str(Path(mp).resolve())
                except (OSError, RuntimeError):
                    key = mp
                name = _norm_label(getattr(d, "name", ""))
                node_map = by_file.get(key, {})
                if name in node_map:
                    target_id = node_map[name]
                    break
            if not target_id or target_id == caller:
                continue
            pair = (caller, target_id)
            if pair in existing_pairs:
                continue
            existing_pairs.add(pair)
            all_edges.append({
                "source": caller,
                "target": target_id,
                "relation": "calls",
                "context": "instance_member_call",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": rc.get("source_file", ""),
                "source_location": rc.get("source_location"),
                "weight": 1.0,
                "metadata": {"resolver": "jedi_lsp", "callee": callee},
            })
