"""Phase-2 security tests: XFF key extraction, 500s with CORS, admin gate."""
import os

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.limiter import _get_real_ip
from api.middleware import CatchAllExceptionMiddleware


def _request_with(headers: dict, client_host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 12345),
    }
    return Request(scope)


@pytest.mark.unit
class TestRateLimitKey:
    def test_rightmost_xff_entry_wins(self):
        # Client spoofs two entries; Railway appends the real IP last
        req = _request_with({"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.9.9.9"})
        assert _get_real_ip(req) == "9.9.9.9"

    def test_single_entry(self):
        req = _request_with({"X-Forwarded-For": "8.8.8.8"})
        assert _get_real_ip(req) == "8.8.8.8"

    def test_whitespace_and_empty_entries_ignored(self):
        req = _request_with({"X-Forwarded-For": "1.2.3.4,  , "})
        assert _get_real_ip(req) == "1.2.3.4"

    def test_no_header_falls_back_to_peer(self):
        req = _request_with({}, client_host="192.168.1.50")
        assert _get_real_ip(req) == "192.168.1.50"

    def test_empty_header_falls_back_to_peer(self):
        req = _request_with({"X-Forwarded-For": ""}, client_host="192.168.1.50")
        assert _get_real_ip(req) == "192.168.1.50"


def _build_crashing_app() -> FastAPI:
    app = FastAPI()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @app.get("/fine")
    async def fine():
        return {"ok": True}

    # Same relative order as production: catch-all inside CORS
    app.add_middleware(CatchAllExceptionMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://testclient.example"],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    return app


@pytest.mark.unit
class TestCatchAll500WithCors:
    def test_500_is_json_and_carries_cors_headers(self):
        client = TestClient(_build_crashing_app(), raise_server_exceptions=False)
        r = client.get("/boom", headers={"Origin": "http://testclient.example"})
        assert r.status_code == 500
        assert r.json() == {"detail": "Internal server error"}
        assert r.headers.get("access-control-allow-origin") == "http://testclient.example"

    def test_500_does_not_leak_exception_details(self):
        client = TestClient(_build_crashing_app(), raise_server_exceptions=False)
        r = client.get("/boom", headers={"Origin": "http://testclient.example"})
        assert "kaboom" not in r.text

    def test_normal_responses_unaffected(self):
        client = TestClient(_build_crashing_app())
        r = client.get("/fine", headers={"Origin": "http://testclient.example"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert r.headers.get("access-control-allow-origin") == "http://testclient.example"


_REQUIRE_ADMIN_SCRIPT = """
import os
os.environ.setdefault("FASTAPI_SERVICE_KEY", "test-key")
from fastapi import HTTPException
from api.routers.auth import require_admin

user = {"id": "u1", "role": "admin"}
assert require_admin(current_user=user) is user

for bad in ({"id": "u2", "role": "user"}, {"id": "u3"}):
    try:
        require_admin(current_user=bad)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError(f"expected 403 for {bad}")

print("REQUIRE_ADMIN_OK")
"""


@pytest.mark.unit
class TestRequireAdmin:
    def test_admin_gate_matrix(self):
        """Runs in a subprocess: importing api.routers pulls in the full ML
        stack, whose optional TensorFlow import can deadlock in restricted
        shells — a subprocess can be timed out and killed, an import cannot."""
        import subprocess
        import sys
        from pathlib import Path

        try:
            proc = subprocess.run(
                [sys.executable, "-c", _REQUIRE_ADMIN_SCRIPT],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=Path(__file__).parent.parent,
            )
        except subprocess.TimeoutExpired:
            pytest.skip("api.routers import hangs in this environment (TF/absl deadlock)")
        assert proc.returncode == 0, proc.stderr
        assert "REQUIRE_ADMIN_OK" in proc.stdout
