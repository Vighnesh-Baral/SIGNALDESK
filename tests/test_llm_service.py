from app.services import llm_service


def test_generate_json_sends_conservative_ollama_memory_settings(monkeypatch):
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

    assert llm_service.generate_json("Return JSON") == {"ok": True}
    assert captured["timeout"] == 240
    assert captured["payload"]["keep_alive"] == "5m"
    assert captured["payload"]["options"]["num_ctx"] == 4096
    assert captured["payload"]["options"]["num_batch"] == 128
    assert captured["payload"]["options"]["num_predict"] == 512


def test_generate_json_retries_cuda_kv_cache_error_with_smaller_context(monkeypatch):
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

    assert result == {"classifications": []}
    assert len(captured) == 2
    assert captured[0]["options"]["num_ctx"] == 4096
    assert captured[0]["options"]["num_batch"] == 128
    assert captured[1]["options"]["num_ctx"] == 2048
    assert captured[1]["options"]["num_batch"] == 64
