"""Generate review-ready product decision artifacts from evidence-backed findings."""
from __future__ import annotations

from typing import Any

import pandas as pd


def _hypotheses(theme: str, quotes: list[str]) -> list[dict[str, str]]:
    text = " ".join(quotes).casefold()
    candidates: list[str] = []
    if theme == "Performance & Speed":
        if any(term in text for term in ("large", "many records", "volume", "dataset")):
            candidates.append("High data volume may be associated with the reported delay; benchmark multiple dataset sizes.")
        if any(term in text for term in ("load", "loading", "spinner", "dashboard")):
            candidates.append("The delay may occur during page rendering or data retrieval; measure client and API timings separately.")
    elif theme == "Crashes & Stability":
        if any(term in text for term in ("export", "download", "report")):
            candidates.append("The failure may be associated with the export workflow; reproduce exports with controlled file sizes and filters.")
        if any(term in text for term in ("mobile", "android", "ios", "phone")):
            candidates.append("The reported failure may be environment-specific; compare affected app versions and devices.")
    elif theme == "Data Sync & Reliability":
        candidates.append("A delay or failure in the sync path may explain the reported inconsistency; trace record IDs and sync timestamps across clients.")
    elif theme == "Authentication & Account Access":
        candidates.append("The issue may occur in sign-in, verification or account-state handling; trace the complete authentication sequence.")
    elif theme == "Reporting & Export":
        candidates.append("The issue may involve export configuration, formatting or data selection; compare requested options with generated output.")
    if not candidates:
        candidates.append("The available feedback identifies a customer-facing symptom but does not establish a technical cause; gather reproducible steps and relevant telemetry.")
    return [{"hypothesis": item, "status": "Unverified hypothesis", "validation": "Test against product telemetry and reproduction evidence before treating as a cause."} for item in candidates]


def build_decision_pack(findings: list[dict], classified: pd.DataFrame, dataset: dict) -> dict[str, Any]:
    cards = []
    documents = []
    total_records = max(1, len(classified))
    for finding in findings:
        theme = str(finding.get("theme", "Other / Unclear"))
        record_ids = [str(item) for item in finding.get("record_ids", [])]
        quotes = classified.loc[classified["record_id"].astype(str).isin(record_ids), "original_feedback"].astype(str).head(12).tolist()
        hypotheses = _hypotheses(theme, quotes)
        top_count = int(finding.get("mention_count", 0))
        customers = int(classified.loc[classified["record_id"].astype(str).isin(record_ids), "source_id"].dropna().astype(str).nunique()) if "source_id" in classified else 0
        urgency = finding.get("urgency_breakdown", {})
        unique = int(finding.get("unique_normalized_feedback_count", 0))
        # Transparent score is a triage aid, not a severity/ROI metric.
        frequency_component = min(40.0, (top_count / total_records) * 100 * 0.4)
        breadth_component = min(25.0, unique / max(1, top_count) * 25)
        urgency_component = min(20.0, (int(urgency.get("high", 0)) / max(1, top_count)) * 20)
        customer_component = min(15.0, (customers / max(1, top_count)) * 15) if customers else 0.0
        score = round(frequency_component + breadth_component + urgency_component + customer_component, 1)
        card = {
            "finding_id": finding.get("finding_id"),
            "theme": theme,
            "problem_statement": f"Customers reported issues related to {theme.casefold()} ({top_count} of {total_records} feedback records; {finding.get('prevalence_pct', 0)}%).",
            "observed_mentions": top_count,
            "unique_wording_patterns": unique,
            "distinct_customers": customers if customers else None,
            "prevalence_pct": finding.get("prevalence_pct", 0),
            "triage_score": score,
            "triage_score_components": {
                "frequency_max_40": round(frequency_component, 1),
                "distinct_wording_max_25": round(breadth_component, 1),
                "high_urgency_language_max_20": round(urgency_component, 1),
                "distinct_customer_max_15": round(customer_component, 1),
            },
            "score_note": "Heuristic triage aid based on observed dataset fields only; not severity, customer value, revenue impact or ROI.",
            "root_cause_hypotheses": hypotheses,
            "evidence_record_ids": record_ids,
            "recommended_checks": finding.get("investigation", {}).get("investigation_checks", []),
            "decision_status": "Needs product-team validation",
        }
        cards.append(card)
        evidence_text = "\n".join(f"- {quote}" for quote in quotes[:5]) or "- No representative quote available."
        hypotheses_text = "\n".join(f"- **Unverified:** {item['hypothesis']}" for item in hypotheses)
        bug_md = f"""# Bug / Problem Investigation Draft: {theme}\n\n**Status:** Draft — validate before filing\n\n## Problem statement\n{card['problem_statement']}\n\n## Evidence\n{evidence_text}\n\n## Candidate explanations (unverified)\n{hypotheses_text}\n\n## Reproduction / investigation checklist\n""" + "\n".join(f"- [ ] {step}" for step in card["recommended_checks"]) + f"\n\n## Source record IDs\n{', '.join(record_ids)}\n\n## Limitations\nThis document is generated from customer feedback only. It does not establish root cause, severity, expected business impact or technical reproducibility."
        prd_md = f"""# Product Requirement Draft: {theme}\n\n**Status:** Discovery draft — requires product and engineering review\n\n## Customer problem\n{card['problem_statement']}\n\n## User need\nAs a customer experiencing {theme.casefold()}, I need the affected workflow to behave reliably so that I can complete my intended task.\n\n## Evidence base\n- Feedback records: {top_count}\n- Distinct wording patterns: {unique}\n- Distinct customers with IDs: {customers if customers else 'Not available'}\n- Source record IDs: {', '.join(record_ids)}\n\n## Proposed acceptance criteria (to refine)\n- The affected workflow completes for the documented reproduction scenarios.\n- Error and performance telemetry is available for the workflow.\n- Regression tests cover the reproduced failure conditions.\n- Existing successful workflows remain unaffected.\n\n## Open questions\n- Which product versions, devices and customer segments are affected?\n- What is the reproducible trigger and expected behaviour?\n- What measurable service-level target should apply?\n\n## Candidate investigation hypotheses (unverified)\n{hypotheses_text}\n\n## Non-goals and limitations\nThis is a discovery draft, not an approved requirement or confirmed technical specification."""
        stories_md = f"""# User Stories: {theme}\n\n1. As an affected customer, I want the {theme.casefold()} workflow to work reliably so I can complete my task.\n2. As a support specialist, I want reproducible steps and source evidence so I can investigate customer reports.\n3. As a product manager, I want telemetry and regression coverage so I can verify whether a change addresses the observed problem.\n\n## Evidence references\n{', '.join(record_ids)}\n\n**Review status:** Draft stories derived from feedback; refine with customer and engineering context."""
        documents.append({"finding_id": finding.get("finding_id"), "theme": theme, "bug_report_markdown": bug_md, "prd_markdown": prd_md, "user_stories_markdown": stories_md})
    return {
        "available": True,
        "method": "evidence_template_generation",
        "documents": documents,
        "prioritised_decision_cards": sorted(cards, key=lambda item: (-item["triage_score"], item["theme"])),
        "limitations": "Generated documents are drafts. Human review is required; candidate root causes are hypotheses, not confirmed diagnoses.",
    }
