from __future__ import annotations

import json

import httpx
import pytest

from s17code.gateway import GatewayClient


@pytest.mark.asyncio
async def test_s17code_calls_gateway_without_owning_provider_keys(monkeypatch):
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "done", "provider": "gemini_2", "model": "gemini"})

    monkeypatch.setenv("S17_GATEWAY_PROVIDER", "gemini")
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        result = await GatewayClient("http://127.0.0.1:8111", client=http).complete(
            "Investigate the papers", "Use evidence", session="proof-run"
        )

    assert captured["url"] == "http://127.0.0.1:8111/v1/chat"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["provider"] == "gemini"
    assert payload["agent"] == "s17_agent"
    assert payload["session"] == "proof-run"
    assert not any("key" in field.lower() or "secret" in field.lower() for field in payload)
    assert result["provider"] == "gemini_2"


@pytest.mark.asyncio
async def test_gateway_retries_transient_pool_cooldown(monkeypatch):
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503, json={"detail": "all providers on cooldown"})
        return httpx.Response(200, json={"text": "recovered", "provider": "gemini_3", "model": "gemini"})

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setenv("S17_GATEWAY_ATTEMPTS", "3")
    monkeypatch.setattr("s17code.gateway.asyncio.sleep", no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await GatewayClient("http://gateway", client=http).complete("goal", "system")
    assert calls == 3
    assert result["text"] == "recovered"


@pytest.mark.asyncio
async def test_gateway_can_fall_back_without_exposing_credentials(monkeypatch):
    providers = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        providers.append(payload["provider"])
        if payload["provider"] == "gemini":
            return httpx.Response(503, json={"detail": "pool exhausted"})
        assert "model" not in payload
        return httpx.Response(200, json={"text": "fallback", "provider": "openrouter", "model": "configured"})

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setenv("S17_GATEWAY_PROVIDER", "gemini")
    monkeypatch.setenv("S17_GATEWAY_FALLBACK_PROVIDERS", "openrouter")
    monkeypatch.setenv("S17_GATEWAY_ATTEMPTS", "1")
    monkeypatch.setattr("s17code.gateway.asyncio.sleep", no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await GatewayClient("http://gateway", client=http).chat(
            prompt="goal", system="system", request={"model": "gemini-only"}
        )
    assert providers == ["gemini", "openrouter"]
    assert result["text"] == "fallback"


def test_s17code_does_not_reimplement_gateway_routes(app_client):
    assert app_client.post("/v1/chat", json={}).status_code == 404
    assert app_client.get("/v1/providers").status_code == 404


class TestClientOutwaitsTheGateway:
    """The caller must not give up before the callee can possibly answer.

    The gateway allows each upstream provider 180s. This client used to wait
    120s, so any completion slower than that was abandoned while the gateway
    was still legitimately waiting on it. The socket closed mid-read, so the
    caller saw a transport error (`httpx.ReadError`) instead of a provider
    error — and because the calls that run long are usually PLANNING calls,
    the graph was left without an answer node and the run finished having
    produced nothing, with no reason attached to say why.

    Observed against a live Gemini backend: planning completions returned in
    5-90s depending on queueing, so the 120s ceiling failed intermittently,
    which is the worst way for it to fail.
    """

    def test_default_timeout_exceeds_the_gateways_own_upstream_ceiling(self):
        client = GatewayClient("http://gateway")

        assert client._client.timeout.read is not None
        assert client._client.timeout.read > GatewayClient.UPSTREAM_CEILING_SECONDS, (
            "waiting less than the gateway's own upstream ceiling abandons calls "
            "it is still waiting on")

    def test_every_phase_of_the_timeout_is_raised_not_just_connect(self):
        """A read timeout is the one that bites; a bare number sets all four,
        so this guards against a future edit that raises only one."""
        timeout = GatewayClient("http://gateway")._client.timeout

        for phase in (timeout.read, timeout.write, timeout.pool):
            assert phase is not None
            assert phase > GatewayClient.UPSTREAM_CEILING_SECONDS

    def test_the_ceiling_is_overridable_for_a_slower_backend(self, monkeypatch):
        monkeypatch.setenv("S17_GATEWAY_TIMEOUT", "600")

        assert GatewayClient("http://gateway")._client.timeout.read == 600.0

    def test_an_injected_client_is_left_alone(self):
        """Tests and callers that supply their own client keep its settings."""
        supplied = httpx.AsyncClient(timeout=1.0)

        assert GatewayClient("http://gateway", client=supplied)._client is supplied
