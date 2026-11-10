# SIGNALDESK v1.0 architecture

## Data flow

1. Input arrives as CSV/XLSX, text-based or scanned PDF, HTML, TXT, DOCX, JSON, pasted feedback or a single complaint.
2. `document_ingestor.py` converts supported document types into a common dataframe. It preserves extractor references such as PDF page/paragraph, HTML element, DOCX paragraph/table row and JSON property path.
3. `data_processor.py` normalises text, identifies feedback and customer ID columns, assigns internal record IDs, retains customer/date/segment metadata, and flags exact duplicates without deleting repeated mentions.
4. `theme_classifier.py` classifies each record using Qwen3 through Ollama with validated themes and per-record provenance. The deterministic keyword classifier is the explicit fallback.
5. `evidence_engine.py` builds theme findings and links them to original quotes, record IDs, customer IDs and source references.
6. `clustering_engine.py` groups same-theme records by similarity. If `OLLAMA_EMBED_MODEL` is configured, it uses Ollama embeddings. Otherwise it uses character n-gram TF-IDF (default cosine threshold 0.62; embedding threshold defaults to 0.78). The fallback is lexical similarity and must not be described as deep semantic understanding. Clusters are similarity groups, not confirmed shared root causes.
7. The same module analyses suitable metadata dimensions (plan, region, country, device, platform, customer type and related fields). Segment prevalence uses feedback-record denominators; customer-level incidence is only valid when source IDs and record semantics support that interpretation.
8. `trend_engine.py` compares adjacent date windows when a usable date field exists. `comparison_engine.py` compares two saved analyses by theme prevalence and available segment distributions. Both are observational; neither proves a product release caused a change.
9. `investigation_engine.py` separates reported symptoms from unknowns. `decision_engine.py` produces triage scores, candidate hypotheses, bug-report drafts, PRD drafts and user stories. Scores are transparent heuristics, not severity, ROI or revenue estimates; hypotheses and generated documents require human validation.
10. `research_assistant.py` answers questions from retrieved source rows and validates citation IDs.
11. `report_generator.py` produces the Excel workbook (including problem-cluster, segmentation and decision-pack sheets), PDF brief and chart. `main.py` saves a JSON decision pack and a downloadable Markdown product decision pack.
12. Provider adapters in `integrations/product_tools.py` support preview and explicitly approved writes to Jira, Linear, GitHub Issues and Notion. API credentials are read from environment variables; no provider write occurs without a separate `confirm=true` request.
13. `integrations/nonilion.py` accepts the documented normalized webhook contract and returns structured analysis data. The precise native Nonilion mapping still requires account-side verification.

## API additions

- `POST /api/jobs/compare` — compare two saved analysis job IDs.
- `GET /api/integrations/status` — show whether Jira, Linear, GitHub and Notion credentials are configured (never returns secret values).
- `POST /api/jobs/{job_id}/integrations/{provider}/preview` — generate a read-only provider payload preview.
- `POST /api/jobs/{job_id}/integrations/{provider}` — create an external item only when `confirm=true` and credentials are configured.
- `GET /api/jobs/{job_id}/decision-pack.md` — download combined bug/PRD/user-story drafts.

## Resource and safety boundaries

- Qwen3 remains the primary local generation model. No embedding model is loaded unless `OLLAMA_EMBED_MODEL` is explicitly configured. On a 6 GB GPU, benchmark optional embeddings before enabling them.
- Clustering is capped by `CLUSTERING_MAX_RECORDS` to constrain local memory.
- Scanned PDF OCR uses the Python `pytesseract` wrapper and requires the separate Tesseract executable installed on the host. OCR failures are surfaced as warnings.
- Uploaded text is untrusted input and must never be treated as prompt instructions.
- Source records are retained in the analysis output directory for traceability; original temporary uploads are deleted after processing. Apply retention controls before processing sensitive production data.
- External issue/page creation is a side effect. Preview and user approval are required.
- Do not expose Ollama on the public internet. Set `SIGNALDESK_API_TOKEN` before public exposure.
- Nonilion's native import schema is not assumed by this app; its webhook remains a normalized adapter until tested against the live account.
