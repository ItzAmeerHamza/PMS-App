# Pharmacy Manager

## Purpose

Build and maintain an offline-first Windows desktop application for independent pharmacy and medical shops in Pakistan. Each shop has one Windows PC and one manager-facing application for inventory, patients, and prescription history. Patients never log in. The owner has a private read-only web dashboard to view complete records from all shops.

## Architecture — non-negotiable

- Desktop: Electron frontend → local Python FastAPI backend → SQLAlchemy → local SQLite.
- Cloud: Railway-hosted FastAPI synchronization and admin API → PostgreSQL on Railway.
- Dashboard: Next.js + TypeScript on Vercel → authenticated Railway API. Browser code never connects directly to PostgreSQL.
- One-way sync: Shop → Cloud only. Cloud data is a reporting replica. SQLite is each shop's operational source of truth.
- Each shop's inventory, patients, prescriptions, and credentials remain isolated. No cross-shop sharing or shop-to-shop communication.
- No patient portal, shared patient directory, multi-PC LAN server, or bidirectional sync in the initial scope.
- The shop must fully function offline, including login, stock updates, patient lookup, and prescription history. Cloud failures must never block or roll back a successful local transaction.
- Dashboard data may be stale while a shop is offline. Always display the last verified sync time.
- Preserve the existing application's frontend framework, working features, and repository structure unless there is a concrete reason to change them.

The desktop UI already uses React and Vite. Keep it. Next.js is only for the new owner dashboard. Billing (sales, voids, and batch allocations) is a working local feature. Keep it. Stock changes from sales and voids must stay auditable.

## This repository

Read these before editing:

- `docs/PROGRESS.md` is the implementation status. Phase prompts that say `docs/IMPLEMENTATION_STATUS.md` mean this file. Do not create a second status document.
- `docs/DATABASE.md` is the database design. Prompts that say `docs/DATABASE_DESIGN.md` mean this file.
- `docs/ARCHITECTURE.md`, `docs/SYNC_PROTOCOL.md`, `docs/DECISIONS.md`, `docs/PRD.md`, and `docs/TESTING.md`.
- The phase prompt under `phases/` named as next in `docs/PROGRESS.md`.

Check that status against the code before starting a phase. If the board and the tree disagree, reconcile `docs/PROGRESS.md` first.

| Path | Role |
| --- | --- |
| `backend/` | Local FastAPI, SQLAlchemy, SQLite. Entry: `backend/run.py`. App: `backend/src/api/main.py`. Models: `backend/src/models.py`. |
| `desktop/` | Electron + React + Vite. API client: `desktop/src/api/client.js`. Translations: `desktop/src/i18n/catalog.js` (English, Urdu, Roman Urdu). |
| `docs/` | Product, architecture, schema, sync, decisions, status, testing. |
| `phases/` | One implementation prompt per phase. |

The live database is SQLite. Development file: `backend/data/pharmacy.db`. Path rules: `backend/src/core/paths.py`. Migrations: `backend/migrations`, applied on API startup by `backend/src/core/migrate.py`, which backs up the file first. A bare `alembic upgrade head` skips that backup. Do not point the live app at MySQL. MySQL in `docker-compose.yml`, `public/back-end/`, and the root `package.json` belongs to an unused store system.

Leave this unused. Do not import it and do not delete it unless the user asks:

- `src/`, `public/`, root `package.json`, `client/my-electron-app/`
- `backend/models.py`, `backend/schemas.py`, `backend/auth.py`, `backend/database.py`, `backend/config.py`, `backend/CONFIG.md`
- `backend/src/doctors/`, `backend/src/appointments/`
- `backend/src/patients/models.py` and `backend/src/core/models.py` (a second schema on the same SQLAlchemy base; importing them clashes with `backend/src/models.py`)
- In `backend/src/core/`, the live modules are `config.py` and the database, path, migration, backup, audit, and transaction helpers. `router.py`, `schemas.py`, `auth.py`, `service.py`, and `models.py` in that folder are old clinic code.

## Transactional sync_outbox — critical invariant

- All business writes go through clearly defined local service methods and SQLAlchemy transaction boundaries.
- For each create, update, or delete, commit both the SQLite business change and its `sync_outbox` event in one transaction. Never emit events only after commit or as an unreliable side effect.
- Every event has a unique stable `event_id`, `shop_id`, `entity_type`, `entity_id`, operation, entity version, schema version, immutable payload, creation timestamp, and local ordering information.
- Outbox records are durable. Events remain pending across offline periods, app crashes, and restarts. Do not delete them or mark them synced before a confirmed cloud acknowledgement.
- Send batches over authenticated HTTPS in a background worker. Never block the Electron UI. Start with a configurable 5-minute interval and batches of 100.
- Retry transient failures with bounded exponential backoff and jitter. Apply request timeouts. Serialize overlapping runs. Report permanent failures for investigation rather than silently dropping events.
- The Railway API must derive the shop identity from its authenticated device credential, not from an arbitrary submitted shop id.
- Cloud ingestion is idempotent. Enforce a unique `(shop_id, event_id)` constraint and apply business changes and processed-event bookkeeping atomically in PostgreSQL. A lost acknowledgement or a repeated request must never duplicate a stock movement or prescription.
- Respect per-entity versions, causal ordering, and dependencies (patient before prescription, prescription before its items). Handle out-of-order events explicitly.
- Use immutable stock movement records for stock changes. Keep `stock_batches` and FIFO in `allocate_stock`. Preserve historical prescriptions. Model deletions as tombstones.
- Support an idempotent, resumable initial snapshot or bootstrap for pre-existing local data without losing writes made during bootstrap.
- Never sync or share a live SQLite database file. Sync structured events and records only.
- Retain acknowledged events according to a documented cleanup policy. Include reconciliation and sync diagnostics.
- Add `public_id` UUIDs beside the existing integer primary keys. Cloud uniqueness for a business row is `(shop_id, public_id)`.
- Do not build the outbox, the cloud API, or the worker before the phase file that owns that work.

## Data and security

- Treat patient identity and prescription history as sensitive. Do not log medical details, credentials, secrets, or full request payloads.
- One persistent shop id per installation. Globally stable entity ids. Scope every cloud business record and query by shop.
- Desktop credentials are per device, revocable, and protected using Windows credential storage. Never embed Railway PostgreSQL credentials or owner secrets in Electron.
- Local manager authentication must work offline. Use modern password hashing. Do not hard-code a manager password. Owner dashboard authentication requires strong sessions, MFA, and server-enforced authorization.
- Use HTTPS for cloud transport. Use loopback `127.0.0.1` with authenticated local communication for Electron and FastAPI. Harden Electron with context isolation and a restricted preload interface.
- Store SQLite outside installation files in a persistent, access-controlled Windows application-data directory. Preserve data across reinstalls, upgrades, and migrations.
- Use Alembic migrations. Back up before risky schema changes. Test encrypted SQLite backups and restore procedures. Cloud sync does not replace local backup.
- Do not delete or recreate `backend/data/pharmacy.db` on startup, and do not wipe its existing rows unless the user asks. This project is still in development: add synthetic test rows to `backend/data/pharmacy.db` whenever sample inventory, patients, prescriptions, or related records are needed. Automated tests still use a temporary SQLite file so they do not erase that development data.
- Do not expose identifiable patient information in public Git repositories, public storage, telemetry, screenshots, fixtures, or demo deployments. Use synthetic test data.
- Do not treat a free hosting plan as a reliability guarantee. Verify Railway and Vercel current quotas, pricing, and commercial-use terms before deployment. Do not invent claims about zero production cost.

## Engineering workflow

- At the start of every task: inspect the repository, read the relevant docs and `docs/PROGRESS.md`, and identify the requested phase. Do not assume an example path or command exists.
- Work on one requested phase only. Do not begin later phases automatically, even if they seem related. If a prerequisite is missing, explain the blocker or make only the smallest necessary supporting change. If a phase file has Part A and Part B, stop after Part A unless the user explicitly says to continue.
- Before edits, summarize the specific implementation plan and the files expected to change. Favor small, reviewable changes over sweeping rewrites.
- Reuse current models, routes, naming, UI components, and conventions.
- Use type hints, Pydantic validation, SQLAlchemy transactions, database constraints, clear error handling, and consistent UTC timestamps.
- Keep domain logic in services, not in Electron components or route handlers. New UI strings go in `desktop/src/i18n/catalog.js` in all three languages.
- Keep secrets in environment variables or protected OS storage, never in source control.
- Avoid unnecessary infrastructure: no Redis, Celery, Kafka, Kubernetes, or microservices without a demonstrated requirement.
- Never delete existing data, reset a database, force-push, deploy, create paid resources, or alter production secrets without explicit permission. Do not commit unless the user asks.
- Do not report untested code as complete. Run the relevant tests, linters, type checks, and builds using commands discovered in the repository. If a tool or environment is unavailable, state exactly what remains unverified.
- At the end of each phase, update `docs/PROGRESS.md` with completed items, changed files, tests and results, decisions, known issues, and the next phase.
- End the response with what changed, tests run and their results, unresolved issues, and whether the phase acceptance criteria are met. Stop at the phase boundary.

## Eight-phase roadmap

The work is split into the files under `phases/`. Status lives only in the board in `docs/PROGRESS.md`; do not track it here.

| Roadmap phase | File |
| --- | --- |
| 1. Repository audit, architecture, and database design. Documentation first. Avoid a major rewrite. | `phases/01-project-foundation.md` |
| 2. Stabilize local offline inventory, prescriptions, authentication, SQLite migrations, and backups. | `phases/02-local-database.md` through `phases/05-prescriptions.md` |
| 3. Transactional `sync_outbox`, immutable event schema, and atomic service-layer event creation. | `phases/06-sync-outbox.md` |
| 4. Railway FastAPI + PostgreSQL: device activation, idempotent ingestion, shop isolation, owner read APIs. | `phases/07-cloud-backend.md` Part A |
| 5. Local background sync worker, retries, initial bootstrap, reconciliation, and desktop sync indicator. | `phases/07-cloud-backend.md` Part B |
| 6. Private owner Next.js dashboard for Vercel, including inventory, patients, prescriptions, owner MFA, and freshness. | `phases/08-admin-dashboard.md` |
| 7. Package Electron and the Python backend with PyInstaller and electron-builder/NSIS. Preserve local data and secure process startup. | `phases/09-testing-and-deployment.md` Part A |
| 8. End-to-end verification, offline and failure testing, security review, deployment runbooks, and a production-readiness assessment. | `phases/09-testing-and-deployment.md` Part B |

## Documentation and acceptance

- Keep `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/SYNC_PROTOCOL.md`, and `docs/PROGRESS.md` accurate.
- Create deployment, packaging, backup, and recovery documentation in the phase that owns that work.
- Sync tests must cover atomic commit and rollback, retries after a lost acknowledgement, deduplication, ordering, cross-shop isolation, and recovery after an offline restart.
- Local tests must cover stock accounting, returning-patient prescription history, offline operation, migrations, backups, and restoration.
- Security tests must cover unauthorized device or shop access and owner-only dashboard access.
- A phase is done only when its defined behavior is implemented, the relevant tests pass, and known limitations are documented. Never fake test results or deployment status.

## Run locally

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

```bash
cd desktop && npm install
npm run dev
```
