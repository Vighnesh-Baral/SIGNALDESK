# SIGNALDESK v1.3.0 — Deployment and persistence foundation

## Added
- Provider-neutral LLM service supporting local Ollama, Groq, OpenRouter and custom OpenAI-compatible hosted chat APIs.
- Optional secondary hosted LLM provider used for quota/rate-limit, connectivity, timeout and provider availability failures.
- Provider provenance recorded per classified feedback record and in grounded Q&A response method.
- SQLAlchemy persistence models and initial Alembic migration for projects, datasets, analyses, themes, evidence and report metadata. Includes a default workspace and authenticated project create/list endpoints plus project-scoped history.
- Local SQLite default and PostgreSQL support through `DATABASE_URL` and `psycopg`.
- Configurable upload, processed, output and temporary storage roots.
- Render Blueprint with `/var/data` Persistent Disk, environment configuration, health check, pre-deploy migration and Uvicorn command.
- Configurable retention cleanup for source uploads, analysis artifacts and temporary files.
- Authenticated analysis history endpoint and bearer-token protection for result, Q&A, comparison, integration and artifact endpoints.
- Readiness health endpoint, security headers and deployment guide.

## Changed
- Successful source uploads are retained by default for a configurable period (30 days by default); failed uploads are removed.
- Frontend AI provenance and report-download handling now support hosted inference and authenticated downloads without changing the visual design.
- Health and report output describe a generic configured AI model rather than assuming Qwen3 is the only provider.

## Operational notes
- Set `SIGNALDESK_STORAGE_ROOT=/var/data` when the Render Persistent Disk is mounted at `/var/data`.
- Set `DATABASE_URL`, `DATABASE_REQUIRED=true`, `LLM_PROVIDER`, provider API keys/model IDs, `SIGNALDESK_API_TOKEN`, `PUBLIC_BASE_URL` and `ALLOW_UNAUTHENTICATED_LOCAL=false` in the server environment.
- Configure an API provider's currently available model IDs; free-tier availability and rate limits can change.
- Render Persistent Disk requires a paid web service and supports only one service instance for this design.
- Live Render, PostgreSQL and hosted LLM verification requires the account owner credentials and was not performed as part of preparing the source package.
- Nonilion remains a normalized webhook adapter pending the official native Bot API specification and live pairing test.

## Verification snapshot
- Automated test suite: 83 passed, 0 failed.
- Offline 200-record synthetic smoke test: passed.
- Local SQLite Alembic migration and Render Blueprint validation: passed in the build environment.
- Live Render, Supabase/PostgreSQL, and hosted provider connectivity still require owner credentials and a deployed environment.
