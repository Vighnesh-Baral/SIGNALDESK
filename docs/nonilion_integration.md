# Nonilion integration checklist

## Public documentation status (checked 10 November 2026)

Nonilion's public documentation navigation currently labels its API reference as “API Reference Soon.” The public Getting Started and Platform Overview pages describe account setup, rooms, meetings and the platform, but do not publish the custom-agent/Bot API event schema. Consequently, the webhook endpoint in this repository is a normalized contract that needs mapping to the real fields shown in your Nonilion account; it must not be presented as a verified native payload.

Official references:
- https://www.nonilion.com/documentation
- https://www.nonilion.com/documentation/getting-started
- https://www.nonilion.com/documentation/overview
- Support contact listed by Nonilion: hello@nonilion.com

Before final submission, open the Nonilion import builder and verify its available agent import type, webhook destination format, request fields, attachment transfer method, response mapping and required authentication. A screenshot of that screen is enough to implement the account-specific adapter. This archive does not claim a verified live Nonilion import.

## What is implemented in this repository

- `POST /api/nonilion/webhook`: provider-neutral normalized webhook endpoint.
- `GET /api/nonilion/manifest`: advertises the endpoint, supported files, bearer authentication and sample request.
- Attachment support: one CSV, XLSX, PDF, HTML/HTM, TXT, DOCX or JSON file passed as base64 in the normalized request.
- Message-only support: a message without an attachment is treated as one customer complaint and sent through the same classification/evidence/reporting pipeline. The local web UI additionally supports bulk pasted comments.
- Reply shape: `response`, `job_id`, `artifacts`, `format`, structured `ai_breakdown`, optional `trend_analysis`, `problem_clusters`, `segment_analysis`, `decision_summary` and `warnings`.
- Dataset Q&A endpoint: `POST /api/jobs/{job_id}/ask`; the agent can use the `job_id` returned by a completed analysis to ask follow-up questions grounded in the saved dataset. It returns the answer method and cited original records.

**Important:** The INNOVORTEX problem statement mentions custom Python/Node webhook or polling through the Nonilion Bot API, but the brief supplied to the team does not define the exact event/request schema. This repository therefore does not claim that the normalized JSON below is Nonilion's native payload. Map the platform's actual schema in its import configuration or add a small adapter once the platform docs/UI reveal it.

## Normalized request contract

```json
{
  "event_type": "message",
  "conversation_id": "conversation-123",
  "sender_id": "user-123",
  "message": "Analyse this feedback and show the five biggest problems.",
  "attachments": [
    {
      "filename": "customer_feedback.csv",
      "content_base64": "<base64-encoded file bytes>"
    }
  ]
}
```

Endpoint:

```text
POST https://YOUR-PUBLIC-HOST/api/nonilion/webhook
Authorization: Bearer YOUR_SIGNALDESK_API_TOKEN
Content-Type: application/json
```

For a follow-up question about a completed job:

```text
POST https://YOUR-PUBLIC-HOST/api/jobs/{job_id}/ask
Authorization: Bearer YOUR_SIGNALDESK_API_TOKEN
Content-Type: application/json
```

```json
{"question": "What feedback supports the Performance & Speed finding?"}
```

The endpoint retrieves matching saved source records, asks Qwen3 to synthesise an answer from those records, and validates citations against the retrieved record IDs. If it cannot produce a valid cited response, it returns a clearly labelled retrieval-only fallback summary.

## Setup sequence

1. Start SIGNALDESK and verify `GET /api/health` reports `ollama_reachable: true` and `model_available: true`.
2. Set a long random `SIGNALDESK_API_TOKEN` in `.env` and restart the backend.
3. Make the FastAPI service reachable at a stable HTTPS URL. During development a temporary HTTPS tunnel can be used; keep the laptop, internet connection, Ollama and tunnel alive. Do not tunnel port `11434`.
4. Set `PUBLIC_BASE_URL` to the reachable HTTPS base URL and restart the app so returned artifact links are absolute.
5. In Nonilion, select its custom webhook/Python agent/Bot API import route, as permitted by the current platform UI and the competition brief.
6. Configure the webhook destination as `/api/nonilion/webhook`; configure the bearer token in Nonilion's secret/credential facility, not in prompts or source code.
7. Map Nonilion's incoming message text to `message`. A message without an attachment is analysed as one complaint. Map uploaded file content to `attachments[0].filename` and `attachments[0].content_base64`. If the platform sends a file ID or download URL instead, implement a provider-authenticated download step; do not accept arbitrary untrusted URLs.
8. Map the returned `response` to the agent's chat reply and returned `artifacts[].url` values to downloadable files or links.
9. Test with `data/sample/customer_feedback_demo.csv` and the request: "Identify the five most frequent customer problems. Show evidence and generate the reports."
10. Verify within Nonilion that the response and both report links are accessible. Capture this end-to-end test for judging.

## Expected response shape

```json
{
  "response": "Analysis complete: ... Top themes by observed frequency: ...",
  "job_id": "32-character-job-id",
  "artifacts": [
    {"type": "excel", "name": "SIGNALDESK research workbook", "url": "https://YOUR-PUBLIC-HOST/api/jobs/.../report.xlsx"},
    {"type": "pdf", "name": "SIGNALDESK research brief", "url": "https://YOUR-PUBLIC-HOST/api/jobs/.../report.pdf"},
    {"type": "chart", "name": "Theme frequency chart", "url": "https://YOUR-PUBLIC-HOST/api/jobs/.../chart.png"},
    {"type": "product_decision_pack", "name": "Product decision pack (Markdown)", "url": "https://YOUR-PUBLIC-HOST/api/jobs/.../decision-pack.md"}
  ],
  "trend_analysis": {
    "available": false,
    "reason": "No recognised date column was found."
  },
  "ai_breakdown": {
    "qwen3_records": 0,
    "fallback_records": 0,
    "unreported_records": 0,
    "total_records": 0,
    "total_classified": 0,
    "qwen3_percentage": 0.0,
    "fallback_percentage": 0.0
  },
  "warnings": [],
  "format": "signaldesk.nonilion.reply.v1"
}
```

## Acceptance test

- Nonilion can call the webhook with the configured token.
- A supported document (for example PDF or HTML) uploaded through the Nonilion workflow is extracted and processed, not merely discussed.
- The response in Nonilion includes actual dataset counts and top themes.
- Excel and PDF artifact URLs open from the Nonilion workspace/browser.
- The app stays available for the duration of the live demo.
- The demo does not rely on the local Swagger page as the user-facing experience.

## Live mapping still to verify

The exact Nonilion-specific import form, Bot API event fields, attachment transfer mechanism, callback/reply endpoint, and any required signature format must be verified against the account's actual import UI or API documentation. The adapter is intentionally explicit about this gap rather than guessing a vendor schema.
