from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_application_status():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["application"] == "SIGNALDESK"
    settings = response.json()["inference_settings"]
    assert settings["batch_size"] == 5
    assert settings["context_window"] == 4096
    assert settings["prompt_batch_tokens"] == 128


def test_nonilion_manifest_describes_webhook_contract():
    response = client.get("/api/nonilion/manifest")
    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "/api/nonilion/webhook"
    assert body["protocol"] == "signaldesk.nonilion.reply.v1"


def test_root_landing_page_is_available():
    response = client.get("/")
    assert response.status_code == 200
    assert "SIGNALDESK" in response.text
    assert "Every customer" in response.text
    assert 'href="/app"' in response.text
    assert "EVIDENCE OVER ASSUMPTION" in response.text


def test_application_workspace_is_available():
    response = client.get("/app")
    assert response.status_code == 200
    assert "AI classification breakdown" in response.text
    assert "Evidence explorer" in response.text
    assert "Analyse customer feedback" in response.text
    assert "Liquid" not in response.text


def test_invalid_job_id_is_rejected():
    response = client.get("/api/jobs/../../etc/passwd")
    assert response.status_code in {404, 422}


def test_job_summary_endpoint_returns_saved_result(tmp_path, monkeypatch):
    import json
    import app.main as main_module

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path)
    job_id = "a" * 32
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    saved = {
        "dataset": {"total_valid_records": 7},
        "summary": {"themes_identified": 2},
        "findings": [],
        "warnings": [],
    }
    (job_dir / "result.json").write_text(json.dumps(saved), encoding="utf-8")

    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["job_id"] == job_id
    assert response.json()["dataset"]["total_valid_records"] == 7


def test_job_summary_endpoint_returns_404_for_unknown_job():
    response = client.get(f"/api/jobs/{'b' * 32}")
    assert response.status_code == 404


def test_nonilion_help_message_does_not_require_model():
    response = client.post("/api/nonilion/webhook", json={"message": "/help"})
    assert response.status_code == 200
    assert "SIGNALDESK" in response.json()["response"]


def test_upload_analyze_and_download_artifacts_end_to_end(tmp_path, monkeypatch):
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError
    import app.main as main_module

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(main_module, "UPLOAD_DIR", tmp_path / "uploads")

    def offline_model(_prompt):
        raise OllamaError("Ollama intentionally disabled in this test.")

    monkeypatch.setattr(theme_classifier, "generate_json", offline_model)

    csv_content = (
        "Customer_ID,Feedback\n"
        "C001,The application crashes during export.\n"
        "C002,The dashboard is very slow to load.\n"
        "C003,The application crashes during export!\n"
        "C004,It is difficult to find the settings page.\n"
    )
    response = client.post(
        "/api/analyze",
        files={"file": ("feedback.csv", csv_content, "text/csv")},
        data={"feedback_column": "Feedback", "source_id_column": "Customer_ID"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dataset"]["total_valid_records"] == 4
    assert body["dataset"]["exact_duplicate_mentions"] == 1
    assert body["summary"]["themes_identified"] >= 3

    job_id = body["job_id"]
    job_response = client.get(f"/api/jobs/{job_id}")
    assert job_response.status_code == 200
    assert job_response.json()["dataset"]["total_valid_records"] == 4

    for extension in ("xlsx", "pdf", "png"):
        artifact_response = client.get(f"/api/jobs/{job_id}/report.{extension}" if extension != "png" else f"/api/jobs/{job_id}/chart.png")
        assert artifact_response.status_code == 200
        assert len(artifact_response.content) > 100
    from openpyxl import load_workbook
    import io
    workbook = load_workbook(io.BytesIO(client.get(f"/api/jobs/{job_id}/report.xlsx").content), read_only=True)
    assert {"Problem Clusters", "Customer Segments", "Decision Pack"}.issubset(set(workbook.sheetnames))
    decision_pack = client.get(f"/api/jobs/{job_id}/decision-pack.md")
    assert decision_pack.status_code == 200
    assert b"Product Requirement Draft" in decision_pack.content


def test_protected_webhook_requires_configured_bearer_token(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "SIGNALDESK_API_TOKEN", "test-secret-token")
    denied = client.post("/api/nonilion/webhook", json={"message": "/help"})
    assert denied.status_code == 401

    allowed = client.post(
        "/api/nonilion/webhook",
        json={"message": "/help"},
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert allowed.status_code == 200


def test_nonilion_webhook_attachment_completes_end_to_end(tmp_path, monkeypatch):
    import base64
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError
    from app.integrations import nonilion as nonilion_module

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(nonilion_module, "UPLOAD_DIR", tmp_path / "uploads")

    def offline_model(_prompt):
        raise OllamaError("Ollama intentionally disabled in this test.")

    monkeypatch.setattr(theme_classifier, "generate_json", offline_model)
    csv_content = (
        "Customer_ID,Feedback\n"
        "C001,The application crashes during export.\n"
        "C002,The dashboard takes too long to load.\n"
        "C003,The navigation is confusing.\n"
    ).encode("utf-8")
    payload = {
        "event_type": "message",
        "conversation_id": "test-conversation",
        "message": "Find the most frequent customer problems and generate the reports.",
        "attachments": [{
            "filename": "feedback.csv",
            "content_base64": base64.b64encode(csv_content).decode("ascii"),
        }],
    }

    response = client.post("/api/nonilion/webhook", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"]
    assert "3 valid feedback records" in body["response"]
    assert "Representative source evidence" in body["response"]
    assert "source row" in body["response"]
    assert "Suggested follow-up" in body["response"]
    assert {item["type"] for item in body["artifacts"]} == {"excel", "pdf", "chart", "product_decision_pack"}

    artifact_urls = {item["type"]: item["url"] for item in body["artifacts"]}
    for artifact_type, url in artifact_urls.items():
        artifact_response = client.get(url)
        assert artifact_response.status_code == 200, (artifact_type, artifact_response.text)


def test_ai_breakdown_counts_only_recognised_classification_methods():
    import pandas as pd
    import app.main as main_module

    result = {
        "dataset": {"total_valid_records": 4},
        "classified_records": pd.DataFrame({
            "classification_method": ["qwen3", "qwen3", "keyword_fallback", "unknown"]
        }),
    }
    breakdown = main_module._classification_breakdown(result)
    assert breakdown == {
        "qwen3_records": 2,
        "fallback_records": 1,
        "unreported_records": 1,
        "total_records": 4,
        "total_classified": 3,
        "qwen3_percentage": 50.0,
        "fallback_percentage": 25.0,
    }


def test_public_mode_fails_closed_without_api_token(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "SIGNALDESK_API_TOKEN", "")
    monkeypatch.setattr(main_module, "PUBLIC_BASE_URL", "https://signaldesk.example")
    monkeypatch.setattr(main_module, "ALLOW_UNAUTHENTICATED_LOCAL", True)
    response = client.post("/api/nonilion/webhook", json={"message": "/help"})
    assert response.status_code == 503


def test_nonilion_file_reply_includes_structured_ai_breakdown(tmp_path, monkeypatch):
    import base64
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError
    from app.integrations import nonilion as nonilion_module

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(main_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main_module, "PUBLIC_BASE_URL", "https://signaldesk.example")
    monkeypatch.setattr(main_module, "SIGNALDESK_API_TOKEN", "integration-test-token")
    monkeypatch.setattr(nonilion_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("test offline")))
    csv_content = b"Feedback\nThe app crashes.\nThe dashboard is slow.\n"
    payload = {
        "message": "Analyse the feedback.",
        "attachments": [{
            "filename": "feedback.csv",
            "content_base64": base64.b64encode(csv_content).decode("ascii"),
        }],
    }
    response = client.post(
        "/api/nonilion/webhook",
        json=payload,
        headers={"Authorization": "Bearer integration-test-token"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_breakdown"]["qwen3_records"] == 0
    assert body["ai_breakdown"]["fallback_records"] == 2
    assert body["ai_breakdown"]["total_records"] == 2
    assert body["artifacts"][0]["url"].startswith("https://signaldesk.example/")


def test_non_local_host_is_blocked_without_api_token(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "SIGNALDESK_API_TOKEN", "")
    monkeypatch.setattr(main_module, "PUBLIC_BASE_URL", "")
    monkeypatch.setattr(main_module, "ALLOW_UNAUTHENTICATED_LOCAL", True)
    remote_client = TestClient(app, base_url="https://public.example")
    response = remote_client.post("/api/nonilion/webhook", json={"message": "/help"})
    assert response.status_code == 503


def test_manual_paste_submission_uses_shared_pipeline_and_preserves_source_rows(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("test offline")))
    response = client.post(
        "/api/analyze/text",
        json={
            "mode": "paste",
            "feedback_text": "The dashboard is slow.\n\nExport crashes during large reports.\n\nThe dashboard is slow!",
            "customer_id": "C-PASTE",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dataset"]["total_valid_records"] == 3
    assert body["dataset"]["exact_duplicate_mentions"] == 1
    assert body["ai_breakdown"]["total_records"] == 3
    job_id = body["job_id"]
    import pandas as pd
    processed = pd.read_csv(tmp_path / "outputs" / job_id / "classified_feedback.csv")
    assert processed["source_row"].tolist() == [1, 2, 3]
    assert processed["source_id"].tolist() == ["C-PASTE"] * 3
    assert processed["source_type"].tolist() == ["manual_text"] * 3


def test_single_complaint_is_kept_as_one_record_even_with_multiple_paragraphs(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("test offline")))
    response = client.post(
        "/api/analyze/text",
        json={
            "mode": "single",
            "feedback_text": "The app crashes after export.\n\nIt also loses my settings.",
            "customer_id": "C-SINGLE",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dataset"]["total_valid_records"] == 1
    import pandas as pd
    processed = pd.read_csv(tmp_path / "outputs" / body["job_id"] / "classified_feedback.csv")
    assert processed.loc[0, "source_id"] == "C-SINGLE"
    assert "It also loses my settings" in processed.loc[0, "original_feedback"]


def test_manual_submission_rejects_empty_text():
    response = client.post("/api/analyze/text", json={"mode": "paste", "feedback_text": "   "})
    assert response.status_code == 400


def test_upload_source_file_is_removed_after_analysis(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(main_module, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("test offline")))
    response = client.post(
        "/api/analyze",
        files={"file": ("feedback.csv", "Feedback\nThe dashboard is slow.\n", "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert not list(upload_dir.glob("**/*"))


def test_dashboard_exposes_three_submission_modes_and_file_remove_control():
    response = client.get("/app")
    assert response.status_code == 200
    for expected in (
        "Upload file", "Paste feedback", "Single complaint", "Remove",
        "/api/analyze/text", "blank line", "Clear inputs",
    ):
        assert expected in response.text


def test_nonilion_single_message_uses_shared_feedback_pipeline(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("test offline")))
    response = client.post("/api/nonilion/webhook", json={"message": "The app crashes whenever I export a report."})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"]
    assert body["ai_breakdown"]["total_records"] == 1
    assert "same classification and evidence pipeline" in body["response"]
    assert len(body["artifacts"]) == 4


def test_manual_paste_accepts_separator_line(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("test offline")))
    response = client.post(
        "/api/analyze/text",
        json={"mode": "paste", "feedback_text": "The search is slow.\n---\nThe app crashes on export."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["dataset"]["total_valid_records"] == 2


def test_analysis_response_includes_investigation_and_trend_state(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("offline")))
    response = client.post("/api/analyze/text", json={
        "mode": "single", "feedback_text": "The dashboard is slow to load."
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["findings"][0]["investigation"]["status"] == "Needs investigation"
    assert body["findings"][0]["investigation"]["evidence_breadth"] == "Limited"
    assert body["trend_analysis"]["available"] is False


def test_ask_endpoint_returns_dataset_grounded_citations(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("offline")))
    analysis = client.post("/api/analyze/text", json={
        "mode": "paste",
        "feedback_text": "The dashboard is slow to load.\n\nAnalytics takes too long to open.",
    })
    assert analysis.status_code == 200, analysis.text
    job_id = analysis.json()["job_id"]

    monkeypatch.setattr(main_module, "answer_research_question", lambda question, records, findings: {
        "answer": "Two retrieved comments mention slow loading.",
        "cited_evidence": [{"record_id": "FB-000001", "theme": "Performance & Speed", "quote": "The dashboard is slow to load."}],
        "answer_method": "qwen3_grounded",
        "caveat": "No timing telemetry was included.",
    })
    response = client.post(f"/api/jobs/{job_id}/ask", json={"question": "Why is performance slow?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == job_id
    assert body["cited_evidence"][0]["record_id"] == "FB-000001"
    assert body["answer_method"] == "qwen3_grounded"


def test_ask_endpoint_rejects_unknown_analysis_job():
    response = client.post("/api/jobs/00000000000000000000000000000000/ask", json={"question": "Why?"})
    assert response.status_code == 404


def test_multi_format_html_upload_uses_shared_analysis_pipeline(tmp_path, monkeypatch):
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError
    import app.main as main_module

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(main_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("offline")))
    html = """<html><nav>unrelated navigation</nav><main>
    <div class='review'>The dashboard is slow to load.</div>
    <div class='review'>Export crashes when reports are large.</div>
    </main></html>"""
    response = client.post("/api/analyze", files={"file": ("reviews.html", html, "text/html")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dataset"]["total_valid_records"] == 2
    assert body["ingestion"]["format"] == "html"
    assert body["problem_clusters"] is not None
    assert body["decision_pack"]["documents"]


def test_compare_saved_analyses_endpoint(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(main_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("offline")))
    first = client.post("/api/analyze/text", json={"mode": "paste", "feedback_text": "The dashboard is slow.\n\nThe dashboard loads slowly."})
    second = client.post("/api/analyze/text", json={"mode": "paste", "feedback_text": "The dashboard is slow.\n\nExport crashes.\n\nExporting reports fails."})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    response = client.post("/api/jobs/compare", json={"baseline_job_id": first.json()["job_id"], "current_job_id": second.json()["job_id"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["comparison_type"] == "observational_dataset_comparison"
    assert body["baseline"]["records"] == 2
    assert body["current"]["records"] == 3


def test_integration_preview_requires_no_provider_credentials(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(main_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("offline")))
    analysis = client.post("/api/analyze/text", json={"mode": "single", "feedback_text": "The dashboard is slow to load."})
    assert analysis.status_code == 200, analysis.text
    job_id = analysis.json()["job_id"]
    response = client.post(f"/api/jobs/{job_id}/integrations/github/preview", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_user_approval"] is True
    assert body["payload_preview"]["title"].startswith("Investigate customer reports")


def test_external_integration_write_requires_explicit_confirmation(tmp_path, monkeypatch):
    import app.main as main_module
    from app.services import theme_classifier
    from app.services.llm_service import OllamaError

    monkeypatch.setattr(main_module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(main_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(theme_classifier, "generate_json", lambda _prompt: (_ for _ in ()).throw(OllamaError("offline")))
    analysis = client.post("/api/analyze/text", json={"mode": "single", "feedback_text": "The dashboard is slow to load."})
    job_id = analysis.json()["job_id"]
    response = client.post(f"/api/jobs/{job_id}/integrations/github", json={"confirm": False})
    assert response.status_code == 400
    assert "confirm=true" in response.json()["detail"]
