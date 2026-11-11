import pytest

from app.services import llm_service


def test_generate_json_sends_conservative_ollama_memory_settings(monkeypatch):
    # This test targets the local Ollama branch regardless of the developer .env.
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "ollama")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": '{"ok": true}'}}

    def fake_post(url, *, json, timeout):
        captured.update({"url": url, "payload": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(llm_service.requests, "post", fake_post)
    monkeypatch.setattr(llm_service, "OLLAMA_NUM_CTX", 4096)
    monkeypatch.setattr(llm_service, "OLLAMA_NUM_BATCH", 128)
    monkeypatch.setattr(llm_service, "OLLAMA_NUM_PREDICT", 512)
    monkeypatch.setattr(llm_service, "OLLAMA_KEEP_ALIVE", "5m")
    monkeypatch.setattr(llm_service, "OLLAMA_TIMEOUT_SECONDS", 240)

    assert llm_service.generate_json("Return JSON") == {"ok": True, "_signaldesk_provider": "ollama"}
    assert captured["timeout"] == 240
    assert captured["payload"]["keep_alive"] == "5m"
    assert captured["payload"]["options"]["num_ctx"] == 4096
    assert captured["payload"]["options"]["num_batch"] == 128
    assert captured["payload"]["options"]["num_predict"] == 512


def test_generate_json_retries_cuda_kv_cache_error_with_smaller_context(monkeypatch):
    # This test targets the local Ollama branch regardless of the developer .env.
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "ollama")
    import copy
    from types import SimpleNamespace
    import requests

    captured = []

    class SuccessResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": '{"classifications": []}'} }

    class OutOfMemoryResponse:
        def raise_for_status(self):
            error = requests.exceptions.HTTPError("500 Server Error")
            error.response = SimpleNamespace(
                text="llama-server reported out-of-memory during startup: failed to allocate buffer for kv cache"
            )
            raise error

    def fake_post(url, *, json, timeout):
        captured.append(copy.deepcopy(json))
        return OutOfMemoryResponse() if len(captured) == 1 else SuccessResponse()

    monkeypatch.setattr(llm_service.requests, "post", fake_post)
    monkeypatch.setattr(llm_service, "OLLAMA_NUM_CTX", 4096)
    monkeypatch.setattr(llm_service, "OLLAMA_NUM_BATCH", 128)

    result = llm_service.generate_json("Return an empty classifications list")

    assert result == {"classifications": [], "_signaldesk_provider": "ollama"}
    assert len(captured) == 2
    assert captured[0]["options"]["num_ctx"] == 4096
    assert captured[0]["options"]["num_batch"] == 128
    assert captured[1]["options"]["num_ctx"] == 2048
    assert captured[1]["options"]["num_batch"] == 64


def test_groq_provider_uses_openai_compatible_endpoint_and_parses_json(monkeypatch):
    from app.services import llm_service

    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}
        def raise_for_status(self):
            return None
        def json(self):
            return {"choices": [{"message": {"content": '{"classifications": []}'}}]}

    def fake_post(url, *, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "payload": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(llm_service, "LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_service, "LLM_BASE_URL", "")
    monkeypatch.setattr(llm_service.requests, "post", fake_post)

    assert llm_service.generate_json("Return classifications") == {"classifications": [], "_signaldesk_provider": "groq"}
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == "test-model"
    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_hosted_provider_requires_key_and_model(monkeypatch):
    from app.services import llm_service

    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "LLM_API_KEY", "")
    monkeypatch.setattr(llm_service, "LLM_MODEL", "")
    with pytest.raises(llm_service.LLMError, match="API key is not configured"):
        llm_service.generate_json("Return JSON")


def test_hosted_provider_rate_limit_becomes_actionable_error(monkeypatch):
    from app.services import llm_service
    import requests

    class RateLimitedResponse:
        status_code = 429
        headers = {"Retry-After": "30"}
        def raise_for_status(self):
            raise requests.HTTPError("429", response=self)

    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(llm_service, "LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_service, "LLM_BASE_URL", "")
    monkeypatch.setattr(llm_service, "_HOSTED_MAX_RETRIES", 0)
    monkeypatch.setattr(llm_service, "_HOSTED_MIN_REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(llm_service.requests, "post", lambda *args, **kwargs: RateLimitedResponse())

    with pytest.raises(llm_service.LLMError, match="rate limit reached"):
        llm_service.generate_json("Return JSON")


def test_groq_rate_limit_uses_configured_openrouter_fallback(monkeypatch):
    from app.services import llm_service

    calls = []

    class Response:
        headers = {}
        def __init__(self, status_code, content=None):
            self.status_code = status_code
            self.content = content
        def raise_for_status(self):
            if self.status_code >= 400:
                import requests
                raise requests.HTTPError(str(self.status_code), response=self)
        def json(self):
            return {"choices": [{"message": {"content": self.content}}]}

    def fake_post(url, **kwargs):
        calls.append(url)
        if "groq.com" in url:
            return Response(429)
        return Response(200, '{"ok": true}')

    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "LLM_API_KEY", "groq-key")
    monkeypatch.setattr(llm_service, "LLM_MODEL", "groq-model")
    monkeypatch.setattr(llm_service, "LLM_BASE_URL", "")
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_PROVIDER", "openrouter")
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_API_KEY", "router-key")
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_MODEL", "router/free-model")
    monkeypatch.setattr(llm_service, "LLM_FALLBACK_BASE_URL", "")
    monkeypatch.setattr(llm_service, "_HOSTED_MAX_RETRIES", 0)
    monkeypatch.setattr(llm_service, "_HOSTED_MIN_REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(llm_service.requests, "post", fake_post)

    result = llm_service.generate_json("Return JSON")
    assert result["ok"] is True
    assert result["_signaldesk_provider"] == "openrouter"
    assert calls == [
        "https://api.groq.com/openai/v1/chat/completions",
        "https://openrouter.ai/api/v1/chat/completions",
    ]


def test_hosted_provider_retries_transient_429_using_retry_after(monkeypatch):
    from app.services import llm_service

    calls = []
    waits = []

    class Response:
        def __init__(self, status_code, content=None, headers=None, text=""):
            self.status_code = status_code
            self.content = content
            self.headers = headers or {}
            self.text = text
        def raise_for_status(self):
            if self.status_code >= 400:
                import requests
                raise requests.HTTPError(str(self.status_code), response=self)
        def json(self):
            return {"choices": [{"message": {"content": self.content}}]}

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return Response(429, headers={"Retry-After": "3"})
        return Response(200, content='{"ok": true}')

    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(llm_service, "LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_service, "LLM_BASE_URL", "")
    monkeypatch.setattr(llm_service, "_HOSTED_MAX_RETRIES", 2)
    monkeypatch.setattr(llm_service, "_HOSTED_MIN_REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(llm_service.time, "sleep", waits.append)
    monkeypatch.setattr(llm_service.requests, "post", fake_post)

    result = llm_service.generate_json("Return JSON")
    assert result["ok"] is True
    assert len(calls) == 2
    assert waits == [3.0]


def test_hosted_provider_does_not_retry_hard_daily_quota_exhaustion(monkeypatch):
    from app.services import llm_service

    calls = []

    class Response:
        status_code = 429
        headers = {}
        text = "Daily quota exceeded"

    def fake_post(*args, **kwargs):
        calls.append(1)
        return Response()

    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_service, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(llm_service, "LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_service, "LLM_BASE_URL", "")
    monkeypatch.setattr(llm_service, "_HOSTED_MIN_REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(llm_service.requests, "post", fake_post)

    with pytest.raises(llm_service.ProviderCapacityError, match="daily quota"):
        llm_service.generate_json("Return JSON")
    assert len(calls) == 1
