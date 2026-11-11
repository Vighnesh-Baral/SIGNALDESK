# SIGNALDESK v1.3 deployment guide

This guide covers the deployment configuration added in v1.3. It is a setup guide, not evidence that external services have already been provisioned or connected.

## Architecture

- **Render Web Service:** FastAPI application and static frontend.
- **Render Persistent Disk:** uploaded source files, processed CSV files, reports, charts and temporary files, mounted at `/var/data`.
- **PostgreSQL:** analysis metadata, analysis history, findings, evidence references and report metadata. Local development defaults to SQLite.
- **LLM provider:** Ollama locally; Groq, OpenRouter or a custom OpenAI-compatible hosted endpoint in production.

A Default Workspace is seeded automatically. Authenticated clients can create named workspaces through `POST /api/projects` and scope history with `GET /api/analyses?project_id=<id>`. The database stores metadata and structured records, not the raw uploaded file bytes. Durable file content remains on the configured filesystem storage root.

## Local development

1. Create and activate a Python virtual environment.
2. Install `requirements.txt`.
3. Copy `.env.example` to `.env` if `.env` does not exist.
4. Leave `DATABASE_URL` blank to use the local SQLite database at `data/signaldesk.db`.
5. Set `LLM_PROVIDER=ollama` and make sure Ollama is running with the configured model available.
6. Run `alembic upgrade head`, then start the app using `uvicorn app.main:app --reload` or the existing PowerShell launcher.

Local directories remain under the project root unless the `SIGNALDESK_*_DIR` variables or `SIGNALDESK_STORAGE_ROOT` are set.

## PostgreSQL setup

1. Create a PostgreSQL database with a managed provider such as Supabase.
2. Copy the provider's PostgreSQL connection URI. Ensure it requires TLS (`sslmode=require`) when the provider instructs you to do so.
3. Configure `DATABASE_URL` in the deployment environment. SQLAlchemy normalises `postgres://` and `postgresql://` URLs to the `postgresql+psycopg://` driver.
4. Set `DATABASE_REQUIRED=true` for production.
5. Run `alembic upgrade head`. The Render Blueprint runs this as its pre-deploy command.
6. Confirm `/api/health/ready` reports a ready application and `/api/analyses` works with a bearer token.

The included initial migration creates the v1.3 schema. Future schema changes should be introduced as new Alembic revisions; do not edit an already-applied migration in a live database.

## Hosted inference

The service accepts `groq`, `openrouter` and `openai_compatible` as hosted providers. Provider model IDs and free-tier quotas change; choose a currently available model in the provider dashboard and configure the exact model ID.

Example primary Groq + secondary OpenRouter configuration:

```dotenv
LLM_PROVIDER=groq
LLM_API_KEY=<Groq API key>
LLM_MODEL=<available Groq model ID>
LLM_FALLBACK_PROVIDER=openrouter
LLM_FALLBACK_API_KEY=<OpenRouter API key>
LLM_FALLBACK_MODEL=<available OpenRouter model ID>
LLM_TIMEOUT_SECONDS=120
LLM_MAX_TOKENS=2048
```

The fallback provider is attempted only when the primary returns a rate-limit/quota response, transport failure, timeout or server-side availability error. Invalid credentials, invalid model configuration and malformed model output are not silently retried. Keyword fallback within the classifier remains the final safe degradation path.

Keep API keys only in server-side environment variables. Never place them in HTML, JavaScript, browser-visible settings or Git-tracked files. Free API tiers have dynamic quotas and are not an uptime guarantee. Review each provider's data handling terms before sending real customer feedback.

## Render Persistent Disk

The included `render.yaml` is a starter Blueprint. Review the selected plan, region and disk size before creating the service. The Blueprint configures a single web service, a 1 GB disk mounted at `/var/data`, the readiness route, Alembic pre-deploy migration and environment-variable prompts.

Set or verify:

```dotenv
SIGNALDESK_STORAGE_ROOT=/var/data
DATABASE_REQUIRED=true
ALLOW_UNAUTHENTICATED_LOCAL=false
SIGNALDESK_API_TOKEN=<strong random secret>
PUBLIC_BASE_URL=https://<your-render-service-host>
RETAIN_SOURCE_UPLOADS=true
SOURCE_UPLOAD_RETENTION_DAYS=30
ARTIFACT_RETENTION_DAYS=90
TEMP_RETENTION_HOURS=24
```

The Render Persistent Disk requires a paid service and is attached to one service instance. Do not scale this configuration horizontally without redesigning file storage. Persistent disks also affect deployment/zero-downtime characteristics; consult current Render documentation before changing plans or instance counts.

## Access control

- Configure `SIGNALDESK_API_TOKEN` before public exposure.
- Set `ALLOW_UNAUTHENTICATED_LOCAL=false` in production.
- Analysis, history, result retrieval, Q&A, comparison, product-integration actions and report downloads require `Authorization: Bearer <token>`.
- `/api/health`, `/api/health/ready` and `/api/nonilion/manifest` are public operational/metadata endpoints. They do not return credentials.
- The workspace includes an API token field. Authenticated report downloads use that token to fetch a file instead of embedding credentials in download URLs.
- Keep the Supabase connection string and LLM provider keys on the server only.

## File retention and backups

Default retention is:

- source uploads: 30 days;
- generated analysis artifacts and their analysis-history rows: 90 days;
- temporary files: 24 hours.

Configure the corresponding `SOURCE_UPLOAD_RETENTION_DAYS`, `ARTIFACT_RETENTION_DAYS` and `TEMP_RETENTION_HOURS` variables. Cleanup runs at application startup and before each new user analysis request. Expiring an analysis removes its stored files and associated metadata; expiring only a source upload clears its database path reference but preserves the analysis and generated reports.

A Persistent Disk is not a backup. Export/backup PostgreSQL through the selected database provider and periodically copy important generated reports to a separate backup location. Verify restore procedures before using the app with important customer data.

## Deployment verification checklist

1. `/api/health` returns version `1.3.0` and the configured inference provider.
2. `/api/health/ready` returns HTTP 200.
3. An unauthenticated upload request returns 401 (or 503 if the token is not configured).
4. An authenticated CSV upload completes analysis and creates report files.
5. The analysis appears in `/api/analyses`.
6. An authenticated report download succeeds.
7. Restart/redeploy the service and confirm that files remain on `/var/data` and database history remains in PostgreSQL.
8. Test primary provider throttling with a configured fallback, and test both provider outages and quota exhaustion.
9. Confirm `SIGNALDESK_API_TOKEN`, provider keys and `DATABASE_URL` are not present in browser assets or logs.

## Known boundaries

- The code package cannot provision Render, Supabase, or provider accounts; credentials and live connectivity must be configured by the repository owner.
- Projects/workspaces are grouped by explicit project ID under a shared bearer token. User accounts, per-user project ownership and role-based access control are not included.
- The deployment template has not been run against the user's Render account in this build.
- Provider free tiers and exact model identifiers change. The owner must select currently available models and review the provider terms/quotas.
- The Nonilion endpoint remains a normalized adapter contract. Native Nonilion request/response mapping and the end-to-end office integration require the official Bot API specification and a live test.
