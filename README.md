# SIGNALDESK v1.3.0

**Evidence-First Customer Research & Product Decision Agent**  
*Turn messy customer feedback into source-traceable product investigations and review-ready decisions.*

SIGNALDESK ingests structured and unstructured customer feedback, classifies problems with local Ollama or a configured hosted LLM provider, calculates counts in Python, preserves evidence references, records analysis metadata in PostgreSQL, stores files under a configurable storage root, compares datasets, and produces draft product decision artifacts. Numerical metrics are deterministic. AI-generated explanations, hypotheses, prioritisation aids and documents are labelled for human review.

## Workspace experience

- Public scroll-based product landing page at `/` with product story, capabilities, evidence standards and workspace calls to action.
- Separate application workspace at `/app` with a light premium SaaS layout, modular dashboard panels, restrained Liquid Glass surfaces and subtle motion.
- Workspace navigation: Overview, Analyse feedback, Investigations, Customers, Trends & comparison, Ask SIGNALDESK, and Reports & decisions.
- Select or create a research workspace when submitting feedback; recent analyses can be listed and restored from persistent history using the configured bearer token.
- Actual analysis results populate workspace metrics, visual theme distribution, AI provenance, emotion signals, trend analysis, problem investigations, clusters, customer segments, evidence, Q&A and report links.
- Responsive layout and `prefers-reduced-motion` support. Inline SVG illustrations avoid reliance on stock images or remote image assets.

## v1.0 capabilities

### Input and document extraction
- File uploads: CSV, XLSX, PDF, HTML/HTM, TXT, DOCX and JSON.
- Manual bulk paste and single-complaint submission remain supported.
- PDF text extraction uses PyMuPDF. Scanned pages attempt OCR through `pytesseract`; the separate Tesseract executable must also be installed and discoverable on PATH.
- HTML removes script/style/navigation chrome and extracts review/comment-like blocks where detectable. Otherwise, it falls back to main/article paragraphs and list items.
- DOCX reads paragraphs and tables. JSON supports arrays/objects with common feedback keys such as `feedback`, `comment`, `review`, `message`, `text`, `content` and `description`.
- Extractor source references are preserved where possible (PDF page/paragraph, HTML element, DOCX paragraph/table row, JSON property path).

### Customer and problem intelligence
- Provider-neutral classification into controlled customer problem themes, with per-record model/fallback provenance. Local Ollama/Qwen3, Groq, OpenRouter and custom OpenAI-compatible endpoints are supported.
- Exact duplicate flags retain all submitted mentions.
- Similarity clustering groups records within the same classified theme. If `OLLAMA_EMBED_MODEL` is set to an installed Ollama embedding model, vectors are used. Otherwise, character n-gram TF-IDF runs locally on CPU. TF-IDF is lexical wording similarity, not deep semantic understanding. The method is shown in the result.
- Customer segmentation recognises metadata such as plan, region, country, device, platform, customer segment/type and industry. Counts use feedback-record denominators; they are not automatically customer incidence rates.
- Emotion/urgency language cues, evidence breadth, conflicting sentiment signals and evidence-linked investigation cards.
- Date-aware emerging problem detection and `POST /api/jobs/compare` for before/after analysis of two saved analyses. Comparison differences are observational and do not prove that a release caused them.

### Product decision support
- Transparent heuristic triage scores with their individual components. These are not severity, ROI, revenue, or customer lifetime value.
- Candidate root-cause hypotheses labelled as unverified.
- Bug/problem report drafts, PRD drafts, user stories and proposed acceptance criteria. These are templates derived from source themes and require product/engineering validation.
- Grounded Ask SIGNALDESK Q&A with citations restricted to retrieved source records.

### Persistence, deployment and security
- SQLAlchemy models and Alembic migration for projects, datasets, analyses, themes, evidence and report metadata. A Default Workspace is seeded automatically; authenticated APIs can create workspaces and scope analysis history. Local development defaults to SQLite; hosted deployment can use PostgreSQL (e.g. Supabase).
- Configurable file roots for uploads, processed data, generated reports and temporary files. Render deployment blueprint mounts a Persistent Disk at `/var/data`.
- Retention cleanup for source uploads, generated artifacts and temporary files; defaults are 30 days, 90 days and 24 hours respectively.
- Bearer-token protection for analysis, history, result retrieval, Q&A, integration actions and report downloads. Public health and Nonilion manifest routes expose configuration status only, not secret values.
- `/api/health/ready` checks storage, configured inference and the database when `DATABASE_REQUIRED=true`.

### Reports and integrations
- Excel: Overview, Theme Findings, Evidence Register, Investigation Cards, Trend Analysis, Problem Clusters, Customer Segments, Decision Pack and Processed Feedback.
- PDF research brief, theme chart and combined Markdown product decision pack.
- Provider adapters for Jira, Linear, GitHub Issues and Notion. Payload previews are read-only. Actual writes require credentials and an explicit `confirm=true` request. Live account credentials are not included and provider writes have not been tested against your workspaces.
- Normalized Nonilion webhook contract supports the file formats above. The exact native Nonilion agent-import/request schema still needs to be mapped and verified in the user's account.

## Requirements

- Python 3.11 or newer (Python 3.12 recommended).
- Ollama installed and running with `qwen3:4b` pulled locally when using local inference. Hosted inference does not require Ollama on the server.
- Windows PowerShell, macOS or Linux.
- Tesseract OCR executable only if scanned PDF OCR is needed.

## Setup (Windows PowerShell)

```powershell
.\setup_signaldesk.ps1
.\run_signaldesk.ps1
```

Open `http://127.0.0.1:8000` for the product landing page, then select **Open workspace** or visit `http://127.0.0.1:8000/app`. API docs: `http://127.0.0.1:8000/docs`.

Equivalent manual setup:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
alembic upgrade head
Copy-Item .env.example .env  # only if .env does not exist
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep Ollama running separately. Confirm the model with `ollama list`.

## Configuration

Edit `.env` (never commit or share it). Core local-model settings:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT_SECONDS=240
OLLAMA_BATCH_SIZE=5
OLLAMA_NUM_CTX=4096
OLLAMA_NUM_BATCH=128
OLLAMA_NUM_PREDICT=512
OLLAMA_KEEP_ALIVE=5m
```

Optional embedding-based clustering:

```dotenv
# Leave blank to use CPU character n-gram TF-IDF similarity.
OLLAMA_EMBED_MODEL=
SIMILARITY_THRESHOLD=0.62
OLLAMA_EMBED_SIMILARITY_THRESHOLD=0.78
CLUSTERING_MAX_RECORDS=2500
PDF_OCR_ENABLED=true
```

Only set `OLLAMA_EMBED_MODEL` after pulling a compatible embedding model in Ollama.

Hosted LLM configuration (keep keys in `.env` locally or Render environment variables in production):

```dotenv
LLM_PROVIDER=groq
LLM_API_KEY=your-groq-api-key
LLM_MODEL=your-selected-groq-model
LLM_FALLBACK_PROVIDER=openrouter
LLM_FALLBACK_API_KEY=your-openrouter-api-key
LLM_FALLBACK_MODEL=your-selected-openrouter-model
```

The primary provider is attempted first. A configured fallback is attempted only for provider capacity/rate-limit, transport or server-availability failures. Invalid credentials and invalid model responses are surfaced rather than silently retried against another provider. Local mode remains `LLM_PROVIDER=ollama`.

### Deployment (Render + PostgreSQL)

A starter Render Blueprint is included in `render.yaml`. It configures a paid web service with a 1 GB Persistent Disk mounted at `/var/data`, runs Alembic migrations before deployment, and starts FastAPI with Uvicorn. Review the plan, region and disk size before provisioning; the Render Persistent Disk feature is not available on the free web-service tier, and the disk is attached to a single service instance.

1. Create a PostgreSQL project (Supabase is one supported managed provider) and copy its PostgreSQL connection URI. Use the provider's recommended connection pooler/connection string appropriate for your deployment.
2. Create or connect the GitHub repository in Render and select the Blueprint. Supply `DATABASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_API_KEY`, `LLM_FALLBACK_MODEL` and `PUBLIC_BASE_URL` when prompted. Render generates `SIGNALDESK_API_TOKEN` from the Blueprint configuration; store it securely.
3. Confirm `SIGNALDESK_STORAGE_ROOT=/var/data`, `DATABASE_REQUIRED=true` and `ALLOW_UNAUTHENTICATED_LOCAL=false` are set in the deployed environment.
4. After deployment, test `/api/health`, `/api/health/ready`, authenticated uploads, analysis history and report downloads. Do not expose database or provider credentials in the browser.
5. Back up PostgreSQL separately. Supabase Free projects can pause after inactivity and have quota/backup limitations; confirm the current provider plan before using it for production customer data.

The Blueprint is a deployment template, not a provisioned environment. Actual hosting, database connectivity, hosted inference and public HTTPS must be verified with your own provider accounts and credentials. See [`docs/deployment_v1.3.md`](docs/deployment_v1.3.md) for a configuration checklist. On a 6 GB GPU, benchmark it alongside Qwen3 before enabling it; the project does not load an embedding model by default.

### Optional external integrations

```dotenv
# Jira Cloud
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=
JIRA_ISSUE_TYPE=Task

# Linear
LINEAR_API_KEY=
LINEAR_TEAM_ID=

# GitHub Issues (owner/repository)
GITHUB_TOKEN=
GITHUB_REPOSITORY=owner/repository

# Notion
NOTION_TOKEN=
NOTION_PARENT_PAGE_ID=
NOTION_DATABASE_ID=
NOTION_TITLE_PROPERTY=Name
NOTION_VERSION=2022-06-28
```

Provider secrets are read from environment variables and are never returned by the health/status endpoint. For Jira, ensure the token can create issues in the selected project; for Linear, the key must access the target team; for GitHub, the token needs repository Issues write permission; for Notion, share the target page/database with the integration and configure its actual title property name. Preview payloads before making any external write.

Set `SIGNALDESK_API_TOKEN` and `PUBLIC_BASE_URL` before public exposure. Do not expose the Ollama port publicly. Analysis, history, result and artifact endpoints require a bearer token when the application is in public mode. The frontend download helper attaches the token from its API token field.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Service health, supported formats and integration configuration status |
| `GET` | `/api/health/ready` | Deployment readiness: storage, configured inference and required database connectivity |
| `GET` | `/api/projects` | List workspaces available to the shared API token |
| `POST` | `/api/projects` | Create a workspace |
| `GET` | `/api/analyses` | Authenticated recent analysis metadata/history; optional `project_id` filter |
| `POST` | `/api/analyze` | Upload a supported feedback file |
| `POST` | `/api/analyze/text` | Analyse bulk pasted feedback or one complaint |
| `GET` | `/api/jobs/{job_id}` | Retrieve a completed analysis |
| `POST` | `/api/jobs/{job_id}/ask` | Ask a question grounded in a saved analysis |
| `POST` | `/api/jobs/compare` | Compare two completed analyses |
| `GET` | `/api/integrations/status` | Show configured product integrations |
| `POST` | `/api/jobs/{job_id}/integrations/{provider}/preview` | Preview Jira/Linear/GitHub/Notion payload |
| `POST` | `/api/jobs/{job_id}/integrations/{provider}` | Create an external item with `confirm=true` |
| `GET` | `/api/jobs/{job_id}/report.xlsx` | Download research workbook |
| `GET` | `/api/jobs/{job_id}/report.pdf` | Download research brief |
| `GET` | `/api/jobs/{job_id}/chart.png` | Download theme chart |
| `GET` | `/api/jobs/{job_id}/decision-pack.md` | Download bug/PRD/user-story draft pack |
| `GET` | `/api/nonilion/manifest` | Normalized agent integration metadata |
| `POST` | `/api/nonilion/webhook` | Normalized Nonilion message/file event |

All analysis and external-integration POST operations are protected by bearer token when `SIGNALDESK_API_TOKEN` is configured. Unauthenticated access is allowed only for localhost development when no public base URL is configured. The normalized Nonilion event format is not a verified native Nonilion schema; follow `docs/nonilion_integration.md`. Project/workspace isolation is by explicit `project_id` only; v1.3 uses one shared bearer token and does not provide user accounts or role-based permissions.

## Tests and smoke test

```powershell
python -m pytest -q
python scripts/smoke_test.py
```

The offline smoke test uses the keyword fallback on a synthetic 200-record dataset and validates generated reports. Its 99.5% agreement with synthetic labels is a controlled QA check, not real-world accuracy. Live hosted/local model inference, OCR on actual scanned PDFs, and all provider writes must be tested in their target environments.

## Sample data

`data/sample/customer_feedback_demo.csv` contains synthetic feedback plus blank rows for data-quality testing. `data/sample/ground_truth.json` is a QA reference and must not be uploaded during a customer-facing demo. Disclose that the dataset is synthetic. Regenerate with `python scripts/generate_demo_data.py`.
