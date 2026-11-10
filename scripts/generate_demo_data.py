"""Regenerate the deterministic synthetic SIGNALDESK demonstration dataset."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sample"
OUT.mkdir(parents=True, exist_ok=True)

CATALOG = [
    ("Crashes & Stability", "Application", [
        "The application crashes when I export a report", "The mobile app freezes after I open the dashboard",
        "The app closes unexpectedly when I save my work", "I get kicked out of the application while editing a project",
        "The application becomes unresponsive when I upload a large file", "The desktop app crashes when I switch workspaces",
        "The app freezes after I attach a document", "My session closes unexpectedly during an edit",
        "The application stops responding when I open a large customer list", "The mobile client keeps freezing after sign in",
    ]),
    ("Performance & Speed", "Dashboard", [
        "The dashboard takes too long to load in the morning", "Switching between pages is painfully slow",
        "Search results take several seconds to appear", "The application feels sluggish when many records are open",
        "Loading the analytics screen is much slower than before", "The analytics summary screen takes a long time to open",
        "Filtering a large list makes the page lag", "The app is slow when I search across projects",
        "The dashboard spinner stays on screen for too long", "Pages respond slowly when several team members are online",
    ]),
    ("Reporting & Export", "Reporting", [
        "The exported spreadsheet is missing several columns", "I cannot choose a date range before exporting a report",
        "The PDF report layout breaks across pages", "Report exports fail when I select more than one team",
        "I need a scheduled weekly report export", "The CSV download contains the wrong date format",
        "The export button does not include archived records", "I cannot export the chart with its data table",
        "The report downloads with blank rows at the bottom", "The monthly report is missing the summary section",
    ]),
    ("Navigation & Usability", "Interface", [
        "It is difficult to find the settings page", "The navigation labels are confusing for a new user",
        "There are too many clicks to reach saved views", "The filter controls are hard to understand",
        "The layout on the main screen is cluttered", "I cannot tell which menu contains team permissions",
        "The page labels do not explain what each option does", "Finding the activity history takes several steps",
        "The settings menu is difficult to navigate", "The dashboard buttons are not clearly labelled",
    ]),
    ("Authentication & Account Access", "Accounts", [
        "The password reset link expires before I can use it", "I cannot sign in even though my password is correct",
        "The two factor authentication code is not accepted", "Invited team members cannot activate their accounts",
        "I need a way to change the account email address", "The login page rejects my valid credentials",
        "The account activation email never arrives", "I am locked out after resetting my password",
        "The sign in code arrives after it has expired", "Our new teammate cannot access the invited account",
    ]),
    ("Data Sync & Reliability", "Data", [
        "Changes made on my laptop do not appear on the web app", "Some records disappear after the page refreshes",
        "The latest uploaded data is not syncing to the dashboard", "I see duplicate records after synchronisation",
        "Edits are not saved reliably when the connection drops", "The dashboard is showing yesterday's data",
        "Updates from the mobile app are missing on desktop", "Some customer records disappear after saving",
        "The background sync stops before all rows are uploaded", "My latest changes are not saved after reconnecting",
    ]),
    ("Integrations", "Integrations", [
        "The Slack integration disconnects every few days", "The API documentation does not explain pagination clearly",
        "I cannot connect our CRM to the application", "The calendar integration is not importing new events",
        "Please add an integration for our project management tool", "The CRM connector fails to authenticate",
        "Our calendar connection stopped updating appointments", "The API response is missing the owner field",
        "I cannot link the application to our support platform", "The Slack connection needs to be authorised again each week",
    ]),
    ("Billing & Subscription", "Billing", [
        "I was charged twice for this month's subscription", "The invoice does not show our company tax details",
        "I cannot find where to change the subscription plan", "The payment failed but my card shows a pending charge",
        "Please explain how to cancel the subscription", "Our invoice has the wrong billing address",
        "The monthly plan price changed without an explanation", "I need a receipt for the last payment",
        "The billing page still shows an unpaid invoice after payment", "Please clarify the renewal date for our annual plan",
    ]),
    ("Feature Requests", "Product", [
        "Please add keyboard shortcuts for common actions", "I would like to save custom dashboard views",
        "It would help to have a dark mode option", "Please add bulk editing for customer records",
        "I wish there was an option to assign comments to teammates", "Could you add a calendar view for upcoming tasks",
        "We need an option to export saved filters", "Please add custom fields to the customer profile",
        "I would like to pin frequently used reports", "It would help to schedule reminders from the task page",
    ]),
    ("Positive Feedback", "General", [
        "The new dashboard is easy to use and looks great", "Your support team was helpful and resolved my issue quickly",
        "The reporting workflow is much better after the latest update", "I love how quickly I can find customer information",
        "The application has made our weekly review much easier", "The new search feature works perfectly for our team",
        "The onboarding guide was clear and helpful", "The updated interface looks excellent",
        "I appreciate how easy it is to organise projects", "The recent improvements made the app much more useful",
    ]),
]
COUNTS = {
    "Crashes & Stability": 35,
    "Performance & Speed": 30,
    "Reporting & Export": 28,
    "Navigation & Usability": 25,
    "Authentication & Account Access": 18,
    "Data Sync & Reliability": 18,
    "Integrations": 14,
    "Billing & Subscription": 12,
    "Feature Requests": 10,
    "Positive Feedback": 10,
}
CONTEXTS = [
    "during a morning session", "during an afternoon session", "after lunch",
    "near the end of the workday", "during a weekday session", "during a weekend session",
    "while preparing a client deliverable", "during a team review", "while working remotely",
    "during a scheduled work session", "at the start of the workday",
]
DEVICES = [
    "a laptop", "a desktop computer", "a tablet", "a phone", "a shared workstation",
    "a home office setup", "a remote session", "a browser window", "a standard work session",
    "a new device", "a wired office network", "a wireless office network", "a personal device",
]

items = []
for theme, area, templates in CATALOG:
    for local_index in range(COUNTS[theme]):
        base = templates[local_index % len(templates)]
        context = CONTEXTS[(local_index * 3 + len(theme)) % len(CONTEXTS)]
        device = DEVICES[(local_index * 7 + len(theme)) % len(DEVICES)]
        # Distinct contexts reduce accidental exact duplicates but keep the issue category intact.
        feedback = base + ". We noticed it " + context + " while using " + device + "."
        items.append((theme, area, feedback))

# Inject twelve intentional exact duplicates (six percent of the dataset).
for index in range(12):
    duplicate_source = index * 7
    duplicate_target = 100 + index * 3
    items[duplicate_target] = items[duplicate_source]

rows = []
truth = {}
for sequence, (theme, area, feedback) in enumerate(items, start=1):
    customer_id = f"CUS-{sequence:04d}"
    created_at = (date(2026, 8, 1) + timedelta(days=(sequence * 3) % 90)).isoformat()
    rows.append({
        "Customer_ID": customer_id,
        "Created_At": created_at,
        "Product_Area": area,
        "Feedback": feedback,
        "Source": ["In-app survey", "Support ticket", "Customer interview follow-up"][sequence % 3],
        "Synthetic_Label": "SYNTHETIC_DEMO_DATA",
    })
    truth[customer_id] = {"expected_theme": theme, "source_text": feedback}

for empty_index in range(6):
    rows.insert(25 + empty_index * 27, {
        "Customer_ID": f"EMPTY-{empty_index + 1}", "Created_At": "2026-10-01",
        "Product_Area": "Unknown", "Feedback": "", "Source": "Synthetic quality test",
        "Synthetic_Label": "SYNTHETIC_DEMO_DATA",
    })

with (OUT / "customer_feedback_demo.csv").open("w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

(OUT / "ground_truth.json").write_text(json.dumps({
    "description": "Synthetic-only QA labels. Never upload this file to SIGNALDESK during the demo.",
    "expected_non_empty_records": len(truth),
    "expected_theme_counts": dict(Counter(theme for theme, _area, _feedback in items)),
    "records": truth,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {len(rows)} rows; {len(truth)} non-empty synthetic records.")
