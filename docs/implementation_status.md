# SIGNALDESK v1.0.0 implementation status

## Implemented in this release

### Unified ingestion
- CSV and XLSX structured uploads.
- PDF text extraction with optional scanned-page OCR when the separate Tesseract executable is installed and discoverable.
- HTML/HTM extraction with script/style/navigation removal and review/comment block heuristics.
- TXT paragraph extraction, DOCX paragraph/table extraction, and JSON recursive feedback extraction.
- Source references retained where extractable: original row, PDF page, HTML element, DOCX paragraph/table, or JSON property path.
- Manual bulk paste and single-complaint entry remain supported.

### Customer and problem intelligence
- Qwen3/Ollama classification with per-record model/fallback provenance; deterministic fallback remains available.
- Exact duplicate flags preserve original mentions.
- Similarity problem clustering within classified themes. Method and threshold are reported per result.
  - With `OLLAMA_EMBED_MODEL`, local Ollama embeddings are used.
  - Without it, character n-gram TF-IDF measures wording similarity. This is explicitly not deep semantic equivalence.
- Customer segmentation across supported metadata fields (e.g. plan, region, device, customer segment, country and industry). Rates use feedback-record denominators unless records have been independently normalised to one per customer.
- Emotion and urgency language signals, evidence breadth, mixed sentiment indicators, evidence-linked investigation cards, and date-aware trend detection.
- Comparison of two saved analyses using counts and prevalence per dataset, with segment comparisons where possible. Observational comparison does not prove release causality.
- Interactive Ask SIGNALDESK answers grounded in retrieved source records, with record-ID citation validation.

### Product decision support
- Investigation/decision cards with transparent heuristic triage components.
- Candidate root-cause hypotheses are labelled unverified.
- Draft bug reports, PRDs, user stories and proposed acceptance criteria.
- Combined Markdown decision pack, Excel workbook and PDF brief.

### Workflow adapters
- Read-only payload preview and explicit-confirmation create adapters for Jira, Linear, GitHub Issues and Notion.
- Provider credentials are read from environment variables and are not returned by status endpoints.
- Normalized Nonilion webhook/manifest contract can receive supported file formats and return summary data.

## Verification performed in the build environment
- 65 automated tests pass.
- Python compilation passes.
- Offline 200-record synthetic smoke test passes; six blank rows are removed, 12 exact duplicate mentions are retained, ten themes are identified, and Excel/PDF/chart outputs are generated.
- The smoke test uses the deterministic keyword fallback, not live Qwen3. Its historical 99.5% agreement with synthetic QA labels is not a real-world model accuracy estimate.

## Not verified / external prerequisites
- Live Qwen3 classification throughput and output quality on the user's RTX 4050 must be verified on that laptop.
- Scanned-PDF OCR requires both the Python dependencies and the separate Tesseract executable; OCR on an actual scanned sample was not verified in this build environment.
- Embedding-based clustering requires an installed Ollama embedding model configured in `OLLAMA_EMBED_MODEL`. The default remains CPU TF-IDF wording similarity.
- Jira, Linear, GitHub and Notion adapters have preview/confirmation logic, but actual writes require the user's credentials, workspace permissions and account-side tests. No external issue/page was created in this build.
- The current Nonilion route is a normalized webhook contract, not a verified native import. Native schema mapping and a live Nonilion-to-SIGNALDESK-to-artifact round trip remain for the later integration milestone.
- Public deployment still requires HTTPS, a configured bearer token, protected artifact/result access, and a deployment decision for the local Qwen3 dependency. Do not expose the user's Ollama service directly.

## Deliberately deferred
- v1.1 frontend redesign. This release keeps the existing v0.4 interface with only functional input changes needed for multi-format uploads.
- Native Nonilion account integration and live judging round trip are deferred to the subsequent integration milestone.

# v1.1 frontend experience update

- Public landing page served at `/` with scroll-based product story and capability sections.
- Separate application workspace served at `/app`.
- Light premium SaaS interface: warm ivory, lavender, periwinkle and pale cyan accents; restrained Liquid Glass surfaces; responsive modular dashboard; accessible controls and reduced-motion support.
- Inline SVG illustrations and light CSS animations are used where they clarify the feedback-to-insight workflow. No stock image dependency was added.
- Frontend update preserves the v1.0 APIs and analysis pipeline.
