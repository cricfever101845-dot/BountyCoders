# Bounty Coders deployment guide

This repository contains a Flask app with server-rendered Jinja pages. It has no separate JavaScript build step, so both Render services are **Web Services**. The frontend service serves the pages and static assets, then forwards `/api/*` requests server-to-server to the backend. The browser stays on one origin, and both services share the same signed-session secret and Supabase database.

The selected free plans are suitable for a student demo. They do not provide production-level availability: Render free web services sleep after 15 minutes without inbound traffic and can take about a minute to wake. Render's free instance hours are shared by the workspace. Supabase Free has a 500 MB database quota, can pause after a week of low activity, and does not provide downloadable automatic backups. See [Render free services](https://render.com/docs/free), [Supabase project pausing](https://supabase.com/docs/guides/platform/free-project-pausing), and [Supabase pricing](https://supabase.com/pricing). If students rely on this service continuously, select paid plans before launch.

## Before you begin

- Push the repository to GitHub on the `main` branch.
- Create a free Supabase account and a Render account.
- If you have a local `bountycoders.db` with existing accounts or progress, migrate it **before** the first Render deployment. The repository checkout inspected for this preparation did not contain a database file.

## 1. Create the Supabase project

1. In Supabase, create a project named `Bounty Coders`.
2. Choose the **Singapore** region to match the Render services' region and keep app-to-database latency low. Region cannot be changed after project creation.
3. Set and save the database password. This password is separate from Supabase account login.
4. Open **Connect** in the project dashboard. Select **Session pooler** and copy its PostgreSQL connection string. Render's IPv4-only network works with the shared session pooler; the connection string normally uses port `5432` and a username like `postgres.<project-ref>`. Do not substitute the transaction pooler.
5. The app enforces encrypted PostgreSQL connections with `DB_SSLMODE=require`. No Supabase browser key, service-role key, or Supabase Auth setup is needed.

The app creates the schema on service startup using the safe, repeatable migration in `migrate_db.py`. It creates the account, course, progress, bounty, attempt, leaderboard, and execution-quota tables, then seeds the four courses and 60 question groups when the database is empty. It never drops tables. Row-level security is enabled without browser-facing policies; application database access stays on the server.

After deployment, confirm the database is ready at `https://<backend-host>/ready` and confirm the tables appear in **Table Editor**. `/health` is the Render health check and does not depend on the database. `/ready` is the separate database check.

### Import existing SQLite data (only if you have a local database)

The importer makes a timestamped SQLite backup first, preserves IDs and password hashes, verifies row counts and progress relationships, and refuses to write into a destination that already has application records. It does not delete or modify the SQLite source. Run it from the repository folder, using the Supabase session-pooler connection string:

```powershell
py -m pip install -r requirements.txt
$env:DATABASE_URL = 'PASTE_THE_SUPABASE_SESSION_POOLER_CONNECTION_STRING'
$env:DB_SSLMODE = 'require'
py migrate_sqlite_to_postgres.py 'C:\path\to\bountycoders.db'
```

Inspect the reported backup path and copied row counts before deploying. Run this against a fresh Supabase project before the Render services create the starter question bank. If the importer reports that the destination is occupied, do not delete those rows; create a new empty Supabase project or review the records manually. Free Supabase projects do not include downloadable automatic backups, so keep the local backup and make regular exports.

## 2. Create the Render services

1. In Render, choose **New → Blueprint** and connect the GitHub repository.
2. Select the `main` branch and the repository's root `render.yaml`.
3. Review the Blueprint. It creates exactly two free Python web services in Singapore:
   - `bounty-coders-frontend`
   - `bounty-coders-backend`
4. The Blueprint generates one shared `BOUNTY_SECRET_KEY` for both services. For each service, enter the same Supabase session-pooler connection string as `DATABASE_URL` when Render asks for the value. Enter the OnlineCompiler REST API key only for the backend service when Render requests it; keep it private.
5. Sync the Blueprint and wait for both services to deploy. Both use the same build and start commands; startup applies the idempotent database migration before Gunicorn starts.
6. In each service's **Environment** page, check that `DATABASE_URL` is present and matches exactly. Do not add Supabase credentials to the HTML, JavaScript, or static files.
7. Check each service's assigned URL. The Blueprint uses these expected URLs:
   - Frontend: `https://bounty-coders-frontend.onrender.com`
   - Backend: `https://bounty-coders-backend.onrender.com`

   If Render assigns a different hostname, update `BACKEND_URL` on the frontend service to the actual backend HTTPS URL, and update `FRONTEND_URL` on both services to the actual frontend HTTPS URL. These values must match exactly; save and redeploy both services.

## 3. Exact Render settings

Both services have the same repository root and Python production server settings. There is no static publish directory and no SPA rewrite rule because Flask serves the templates and resolves direct page URLs.

| Setting | Frontend | Backend |
| --- | --- | --- |
| Render type | Web Service | Web Service |
| Name | `bounty-coders-frontend` | `bounty-coders-backend` |
| Runtime | Python 3.14.10 | Python 3.14.10 |
| Region | Singapore | Singapore |
| Plan | Free | Free |
| Root directory | `.` (repository root) | `.` (repository root) |
| Build command | `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| Start command | `python migrate_db.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --graceful-timeout 30 --access-logfile - --error-logfile -` | Same command |
| Health check path | `/health` | `/health` |
| Static publish directory | Not applicable | Not applicable |

The one-worker, four-thread setup keeps each free instance's database connections conservative. Connections are opened per request, closed at request teardown, and retried briefly on initial connection errors. The frontend's `BACKEND_URL` uses the public HTTPS service URL because free web services cannot receive private-network traffic from another free web service.

## 4. Environment variables

`render.yaml` sets the non-secret values and creates the shared `BOUNTY_SECRET_KEY`. Set the database connection string in **both** services. Keep the shared secret identical on both services; use the Render-generated shared environment group.

### Frontend service

- `ENVIRONMENT=production`
- `SERVICE_ROLE=frontend`
- `BOUNTY_SECRET_KEY` — generated by the shared Render environment group
- `DATABASE_URL` — Supabase PostgreSQL **Session pooler** string
- `FRONTEND_URL` — exact public HTTPS URL of `bounty-coders-frontend`
- `BACKEND_URL` — public HTTPS URL of `bounty-coders-backend`
- `API_PROXY_TIMEOUT_SECONDS=90`
- `DB_SSLMODE=require`
- `BC_RUNNER_MODE=disabled`

### Backend service

- `ENVIRONMENT=production`
- `SERVICE_ROLE=backend`
- `BOUNTY_SECRET_KEY` — the same shared Render-generated secret
- `DATABASE_URL` — the same Supabase Session pooler string
- `FRONTEND_URL` — public HTTPS URL of `bounty-coders-frontend`; this is the allowed browser origin
- `DB_SSLMODE=require`
- `BC_RUNNER_MODE=disabled`
- `CODE_EXECUTION_ENABLED=true`
- `CODE_EXECUTION_PROVIDER=onlinecompiler`
- `ONLINECOMPILER_API_KEY` — private key from the provider's dashboard; never put it on the frontend
- `CODE_EXECUTION_TIME_LIMIT=8` seconds (maximum 30)
- `CODE_EXECUTION_REQUEST_TIMEOUT=40` seconds
- `CODE_EXECUTION_PER_HOUR=30` per user
- `CODE_EXECUTION_PER_DAY=100` per user
- `CODE_EXECUTION_PER_MONTH=80000` total application runs

`CORS_ALLOWED_ORIGINS` is not required: the browser calls the frontend origin, and the frontend forwards API requests to the backend. The backend accepts state-changing browser requests only from `FRONTEND_URL`. Flask sessions use HTTP-only, Secure, SameSite=Lax cookies. The frontend forwards the session cookie over the server-to-server request, and the services share its signing secret.

Matching sample files are in `config/frontend.env.example` and `config/backend.env.example`.

## 5. Verify the deployment

After both services are live:

1. Open `/health` on the frontend and backend. Each should return `{"status":"ok"}`.
2. Open `/ready` on the backend. It should return `{"status":"ready","database":"connected"}`.
3. Confirm the Supabase tables exist. For a fresh database, `courses` should contain 4 rows and `questions` should contain 60 rows. The migration also creates persistent `difficulty_attempts`, `difficulty_best`, and `execution_requests` tables.
4. On the frontend, create an account, log out, sign in, open the course list, and start a course. Confirm progress resumes after a refresh.
5. Check that a request to a protected API without a login returns HTTP 401.
6. Confirm a cross-origin browser request to the backend is rejected. Normal browser API calls go through the frontend proxy.
7. Use a phone-sized viewport and a desktop browser to review the pages and static assets.

Python, Java, and C source is sent from the backend to OnlineCompiler.io's server-side sync API using compiler IDs `python-3.14`, `openjdk-25`, and `gcc-15`; the key is never sent to the browser. Their API documentation describes per-run gVisor isolation, no network access, memory/process limits, and a maximum 30-second runtime. The app sets an 8-second program limit, 20 KB source cap, bounded output, 30 runs/hour and 100/day per user, and an 80,000-run monthly application cap. The provider's free plan currently advertises 100,000 runs/month, so the app cap leaves headroom. Check current limits before launch: [API and compiler docs](https://onlinecompiler.io/docs/run-code), [compiler IDs](https://onlinecompiler.io/docs/compilers), and [provider limits](https://onlinecompiler.io/docs/limits).

`Run Code` never scores or changes hearts. `Submit Answer` runs code on the provider and grades it server-side. Provider/configuration/quota failures return without a heart or bounty change; a submitted program that actually compiles/runs and produces an error, times out, or returns the wrong output counts as an incorrect answer. This provider stores code, input, output, errors, timing, and IP-address execution history for 365 days according to its [privacy policy](https://onlinecompiler.io/privacy). Do not submit secrets or personal data in code or program input. Its security page says it has no SOC 2 or ISO 27001 certification and has not published a third-party audit; review that statement against your institution's policy before using it with student work. See [provider security details](https://onlinecompiler.io/security).

The game starts each difficulty attempt with three hearts; each correct answer adds 5M/10M/15M berries on Easy/Medium/Hard, and each incorrect submission removes 1M without allowing a negative total. At zero hearts the active difficulty attempt ends and its bounty is reset to zero. Earlier completed difficulties and personal best records remain. Leaderboards rank each user's best completed difficulty score; Overall sums the three bests. Hearts, retries, progress, and best scores are stored in Supabase, so rotation or page refresh cannot alter the score.

## 6. Free-tier limits and backups

- Render free web services sleep after 15 minutes of inactivity, may restart, and use an ephemeral filesystem. The app stores no user uploads or runtime data there; account and course progress live in Supabase. Static images, videos, CSS, and fonts are committed assets.
- The frontend and backend are two free services. Render's free instance-hours are shared by the workspace; monitor included usage and bandwidth. Do not add a keep-alive ping.
- Supabase Free may pause after a week with too little database activity. It includes 500 MB of database size and does not include downloadable automatic backups. Keep off-site database exports and retain the original SQLite backup when importing.
- A pause or cold start can delay requests. Retry the page or action after the service wakes. If students depend on consistent availability, use paid plans; no paid resource is enabled by this Blueprint.
- There is no persistent user file storage requirement in this application, so Supabase Storage is not configured.

## 7. Updates and troubleshooting

- Push changes to `main`; Render's default Blueprint auto-deploy rebuilds and deploys the services.
- **Database password/authentication failure:** recopy the Session pooler URI from Supabase's Connect panel and update both `DATABASE_URL` values. URL-encode special characters in a manually constructed password.
- **Database SSL error:** keep `DB_SSLMODE=require`; use the Supabase connection string and hostname exactly as provided.
- **Frontend API returns 503:** verify `BACKEND_URL`, confirm the backend service is live, then retry after its free instance wakes.
- **Code run says service is not configured:** add a valid `ONLINECOMPILER_API_KEY` to the backend's private Render environment, then restart that service. Never add it to frontend variables or static assets.
- **Code service returns 429:** the application per-user rate limit or provider capacity/account limit was reached; wait and retry. The app does not deduct a heart for provider-side failures.
- **Backend rejects a request with 403:** set `FRONTEND_URL` to the frontend's exact HTTPS origin, with no path or trailing slash.
- **Render health check fails:** confirm the start command binds Gunicorn to `0.0.0.0:$PORT` and review startup logs for missing required variables or failed migrations.
- **A free Supabase project is paused:** resume it from the Supabase dashboard, then retry `/ready`.
- **Data migration reports occupied destination:** stop and review the destination; the importer will not merge into existing user records.

Before any manual database migration, make an export. Supabase recommends regular off-site logical backups for free projects; see [Supabase database backups](https://supabase.com/docs/guides/platform/backups).

## Render Blueprint validation

The Blueprint follows Render's current web-service, environment-group, free-plan, and health-check fields. With Render CLI 2.7.1 or later installed, validate it from the repository root:

```sh
render blueprints validate render.yaml
```

The Render Dashboard also validates the Blueprint during sync. Do not sync until validation succeeds and each `DATABASE_URL` value is ready.

### Free-tier cold-start recovery

The browser checks the backend database-readiness endpoint through the frontend before sending API requests. When the backend is asleep, the interface shows a startup message and waits up to 110 seconds for a valid ready response. Checks are short, bounded, and shared between concurrent requests on the same page. There is no background keep-alive. Once ready, the requested API action is sent. Safe reads can be retried; answer submissions and other writes are never automatically replayed. If an answer response is lost, reload saved progress before trying again. The frontend's `/api/service_ready` proxy maps to backend `/ready` without forwarding session credentials. If this endpoint never reports readiness, inspect the Render backend logs and usage limits rather than increasing request timeouts indefinitely.
