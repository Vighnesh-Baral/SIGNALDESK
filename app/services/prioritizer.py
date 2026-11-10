"""Rank findings by frequency and attach clearly labelled follow-up suggestions."""
from __future__ import annotations

from app.services.investigation_engine import build_investigation_card

FOLLOW_UP_SUGGESTIONS = {
    "Crashes & Stability": "Reproduce the reported action and collect application logs, device details and steps to reproduce.",
    "Performance & Speed": "Benchmark the affected screen or workflow under representative data volumes and network conditions.",
    "Reporting & Export": "Verify export formats, filters, date ranges and generated file contents against the user's selected options.",
    "Navigation & Usability": "Run a short task-based usability review to identify where users get lost or need extra steps.",
    "Authentication & Account Access": "Review the sign-in, reset and verification journey, including email or code delivery timing.",
    "Billing & Subscription": "Reconcile the affected invoice, payment event and subscription state before changing billing records.",
    "Integrations": "Check connector authentication, permissions, field mapping and sync/API responses with the affected provider.",
    "Data Sync & Reliability": "Trace sync timestamps and record IDs across clients to identify where updates stop appearing.",
    "Feature Requests": "Validate demand with affected users and assess scope, effort and fit with the product roadmap.",
    "Positive Feedback": "Identify which workflow created the positive experience and preserve it during future product changes.",
    "Other / Unclear": "Request one concrete example, the affected workflow and the expected result before prioritising.",
}


def prioritize_findings(findings: list[dict]) -> list[dict]:
    """Order by observed frequency; add suggestions without inventing a priority score."""
    ranked = sorted(
        findings,
        key=lambda item: (-int(item.get("mention_count", 0)), str(item.get("theme", "")).casefold()),
    )
    for rank, finding in enumerate(ranked, start=1):
        finding["priority_rank"] = rank
        finding["priority_basis"] = (
            "Relative frequency in the uploaded dataset; severity and revenue impact were not independently measured."
        )
        finding["suggested_next_step"] = FOLLOW_UP_SUGGESTIONS.get(
            str(finding.get("theme", "")), FOLLOW_UP_SUGGESTIONS["Other / Unclear"]
        )
        finding["suggestion_note"] = "Analyst suggestion based on theme; validate against product context and source evidence."
        finding["investigation"] = build_investigation_card(finding)
    return ranked
