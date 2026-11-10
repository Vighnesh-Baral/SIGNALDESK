# SIGNALDESK v0.4.0 — Evidence-led investigation and interactive research

## Added

- Per-record emotion and language-based urgency signals from Qwen3, with conservative keyword fallback labels. These are language cues, not clinical assessments or verified business severity.
- Evidence-breadth labels per theme based on distinct normalized feedback wording. Labels explicitly are not statistical confidence scores.
- Problem investigation cards that state what customers reported, list checks the product team can run, and identify important unknowns. They do not claim to establish root cause.
- Date-aware emerging-problem detection when a recognised date column exists. It compares adjacent 30-day windows anchored to the latest date in the dataset, and requires at least three dated rows in each period.
- Mixed sentiment signal visibility where both positive and negative/mixed labels appear in a theme. This is not treated as proof of direct contradiction.
- `POST /api/jobs/{job_id}/ask` for questions grounded in saved analysis records. Qwen3 answers must cite IDs present in the retrieved record set; invalid citations trigger a retrieval-only fallback answer.
- UI sections for emotion/urgency signals, date trends, problem investigation cards and Ask SIGNALDESK.
- Excel sheets for Investigation Cards and Trend Analysis; per-record emotion/urgency metadata in exports; corresponding PDF brief sections.
- Nonilion reply metadata now includes the trend-analysis object when available.

## Verification

- 51 automated tests pass in the build environment.
- The offline 200-record smoke test passes and produces Excel, PDF and chart outputs.
- The smoke test deliberately uses keyword fallback. It does not verify live Qwen3 runtime or model quality on the user's machine.

## Limitations

- File uploads remain CSV/XLSX; HTML, PDF, DOCX and OCR ingestion are not part of this release.
- Trend detection requires a recognisable, parseable date column and enough records in both windows.
- Research Q&A uses lexical retrieval over saved record text and theme names, then asks Qwen3 to answer from those retrieved records. It is not embedding-based semantic search.
- Investigation cards provide validation plans, not causal root-cause findings.
- Emotion and urgency are language signals only. Urgency is not a verified incident severity or business-priority score.
- Evidence breadth counts distinct normalized wording patterns. It is not a statistical confidence measure.
- The normalized Nonilion adapter still needs to be mapped and tested against the actual account-specific import interface.
