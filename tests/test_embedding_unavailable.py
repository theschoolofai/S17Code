"""The embedder must fail as itself, not as a raw urllib error.

`OllamaNomicEmbedder` tries the current `/api/embed` endpoint and falls back to
the legacy `/api/embeddings` one. That fallback exists to tolerate an older
Ollama *install*; it says nothing about Ollama being absent. When nothing is
listening the fallback raised straight through `MemoryStore.write` and out of
`AgentRuntime.run`, so a run died on `urllib.error.URLError` with no statement
of what was unreachable or what to do about it.
"""
from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from s17code.core.memory.embeddings import EmbeddingUnavailable, OllamaNomicEmbedder


def _closed_port() -> int:
    """A port that was bound and released, so connecting to it is refused."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class _LegacyOnly(BaseHTTPRequestHandler):
    """An Ollama old enough to have only /api/embeddings."""

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/api/embed":
            self.send_error(404)
            return
        body = json.dumps({"embedding": [0.5, 0.25]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


def test_unreachable_service_raises_embedding_unavailable_not_urlerror() -> None:
    embedder = OllamaNomicEmbedder(base_url=f"http://127.0.0.1:{_closed_port()}")

    with pytest.raises(EmbeddingUnavailable):
        embedder.embed("anything")


def test_the_message_names_the_service_the_model_and_both_endpoint_errors() -> None:
    """A run that dies here must say what was unreachable and what to do.

    Both endpoint failures are reported: when Ollama is up but the model name is
    wrong, the modern endpoint's error is the one that explains it, and it used
    to be discarded by the bare `except Exception`.
    """
    port = _closed_port()
    embedder = OllamaNomicEmbedder(model="nomic-embed-text", base_url=f"http://127.0.0.1:{port}")

    with pytest.raises(EmbeddingUnavailable) as raised:
        embedder.embed_document("anything")

    message = str(raised.value)
    assert str(port) in message
    assert "nomic-embed-text" in message
    assert "/api/embed" in message and "/api/embeddings" in message
    assert "ollama" in message.lower()


def test_the_legacy_endpoint_fallback_still_works() -> None:
    """Guard the reason the bare except was there in the first place."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _LegacyOnly)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        embedder = OllamaNomicEmbedder(base_url=f"http://127.0.0.1:{server.server_port}")
        assert embedder.embed_query("anything") == [0.5, 0.25]
    finally:
        server.shutdown()
        server.server_close()
