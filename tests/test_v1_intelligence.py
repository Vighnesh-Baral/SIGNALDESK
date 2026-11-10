import pandas as pd

from app.services.clustering_engine import analyze_segments, build_problem_clusters
from app.services.comparison_engine import compare_analyses
from app.services.decision_engine import build_decision_pack


def _frame():
    return pd.DataFrame([
        {"record_id": "FB-1", "original_feedback": "Dashboard is very slow to load", "theme": "Performance & Speed", "source_id": "C1", "plan": "Pro"},
        {"record_id": "FB-2", "original_feedback": "Dashboard loading is very slow", "theme": "Performance & Speed", "source_id": "C2", "plan": "Pro"},
        {"record_id": "FB-3", "original_feedback": "Export crashes every time", "theme": "Crashes & Stability", "source_id": "C3", "plan": "Free"},
        {"record_id": "FB-4", "original_feedback": "Export keeps crashing each time", "theme": "Crashes & Stability", "source_id": "C4", "plan": "Free"},
    ])


def test_customer_segmentation_reports_record_denominators():
    result = analyze_segments(_frame())
    assert result["available"] is True
    plan = next(item for item in result["dimensions"] if item["column"] == "plan")
    assert {item["segment"] for item in plan["segments"]} == {"Pro", "Free"}
    assert sum(item["feedback_records"] for item in plan["segments"]) == 4


def test_problem_clustering_reports_method_and_record_ids():
    result = build_problem_clusters(_frame(), threshold=0.55)
    assert result["available"] is True
    assert result["method"] in {"character_ngram_tfidf_fallback"}
    assert result["clusters"]
    assert all(len(item["record_ids"]) >= 2 for item in result["clusters"])


def test_comparison_uses_prevalence_not_raw_counts_only():
    base = {"dataset": {"filename": "before"}, "classified_records": _frame().iloc[:2].copy()}
    current_frame = _frame().iloc[:4].copy()
    current_frame.loc[2, "theme"] = "Performance & Speed"
    current = {"dataset": {"filename": "after"}, "classified_records": current_frame}
    result = compare_analyses(base, current)
    performance = next(item for item in result["theme_comparisons"] if item["theme"] == "Performance & Speed")
    assert performance["baseline_prevalence_pct"] == 100.0
    assert performance["current_prevalence_pct"] == 75.0
    assert "not proof" in result["interpretation"]


def test_decision_pack_labels_hypotheses_and_scores_as_unverified_heuristics():
    frame = _frame()
    finding = {
        "finding_id": "F-001", "theme": "Performance & Speed", "mention_count": 2,
        "prevalence_pct": 50.0, "record_ids": ["FB-1", "FB-2"],
        "unique_normalized_feedback_count": 2, "urgency_breakdown": {"high": 0},
        "investigation": {"investigation_checks": ["Benchmark load times"]},
    }
    result = build_decision_pack([finding], frame, {"total_valid_records": 4})
    card = result["prioritised_decision_cards"][0]
    assert card["triage_score"] >= 0
    assert "not severity" in card["score_note"]
    assert card["root_cause_hypotheses"][0]["status"] == "Unverified hypothesis"
    assert result["documents"][0]["prd_markdown"].startswith("# Product Requirement Draft")
