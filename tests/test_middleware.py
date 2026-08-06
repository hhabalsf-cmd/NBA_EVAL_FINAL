"""Tests for api.middleware — in particular that SSE bypasses gzip buffering."""
import gzip
import json

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from api.middleware import SelectiveGZipMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/big")
    async def big():
        return {"data": "x" * 5000}

    @app.get("/stream")
    async def stream():
        async def gen():
            for i in range(3):
                yield f"data: {json.dumps({'progress': i})}\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    app.add_middleware(SelectiveGZipMiddleware, minimum_size=1000)
    return app


@pytest.fixture()
def client():
    return TestClient(_build_app())


@pytest.mark.unit
class TestSelectiveGZip:
    def test_regular_json_is_gzipped(self, client):
        r = client.get("/big", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        assert r.headers.get("content-encoding") == "gzip"
        assert r.json()["data"] == "x" * 5000

    def test_sse_request_bypasses_gzip(self, client):
        r = client.get(
            "/stream",
            headers={"Accept": "text/event-stream", "Accept-Encoding": "gzip"},
        )
        assert r.status_code == 200
        assert "content-encoding" not in r.headers
        assert "data: " in r.text
        # Raw bytes must NOT be gzip (magic number 0x1f 0x8b)
        assert not r.content.startswith(b"\x1f\x8b")

    def test_sse_body_messages_pass_through_unmodified(self):
        """At the ASGI level each SSE event must stay its own body message,
        byte-identical — the gzip path would rewrite/coalesce them."""
        import anyio

        async def inner_app(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            })
            for i in range(3):
                await send({
                    "type": "http.response.body",
                    "body": f"data: {i}\n\n".encode(),
                    "more_body": i < 2,
                })

        mw = SelectiveGZipMiddleware(inner_app, minimum_size=1)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/stream",
            "headers": [
                (b"accept", b"text/event-stream"),
                (b"accept-encoding", b"gzip"),
            ],
        }
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        anyio.run(mw, scope, receive, send)

        bodies = [m for m in sent if m["type"] == "http.response.body"]
        assert [m["body"] for m in bodies] == [b"data: 0\n\n", b"data: 1\n\n", b"data: 2\n\n"]
        start = next(m for m in sent if m["type"] == "http.response.start")
        assert (b"content-encoding", b"gzip") not in start["headers"]

    def test_small_responses_not_gzipped(self, client):
        app_client = client
        r = app_client.get("/stream", headers={"Accept-Encoding": "gzip"})
        # Without an SSE Accept header the gzip path is used, but streaming
        # responses under GZipMiddleware must still decode correctly.
        assert r.status_code == 200
        assert "data: " in r.text
