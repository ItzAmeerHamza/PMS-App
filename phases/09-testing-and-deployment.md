# Phase 09 — Packaging, testing, and deployment

Status: not started.
Depends on: `phases/08-admin-dashboard.md` marked done.

This file has two parts. Complete **Part A**, run the review, and stop. Start **Part B** only when the user explicitly says to continue.

Read `docs/ARCHITECTURE.md`, `docs/PROGRESS.md`, `docs/SYNC_PROTOCOL.md`, and `docs/DECISIONS.md` first.

---

## Part A — Windows installer

### Goal

Package the existing Electron UI, the local FastAPI backend, and database migrations into an installer a shop can run without installing Python, Node.js, or SQLite.

The app must still run offline. Do not deploy Railway or Vercel in this part.

### Backend executable

- A Python launcher starts the existing FastAPI app, resolves the SQLite path in the Windows application-data directory, runs Alembic, starts the sync worker, and binds `127.0.0.1` only.
- Health endpoint stays available.
- Shutdown stops the worker and closes the database.
- Package it with PyInstaller.
- Do not include `backend/data/pharmacy.db` or any file that contains real patients.

### Electron

Update `desktop/electron/main.js` so a packaged build:

1. Finds the backend executable.
2. Starts it as a child process.
3. Uses an ephemeral loopback port.
4. Sends a per-launch secret the backend requires.
5. Waits until health succeeds.
6. Opens the window.
7. Shows a startup error if the backend does not become ready.
8. Terminates that child when Electron quits.

Keep `contextIsolation: true` and `nodeIntegration: false`. The preload API stays limited to what the UI needs, including print and the local API base.

Development on a Mac may keep using `npm run dev` plus `python run.py`. Document both.

### Installer

electron-builder with NSIS. The artifact name should look like `PharmacyManager-Setup-<version>.exe`.

- Installs files, Start menu shortcut, and the bundled runtime.
- Does not bundle production secrets or a populated shop database.
- An upgrade must keep the SQLite file and run migrations.
- Uninstall must not delete the application-data database. Document that choice.
- Document code-signing. Do not claim the binary is signed if it is not.

Each install keeps its own shop `public_id`, manager password, and, after activation, a protected device credential. Ordinary launch does not need the internet.

### Versioning

Record the app version, the local schema revision, and the sync `schema_version` the build speaks. Refuse to start if the database revision is newer than the binary. Do not silently apply a destructive downgrade.

### Tests and scripts

Add repeatable build scripts and document them in `docs/WINDOWS_PACKAGING.md`.

If this machine cannot produce a Windows installer, still commit the scripts and write the exact steps that remain. Do not invent an `.exe` that was not built.

Automated tests:

- Launcher refuses a non-loopback bind.
- Migrations run against a copy of an already-populated SQLite file and keep the rows.
- A second launch reuses `public_id`.
- Existing backend tests still pass.

Manual checklist to record as verified or not verified:

- Fresh install, offline start, manager login, inventory, prescription history, pending outbox rows, restart, upgrade, backup restore, uninstall/reinstall leaving the database in place.

### Part A review, then stop

1. Run the automated tests.
2. Update `docs/WINDOWS_PACKAGING.md` and `docs/PROGRESS.md` with the build result you actually got.
3. Next step, only after the user asks: Part B.
4. Stop.

---

## Part B — Final review

Start only after Part A is marked done and the user says to continue.

### Goal

Review the whole system and write an honest readiness report. Do not claim production-ready unless the critical checks below were actually performed. Do not fabricate test or deploy results. Do not deploy without credentials and an explicit user request.

### End-to-end, synthetic data only

If the environment can run it:

1. Install or start the packaged app.
2. Confirm a stable shop `public_id`.
3. Create inventory, a patient, and a prescription while offline.
4. Confirm the SQLite rows and the matching `sync_outbox` rows.
5. Activate and sync to a non-production PostgreSQL.
6. Confirm PostgreSQL rows.
7. Open the dashboard and confirm the owner can see that shop.

If a step cannot be run, write "not verified" and why.

### Failures to attempt

Offline for the test window, cloud HTTP down, timeout, process kill, restart, duplicate event, out-of-order event, interrupted bootstrap, failed migration on a copy of the database, missing device secret, backup and restore.

Local create and dispense must still work in the offline cases.

### Three shops

Create three synthetic shops. Prove separate SQLite data, credentials that cannot read another shop, independent sync, no primary-key collision in PostgreSQL, and a dashboard shop selector. If this cannot be run, say so.

### Security

Review and fix issues that are contained in this repo:

- Local password hashing and the absence of a hard-coded password.
- Owner MFA, cookie flags, session expiry, rate limit.
- Device secret storage and hashed secrets in PostgreSQL.
- Admin routes versus device routes.
- SQL injection via ORM usage and any raw SQL.
- Electron isolation, loopback bind, per-launch secret.
- Patient data in logs, sync errors, and backups.
- Secrets in git, the installer, and the client bundle.

Record Pakistani privacy, health-record, pharmacy, and retention questions as requiring external verification. Do not invent a legal conclusion.

### Hosts

Update `docs/RAILWAY_DEPLOYMENT.md` and `docs/VERCEL_DEPLOYMENT.md` with the final env var list, migration command, health check, and backup notes. State that commercial use likely needs paid Railway resources and a non-Hobby Vercel plan. Do not deploy unless asked.

### Performance

On synthetic data, note behavior for a large inventory, thousands of patients, long prescription histories, and a few thousand queued events. Add an index only when a real query needs it. Do not add Redis or Kafka.

### Docs to bring in line with the code

- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/SYNC_PROTOCOL.md`
- `docs/LOCAL_DEVELOPMENT.md`
- `docs/RAILWAY_DEPLOYMENT.md`
- `docs/VERCEL_DEPLOYMENT.md`
- `docs/WINDOWS_PACKAGING.md`
- `docs/BACKUP_AND_RECOVERY.md`
- `docs/PROGRESS.md`

### Final report

Write this into `docs/PROGRESS.md` and the session summary:

1. Features that are implemented.
2. Files created or modified in this phase.
3. Automated test commands and results.
4. Windows installer: built or not built, and where.
5. Railway readiness, without claiming a deploy that did not happen.
6. Vercel readiness, same rule.
7. Environment variables and which secrets the operator must supply.
8. Technical risks.
9. Security and compliance items that remain open.
10. An explicit ready or not-ready statement.

## Stop

Do not start a new feature after the report. Do not call the system production-ready to paper over a check that was not run.
