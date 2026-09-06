"""AST-native Python instance member-call resolver (Fase 11: replaces jedi).

The extractor now stamps `receiver_type` on Python member-call raw_calls from
local `var = ClassName(...)` bindings (see extractors/engine.py). This resolver
uses that type — plus the class/method index already built by the native Python
member-call pass — to resolve `o.method()` to the true definition WITHOUT jedi.

This is the same mechanism Ruby/C#/Java already use, and it is ~10x faster than
jedi (no inference engine, no stdlib plugins, no per-call goto).
"""
from __future__ import annotations

import re
from typing import Any


def _key(label: Any) -> str:
    """Normalize a class/method label to a comparison key (drop punctuation)."""
    return re.sub(r"[^a-zA-Z0-9]+", "", str(label or "")).lower()


def resolve_python_instance_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Python instance member calls by receiver_type (AST-native).

    Only raw_calls that carry a ``receiver_type`` (from the extractor's local
    `var = ClassName(...)` bindings) are resolved — 100%-confidence type
    evidence, never a bare-name guess. Emits EXTRACTED ``calls`` edges to the
    method node the class owns.
    """
    node_by_id: dict[str, dict] = {str(n.get("id")): n for n in all_nodes if n.get("id")}

    # Class label -> class node ids; (class_node_id, method_key) -> method node id.
    class_def_nids: dict[str, list[str]] = {}
    method_index: dict[tuple[str, str], str] = {}
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        src, tgt = str(e.get("source", "")), str(e.get("target", ""))
        cnode = node_by_id.get(src)
        if cnode is not None:
            class_def_nids.setdefault(_key(cnode.get("label", "")), []).append(src)
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            method_name = str(tnode.get("label", "")).strip("()").lstrip(".")
            method_index[(src, _key(method_name))] = tgt
    # A class with N methods produced N entries; collapse to a unique set.
    for k in list(class_def_nids):
        class_def_nids[k] = sorted(set(class_def_nids[k]))

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}

    def _unique_class(name: str) -> str | None:
        nids = class_def_nids.get(_key(name), [])
        return nids[0] if len(nids) == 1 else None

    for result in per_file:
        if not isinstance(result, dict):
            continue
        for rc in result.get("raw_calls", []):
            if not isinstance(rc, dict):
                continue
            if not rc.get("is_member_call"):
                continue
            caller = str(rc.get("caller_nid", ""))
            callee = str(rc.get("callee", "")).strip()
            receiver_type = rc.get("receiver_type")
            if not caller or not callee or not receiver_type:
                continue
            class_nid = _unique_class(str(receiver_type))
            if class_nid is None:
                continue  # ambiguous / absent -> bail (god-node guard)
            method_nid = method_index.get((class_nid, _key(callee)))
            if method_nid is None:
                continue
            pair = (caller, method_nid)
            if pair in existing_pairs:
                continue
            existing_pairs.add(pair)
            all_edges.append({
                "source": caller,
                "target": method_nid,
                "relation": "calls",
                "context": "instance_member_call",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": rc.get("source_file", ""),
                "source_location": rc.get("source_location"),
                "weight": 1.0,
                "metadata": {
                    "resolver": "python_receiver_type",
                    "receiver_type": receiver_type,
                    "callee": callee,
                },
            })
