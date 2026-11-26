# Phase 01 — Project foundation

Status: not started.
Depends on: nothing.
You are a senior software architect. Execute this phase only, then stop.

## Read first

- `docs/PRD.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/SYNC_PROTOCOL.md`
- `docs/DECISIONS.md`
- `docs/PROGRESS.md`
- `docs/TESTING.md`

Those files are a baseline from 26 November 2026. They are not a blank template, and they are not permission to rewrite the app. Your job is to check them against the repository and correct anything that is wrong or stale.

## Repository facts

The live app is `backend/` (FastAPI, SQLAlchemy, SQLite) and `desktop/` (Electron, React, Vite).

Do not treat these as the product:

- Root `package.json`, `src/`, and `public/` (unused "My Store" system).
- `backend/auth.py`, `backend/database.py`, `backend/config.py`, `backend/CONFIG.md`.
- `backend/src/doctors/`, `backend/src/appointments/`, `backend/src/core/models.py`, `backend/src/patients/models.py`.

`backend/src/patients/models.py` declares a second `patients` table on the same SQLAlchemy base as the live `Patient` in `backend/src/models.py`. Do not import it.

The running API is `backend/src/api/main.py`. It already has auth, pharmacies, inventory, patients, prescriptions, a shop dashboard, and billing.

## Tasks

1. Inspect the repository. Confirm the frontend, backend, models, Electron-to-FastAPI path, auth, and what is actually implemented.
2. Update `docs/ARCHITECTURE.md` so the current-versus-target section matches the code you just read. Include the ASCII diagram. Fix any mistake in the baseline.
3. Update `docs/DATABASE.md` so every live table, relationship, and missing table matches `backend/src/models.py`.
4. Update `docs/PROGRESS.md` with what exists, what is missing, and what you could not verify by running the app.
5. Leave `docs/SYNC_PROTOCOL.md` and `docs/DECISIONS.md` in place. Change them only to correct a factual error. Do not weaken one-way sync, the read-only dashboard, or the rule to keep billing.
6. Note reusable code and missing pieces:
   - Reuse the service modules, routers, React pages, and `desktop/src/api/client.js`.
   - Missing: Alembic, UUIDs, stock movements, outbox, worker, cloud API, owner dashboard, PharmaCare installer, tests.
7. Record migration and data-loss risks, especially integer ids, startup `create_all`, hard deletes, and the seeded manager account.

## Out of scope

- Do not implement the cloud API, sync worker, admin dashboard, or Windows packaging.
- Do not add `sync_outbox` yet.
- Do not delete or replace working code.
- Do not create `docs/DATABASE_DESIGN.md` or `docs/IMPLEMENTATION_STATUS.md`. The canonical files are `docs/DATABASE.md` and `docs/PROGRESS.md`.
- Do not start phase 02.

## Done when

- The docs describe the code that is actually in the tree.
- No feature work landed.
- `docs/PROGRESS.md` says this phase is done and names the next file: `phases/02-local-database.md`.

## Review, then stop

Before you finish:

1. Re-read the docs you changed and confirm every claim against a file path.
2. Confirm you did not modify application behavior.
3. Update `docs/PROGRESS.md` with completed work, anything you could not run, and the next step.
4. Write a short report: existing structure, what to reuse, what is missing, the recommended sequence (the phase board), and data-loss risks.
5. Stop. Do not begin phase 02.
