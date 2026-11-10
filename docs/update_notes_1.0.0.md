# SIGNALDESK v1.0.0 — Customer Intelligence & Product Decision Agent

## Added

- Multi-format feedback ingestion: CSV, XLSX, PDF, HTML/HTM, TXT, DOCX and JSON, plus the existing manual text modes.
- Source-aware extraction metadata for supported formats; scanned PDF OCR is attempted only when Tesseract is installed.
- Similarity-based problem clustering with an optional local Ollama embedding model and a disclosed CPU TF-IDF lexical fallback.
- Customer segmentation using available metadata, with explicit record-level denominator semantics.
- Saved-analysis comparison using theme prevalence and compatible segment dimensions.
- Product decision packs containing investigation cards, candidate root-cause hypotheses, draft bug reports, PRDs, user stories and acceptance criteria.
- Read-only previews and approval-gated create adapters for Jira, Linear, GitHub Issues and Notion.
- Expanded normalized Nonilion manifest/webhook outputs to expose ingestion, clusters, segments and decision summaries.
- Expanded Excel/PDF reporting with problem clusters, segmentation and product-decision drafts.

## Preserved

- Qwen3/Ollama classification and per-record classification provenance.
- VRAM-safe batch/context defaults and fallback classification.
- Evidence-linked findings, trend analysis and Ask SIGNALDESK.
- Existing v0.4 interface structure; the full visual redesign remains v1.1.

## Caveats

- TF-IDF fallback groups similar wording, not necessarily semantically equivalent problems. For embedding similarity, configure an installed Ollama embedding model and benchmark it against the available GPU memory.
- OCR requires the separate Tesseract executable.
- Provider connectors are not live until configured and tested in the user's own workspaces.
- The Nonilion webhook is a normalized contract; native import compatibility is not yet demonstrated.
- Heuristic priority scores are not severity, ROI, revenue, or customer lifetime value. Generated documents and root-cause hypotheses require human review.
