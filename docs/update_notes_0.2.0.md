# SIGNALDESK 0.2.0 — update notes

## Changes in this archive

- Added a browser-side AI classification breakdown: Qwen3 records, keyword-fallback records, unreported method count, and Qwen3 share of all valid records.
- Added an evidence explorer showing representative original quotes, record IDs, source rows, optional customer IDs, and duplicate-retained status.
- Added warnings to the result view so fallback use and processing issues are visible.
- Corrected the Nonilion reply contract: file-analysis replies now include a top-level `ai_breakdown` object and optional `warnings`, matching the manifest.
- Added the AI method split to the Excel Overview and PDF brief.
- Hardened unauthenticated access: it is allowed only for explicitly enabled localhost development. A non-local host or a configured public base URL requires `SIGNALDESK_API_TOKEN`.
- Added a health field indicating whether `PUBLIC_BASE_URL` is configured.
- Updated the offline smoke test and regression tests.

## Verification in this build environment

- 23 automated tests pass.
- Python compilation passes.
- Frontend JavaScript syntax check passes.
- Offline 200-record smoke test passes: six blank rows removed, 12 duplicate mentions retained, 10 themes identified, Excel/PDF/chart generated. The fallback matched 199/200 labels in the synthetic QA fixture; this is not a real-world accuracy estimate.

## Still not verified

- Live Qwen3 classification on the user's laptop. The archive can report per-record Qwen3/fallback provenance, but the model must be exercised locally and the resulting counts inspected.
- Native Nonilion import compatibility. The webhook is a normalized adapter; Nonilion's currently public documentation labels its API reference as “API Reference Soon”. Confirm the account-specific import fields and attachment mechanism before claiming a live integration.
- Public deployment, TLS/tunnel configuration, persistent storage and live artifact opening from Nonilion.

## Required environment configuration before public use

- Set a strong `SIGNALDESK_API_TOKEN`.
- Set `PUBLIC_BASE_URL` to the exact HTTPS origin reachable from Nonilion.
- Do not expose Ollama port `11434`.
- Do not distribute `.env` or real customer data in the hackathon archive.
