"""Minimal LSP client over stdio JSON-RPC (stdlib only).

Correct LSP semantics:
  * REQUESTS carry an id and expect a response (initialize, definition).
  * NOTIFICATIONS carry NO id (initialized, didOpen, didChangeConfiguration).

Drives pyright-langserver (or any stdio LSP) for go-to-definition.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


class LspClient:
    def __init__(self, cmd: list[str], root_uri: str):
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._next_id = 1
        self._lock = threading.Lock()
        self._pending: dict[int, list[dict]] = {}
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # ── framing ──────────────────────────────────────────────────────────
    def _read_loop(self) -> None:
        buf = b""
        while True:
            try:
                c = self.proc.stdout.read(1)
            except Exception:
                return
            if not c:
                return
            buf += c
            while b"\r\n\r\n" in buf:
                header, _, rest = buf.partition(b"\r\n\r\n")
                length = 0
                for line in header.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1].strip())
                while len(rest) < length:
                    nxt = self.proc.stdout.read(1)
                    if not nxt:
                        return
                    rest += nxt
                body, buf = rest[:length], rest[length:]
                try:
                    msg = json.loads(body)
                except Exception:
                    continue
                if "id" in msg and msg.get("id") is not None:
                    with self._lock:
                        self._pending.setdefault(msg["id"], []).append(msg)

    def _send_frame(self, obj: dict) -> None:
        payload = json.dumps(obj).encode("utf-8")
        frame = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8") + payload
        self.proc.stdin.write(frame)
        self.proc.stdin.flush()

    def _request(self, method: str, params: dict) -> Any | None:
        with self._lock:
            rid = self._next_id
            self._next_id += 1
            self._pending[rid] = []
        self._send_frame({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.time() + 30.0
        while time.time() < deadline:
            with self._lock:
                if self._pending.get(rid):
                    return self._pending[rid].pop(0)
            time.sleep(0.02)
        return None

    def _notify(self, method: str, params: dict) -> None:
        self._send_frame({"jsonrpc": "2.0", "method": method, "params": params})

    # ── LSP methods ───────────────────────────────────────────────────────
    def initialize(self, root_uri: str, init_opts: dict | None = None) -> dict | None:
        params: dict = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "capabilities": {"textDocument": {"definition": {"linkSupport": False}}},
        }
        if init_opts:
            params["initializationOptions"] = init_opts
        return self._request("initialize", params)

    def initialized(self) -> None:
        self._notify("initialized", {})

    def open(self, file_uri: str, text: str, language_id: str = "python") -> None:
        self._notify("textDocument/didOpen", {
            "textDocument": {"uri": file_uri, "languageId": language_id, "version": 1, "text": text}})

    def definition(self, file_uri: str, line0: int, char0: int) -> list[dict] | None:
        resp = self._request("textDocument/definition", {
            "textDocument": {"uri": file_uri},
            "position": {"line": line0, "character": char0},
        })
        if not resp or "result" not in resp:
            return None
        result = resp["result"]
        if isinstance(result, dict):
            result = [result]
        return result or None

    def close(self) -> None:
        try:
            self._request("shutdown", {})
            self._notify("exit", {})
            self.proc.stdin.close()
            self.proc.terminate()
        except Exception:
            pass
