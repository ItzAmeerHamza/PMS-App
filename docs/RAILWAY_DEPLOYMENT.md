# Railway deployment (cloud API)

Written in phase 07 Part A (26 November 2026). **Nothing has been deployed.** Deploying needs the owner's Railway account, an explicit go-ahead, and a check of Railway's current pricing, limits, and commercial-use terms (see `CLAUDE.md`). A free or trial plan is not a reliability guarantee for shop data.

The service is `cloud-api/` in this repository. It receives sync events from shop devices and serves the owner's read-only API. The desktop app never talks to PostgreSQL and never holds its credentials.

## Service settings

| Setting | Value |
| --- | --- |
| Root directory | `cloud-api` |
| Builder | Nixpacks (Python) or a Dockerfile; Nixpacks detects `requirements.txt` |
| Dependency file | `cloud-api/requirements.txt` (runtime only; `requirements-dev.txt` adds pytest and httpx2) |
| Python | 3.12 or newer (developed and tested on 3.14.6) |
| Pre-deploy command | `alembic upgrade head` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"` |
| Health check path | `/health` (returns `{"status": "ok"}`; does not touch the database) |
| Replicas | 1 to start. Push handling is safe with more (per-shop row lock plus unique constraints), but that has only been tested with concurrent requests in one process. |

Railway terminates HTTPS. Clients must use the `https://` URL Railway assigns, or a custom domain.

## PostgreSQL

Add a Railway PostgreSQL service to the same project and reference its URL in the API service:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Railway reference variable). `postgres://` and `postgresql://` are accepted; the app switches the driver to psycopg 3. |

Railway also exposes `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`. The app reads only `DATABASE_URL`.

Turn on Railway's PostgreSQL backups, or schedule `pg_dump`, before real shop data arrives. Shop data is also the source of truth on each shop PC, but the cloud replica holds patient records too and must be protected the same way.

## Environment variables

Example with placeholders only. Never commit real values.

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
OWNER_SESSION_HOURS=12
MAX_EVENTS_PER_PUSH=500
CORS_ORIGINS=https://<your-dashboard>.vercel.app
```

`CORS_ORIGINS` stays empty until the owner dashboard (phase 08) exists. Shop devices do not need CORS.

There are no other secrets in the service. Device secrets and owner passwords are stored hashed in PostgreSQL, never in variables.

## Migrations

```bash
cd cloud-api
alembic upgrade head          # what the pre-deploy command runs
alembic current
```

Migrations live in `cloud-api/alembic/versions/`. The first is `0001_initial`. Never run `alembic downgrade` on production data without a backup.

## First owner

Run once after the first deploy, from a Railway shell (`railway run` or the service's shell), with the password in an environment variable so it is not in shell history:

```bash
OWNER_PASSWORD='<a long password>' python -m app.cli create-owner --email owner@example.com
```

Minimum 12 characters. The first sign-in (the dashboard, or `POST /api/v1/owner/login` then `POST /api/v1/owner/totp`) shows an authenticator key once. Later sign-ins ask for the 6-digit code. Set `COOKIE_SECURE=true` on Railway.

## Registering a shop and its device

1. On the shop PC, open **Sync**. It shows the pharmacy's `public_id`. The shop works before this step.
2. `POST /api/v1/admin/shops` with `{"shop_id": "<that public_id>", "name": "<shop name>"}` and the owner token.
3. `POST /api/v1/admin/shops/<shop_id>/devices` returns a device token once (`pcd_<device id>.<secret>`). Give it to the shop PC securely. Only its SHA-256 hash is stored.
4. On the Sync page, paste the token. Optionally set the cloud address (`https://…`, no password in the URL). The PC stores the token with DPAPI on Windows, or in a mode-0600 file under the data directory on macOS and Linux. It is not shown again.
5. To revoke: `POST /api/v1/admin/devices/<device_id>/revoke`. The shop keeps working offline; the next push is rejected until a new code is pasted.

## Logging

- Access log: method, path, status. Query strings are removed (`_StripQueryString` in `app/main.py`).
- App log (`pharmacare.*` at INFO): one line per push with shop id, event count, and result counts. Apply failures log the shop id and a stack trace, never the event payload.
- Never logged: patient names, phones, allergies, diagnoses, prescription lines, passwords, device or owner tokens, the database URL. `Settings.__repr__` hides the database URL.
- SQLAlchemy runs with `hide_parameters=True`, so database errors do not echo row values.

## Before going live (not done)

- Owner TOTP, HTTP-only cookie sessions, and CSRF protection (phase 08).
- Rate limiting on `/api/v1/owner/login` and `/api/v1/sync/push`.
- Confirm Pakistani health-record and data-protection requirements for storing patient data in the cloud region chosen (see `PRD.md`, compliance note).
- Load test with realistic batch sizes.
