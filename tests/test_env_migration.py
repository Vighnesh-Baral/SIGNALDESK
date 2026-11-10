from scripts.apply_vram_safe_defaults import update_env_file


def test_vram_defaults_update_only_inference_keys_and_preserve_secrets(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SIGNALDESK_API_TOKEN=keep-this-secret\n"
        "PUBLIC_BASE_URL=https://example.test\n"
        "OLLAMA_BATCH_SIZE=15\n"
        "OLLAMA_MODEL=qwen3:4b\n",
        encoding="utf-8",
    )

    updated = update_env_file(env_file)
    content = env_file.read_text(encoding="utf-8")

    assert "SIGNALDESK_API_TOKEN=keep-this-secret" in content
    assert "PUBLIC_BASE_URL=https://example.test" in content
    assert "OLLAMA_MODEL=qwen3:4b" in content
    assert "OLLAMA_BATCH_SIZE=5" in content
    assert "OLLAMA_NUM_CTX=4096" in content
    assert "OLLAMA_NUM_BATCH=128" in content
    assert len(updated) == 6
