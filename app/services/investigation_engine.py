"""Create evidence-grounded problem investigation cards without inventing root causes."""
from __future__ import annotations

INVESTIGATION_CHECKS = {
    "Crashes & Stability": [
        "Reproduce the reported action using the affected workflow.",
        "Capture application logs, device/browser details and steps to reproduce.",
        "Compare crash frequency across app versions and environments if those fields are available.",
    ],
    "Performance & Speed": [
        "Benchmark the affected screen or workflow under representative data volumes.",
        "Measure client rendering and API response time separately.",
        "Compare reports by device, network or account segment when those fields are available.",
    ],
    "Reporting & Export": [
        "Reproduce the export with the same filters, date range and data volume.",
        "Compare generated file contents with the user's selected options.",
        "Check whether failures are limited to particular formats or report sizes.",
    ],
    "Navigation & Usability": [
        "Identify the task customers were trying to complete.",
        "Run a short task-based usability review and observe where users hesitate.",
        "Check whether labels, menus and navigation paths match customer language.",
    ],
    "Authentication & Account Access": [
        "Reconstruct the sign-in, reset or verification sequence.",
        "Check authentication logs and email/code delivery timing.",
        "Compare affected accounts by identity provider or account state if available.",
    ],
    "Billing & Subscription": [
        "Reconcile the customer statement with invoice, payment and subscription events.",
        "Check whether the issue concerns billing presentation, payment execution or plan state.",
        "Do not alter billing records until the underlying event is verified.",
    ],
    "Integrations": [
        "Check connector authentication, permissions and field mapping.",
        "Compare sync/API responses and timestamps with the affected provider.",
        "Confirm whether the problem is isolated to one integration or multiple providers.",
    ],
    "Data Sync & Reliability": [
        "Trace the same record ID and sync timestamps across affected clients.",
        "Check whether updates are delayed, dropped or overwritten.",
        "Compare behaviour across devices and network conditions if available.",
    ],
    "Feature Requests": [
        "Restate the requested capability as a user need, not a proposed solution.",
        "Check how many distinct customers describe the same unmet need.",
        "Validate roadmap fit, expected benefit and implementation effort with the product team.",
    ],
    "Positive Feedback": [
        "Identify the workflow or experience customers praise.",
        "Check which product behaviours should be preserved during future changes.",
        "Look for recurring praise across distinct customers, not only repeated copies.",
    ],
    "Other / Unclear": [
        "Request one concrete example and the affected workflow.",
        "Ask what the customer expected to happen and what happened instead.",
        "Do not assign a technical cause until the feedback is more specific.",
    ],
}


def build_investigation_card(finding: dict) -> dict:
    """Describe what the dataset supports and what remains unknown."""
    theme = str(finding.get("theme", "Other / Unclear"))
    unique_count = int(finding.get("unique_normalized_feedback_count", 0))
    if unique_count <= 1:
        evidence_breadth = "Limited"
        breadth_note = "Based on one distinct wording pattern; treat this as an initial signal."
    elif unique_count <= 4:
        evidence_breadth = "Early signal"
        breadth_note = "Several distinct wording patterns support this theme; further validation is useful."
    elif unique_count <= 9:
        evidence_breadth = "Recurring signal"
        breadth_note = "Multiple distinct feedback patterns recur in this dataset."
    else:
        evidence_breadth = "Broad signal"
        breadth_note = "Many distinct feedback patterns contribute to this theme. This is not a statistical confidence score."

    sentiment = finding.get("sentiment_breakdown", {})
    positive = int(sentiment.get("positive", 0))
    negative = int(sentiment.get("negative", 0))
    mixed = int(sentiment.get("mixed", 0))
    mixed_experience = positive > 0 and negative > 0 or mixed > 0
    known_statement = (
        f"{finding.get('mention_count', 0)} retained feedback records were assigned to {theme}. "
        f"The records include {unique_count} distinct normalised wording patterns."
    )
    return {
        "status": "Needs investigation",
        "what_customers_report": known_statement,
        "evidence_breadth": evidence_breadth,
        "evidence_breadth_note": breadth_note,
        "mixed_experience_signals": mixed_experience,
        "sentiment_note": (
            "Both positive and negative/mixed sentiment labels appear in this theme. Review the linked quotes; "
            "this is a sentiment mix, not proof that customers contradict one another."
            if mixed_experience else "No positive-versus-negative mix was detected in the available sentiment labels."
        ),
        "what_is_not_established": [
            "The underlying technical or organisational root cause.",
            "The actual severity, financial impact or number of affected active customers.",
            "Whether the issue is limited to a particular version, device or customer segment unless those fields are present.",
        ],
        "investigation_checks": INVESTIGATION_CHECKS.get(theme, INVESTIGATION_CHECKS["Other / Unclear"]),
        "recommended_next_step": finding.get("suggested_next_step", "Collect more specific feedback."),
    }
