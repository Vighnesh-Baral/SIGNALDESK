# SIGNALDESK v0.3.0 — Multi-mode feedback input

## New submission methods

- **Upload file:** CSV and XLSX remain supported, including optional feedback-column and customer-ID-column mapping.
- **Paste feedback:** Users can paste multiple comments. A blank line or a line containing `---` separates records; single newlines remain within the same comment so multi-line support messages are preserved. Maximum: 500 records and 500,000 characters per manual submission.
- **Single complaint:** The entire text entry is treated as one feedback record, including multi-paragraph complaints.
- Manual submissions can optionally include a customer ID. For bulk paste, the supplied ID applies to every pasted comment.

## Unified processing

All three methods are converted to a dataframe and use the same cleaning, duplicate detection, Qwen3/fallback classification, evidence aggregation, prioritisation and report-generation workflow. Manual source rows are numbered from 1. File source rows continue to reflect spreadsheet rows beginning at 2.

## File selection and retention

- Added a visible Remove file button and a Clear inputs action.
- After a successful file analysis, the browser file input is cleared.
- The backend removes the original uploaded working file after analysis completes, including error paths. It retains generated reports and the processed-feedback export in the job output folder.
- Nonilion base64 attachments are also removed from temporary upload storage after processing.

## API

- Added `POST /api/analyze/text` with JSON fields `mode`, `feedback_text`, and optional `customer_id`.
- `mode` accepts `paste` or `single`.
- Existing `POST /api/analyze` remains the CSV/XLSX endpoint.
- Nonilion message-only events now use the same single-complaint analysis pipeline.

## Current file-format scope

File upload remains CSV/XLSX only. PDF, DOCX, HTML, TXT and JSON file extraction are not included in this release. Text can be pasted directly without uploading a file.
