import pandas as pd

from app.services.research_assistant import answer_research_question, retrieve_relevant_records


def make_records():
    return pd.DataFrame([
        {"record_id": "FB-001", "theme": "Performance & Speed", "sentiment": "negative", "emotion": "frustration", "urgency": "medium", "original_feedback": "The dashboard is slow to load.", "source_id": "C1", "source_row": 2},
        {"record_id": "FB-002", "theme": "Performance & Speed", "sentiment": "negative", "emotion": "frustration", "urgency": "low", "original_feedback": "Analytics takes too long to open.", "source_id": "C2", "source_row": 3},
        {"record_id": "FB-003", "theme": "Reporting & Export", "sentiment": "negative", "emotion": "disappointment", "urgency": "low", "original_feedback": "Export crashes on large reports.", "source_id": "C3", "source_row": 4},
    ])


def test_retrieval_matches_theme_and_feedback_words():
    findings = [{"theme": "Performance & Speed"}, {"theme": "Reporting & Export"}]
    rows = retrieve_relevant_records("Why is Performance & Speed a problem?", make_records(), findings)
    assert {item["record_id"] for item in rows} == {"FB-001", "FB-002"}


def test_answer_only_returns_citations_in_retrieved_evidence(monkeypatch):
    # The expected provenance is Qwen3/Ollama; do not inherit the developer .env.
    from app.services import llm_service
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "ollama")

    def model(_prompt):
        assert '"mention_count"' in _prompt
        return {"answer": "Customers describe slow dashboard and analytics loading.", "record_ids": ["FB-001", "FB-999"], "caveat": "No timing telemetry was included."}

    result = answer_research_question(
        "Why is Performance & Speed a problem?",
        make_records(),
        [{"theme": "Performance & Speed"}],
        model_call=model,
    )
    assert result["answer_method"] == "qwen3_grounded"
    assert [item["record_id"] for item in result["cited_evidence"]] == ["FB-001"]
    assert "timing telemetry" in result["caveat"]


def test_invalid_model_citations_trigger_retrieval_fallback():
    def model(_prompt):
        return {"answer": "There is a root cause.", "record_ids": ["NOT-A-REAL-ID"]}

    result = answer_research_question(
        "Why is Performance & Speed a problem?",
        make_records(),
        [{"theme": "Performance & Speed"}],
        model_call=model,
    )
    assert result["answer_method"] == "retrieval_fallback"
    assert result["cited_evidence"]
    assert all(item["record_id"].startswith("FB-") for item in result["cited_evidence"])
    assert "does not infer a root cause" in result["caveat"]



def test_rejects_invented_record_id_in_answer_prose():
    def model(_prompt):
        return {"answer": "The issue appears in FB-001 and FB-999.", "record_ids": ["FB-001"]}

    result = answer_research_question(
        "Why is Performance & Speed a problem?",
        make_records(),
        [{"theme": "Performance & Speed"}],
        model_call=model,
    )
    assert result["answer_method"] == "retrieval_fallback"
    assert all(item["record_id"] != "FB-999" for item in result["cited_evidence"])
