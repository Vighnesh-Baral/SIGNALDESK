import pandas as pd

from app.services import theme_classifier
from app.services.llm_service import OllamaError


def test_keyword_fallback_groups_common_feedback(monkeypatch):
    def fail_model(_prompt):
        raise OllamaError("offline for test")

    monkeypatch.setattr(theme_classifier, "generate_json", fail_model)
    frame = pd.DataFrame({
        "record_id": ["FB-000001", "FB-000002", "FB-000003"],
        "original_feedback": [
            "The app crashes during export.",
            "The dashboard is extremely slow.",
            "I cannot reset my password.",
        ],
    })
    result, warnings = theme_classifier.classify_records(frame, batch_size=3)
    assert result["theme"].tolist() == [
        "Crashes & Stability", "Performance & Speed", "Authentication & Account Access"
    ]
    assert set(result["classification_method"]) == {"keyword_fallback"}
    assert warnings


def test_qwen3_classification_is_tagged_per_record(monkeypatch):
    import pandas as pd
    from app.services import theme_classifier

    def fake_generate_json(_prompt):
        return {
            "classifications": [
                {"record_id": "FB-000001", "theme": "Performance & Speed", "sentiment": "negative"},
                {"record_id": "FB-000002", "theme": "Positive Feedback", "sentiment": "positive"},
            ]
        }

    monkeypatch.setattr(theme_classifier, "generate_json", fake_generate_json)
    frame = pd.DataFrame([
        {"record_id": "FB-000001", "original_feedback": "The dashboard is slow."},
        {"record_id": "FB-000002", "original_feedback": "This tool is excellent."},
    ])
    classified, warnings = theme_classifier.classify_records(frame, batch_size=2)

    assert classified["classification_method"].tolist() == ["qwen3", "qwen3"]
    assert classified["theme"].tolist() == ["Performance & Speed", "Positive Feedback"]
    assert warnings == []


def test_omitted_qwen3_records_use_explicit_fallback(monkeypatch):
    import pandas as pd
    from app.services import theme_classifier

    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: {
        "classifications": [
            {"record_id": "FB-000001", "theme": "Performance & Speed", "sentiment": "negative"}
        ]
    })
    frame = pd.DataFrame([
        {"record_id": "FB-000001", "original_feedback": "The dashboard is slow."},
        {"record_id": "FB-000002", "original_feedback": "The export crashes."},
    ])
    classified, warnings = theme_classifier.classify_records(frame, batch_size=2)

    assert classified["classification_method"].tolist() == ["qwen3", "keyword_fallback"]
    assert any("omitted or returned an invalid classification" in warning for warning in warnings)


def test_gpu_memory_error_splits_batches_and_retries_smaller_chunks(monkeypatch):
    import json
    import pandas as pd
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    calls = []

    def adaptive_model(prompt):
        records_block = prompt.split(
            "Records (IDs and text are supplied evidence; do not alter IDs):\n", 1
        )[1].split("\n\nReturn one JSON object", 1)[0]
        records = json.loads(records_block)
        calls.append(len(records))
        if len(records) > 2:
            raise OllamaError(
                'Ollama returned an HTTP error: CUDA out of memory while evaluating the prompt batch'
            )
        return {
            "classifications": [
                {"record_id": record["record_id"], "theme": "Performance & Speed", "sentiment": "negative"}
                for record in records
            ]
        }

    monkeypatch.setattr(theme_classifier, "generate_json", adaptive_model)
    frame = pd.DataFrame({
        "record_id": ["FB-1", "FB-2", "FB-3", "FB-4"],
        "original_feedback": ["Slow screen" for _ in range(4)],
    })
    classified, warnings = theme_classifier.classify_records(frame, batch_size=4)

    assert calls == [4, 2, 2]
    assert classified["classification_method"].tolist() == ["qwen3"] * 4
    assert any("GPU memory pressure" in warning for warning in warnings)


def test_single_record_gpu_memory_error_uses_keyword_fallback(monkeypatch):
    import pandas as pd
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(
        theme_classifier,
        "generate_json",
        lambda _prompt: (_ for _ in ()).throw(
            OllamaError("CUDA error: failed to allocate temporary prompt buffer")
        ),
    )
    frame = pd.DataFrame({
        "record_id": ["FB-1"],
        "original_feedback": ["The dashboard is extremely slow."],
    })
    classified, warnings = theme_classifier.classify_records(frame, batch_size=1)

    assert classified.loc[0, "classification_method"] == "keyword_fallback"
    assert classified.loc[0, "theme"] == "Performance & Speed"
    assert any("GPU memory remained insufficient" in warning for warning in warnings)


def test_qwen3_emotion_and_urgency_are_validated_per_record(monkeypatch):
    def fake_generate_json(_prompt):
        return {"classifications": [{
            "record_id": "FB-EMO-1",
            "theme": "Crashes & Stability",
            "sentiment": "negative",
            "emotion": "frustration",
            "urgency": "high",
        }]}

    monkeypatch.setattr(theme_classifier, "generate_json", fake_generate_json)
    frame = pd.DataFrame({"record_id": ["FB-EMO-1"], "original_feedback": ["Urgent: the app keeps crashing."]})
    classified, _warnings = theme_classifier.classify_records(frame, batch_size=1)
    assert classified.loc[0, "emotion"] == "frustration"
    assert classified.loc[0, "urgency"] == "high"


def test_fallback_emotion_and_urgency_are_conservative(monkeypatch):
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("offline")))
    frame = pd.DataFrame({"record_id": ["FB-EMO-2"], "original_feedback": ["Urgent, I am frustrated because login keeps failing."]})
    classified, _warnings = theme_classifier.classify_records(frame, batch_size=1)
    assert classified.loc[0, "emotion"] == "frustration"
    assert classified.loc[0, "urgency"] == "high"
