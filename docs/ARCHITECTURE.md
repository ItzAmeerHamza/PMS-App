# Technical architecture

Baseline inspection: 26 November 2026. Verified against the repository in phase 01 on 26 November 2026, including a run of the local API against a scratch SQLite file. Do not rebuild the application from this document.

## What exists today

The live application is:

```
backend/     Python FastAPI + SQLAlchemy + SQLite
desktop/     Electron + React (Vite) talking to http://127.0.0.1:8000/api/v1
```

`README.md` states that `src/`, `public/`, and the root `package.json` store-system (React 16, Redux, Sequelize, MySQL, electron-builder "My Store") are leftover and unused. `client/my-electron-app/` is another unused Electron stub. A second unused clinic scaffold also sits inside `backend/`:

| Unused file or folder | Note |
| --- | --- |
| `backend/auth.py`, `backend/config.py`, `backend/database.py`, `backend/models.py`, `backend/schemas.py`, `backend/CONFIG.md` | Older top-level clinic app. `CONFIG.md` describes PostgreSQL and JWT, which the live app does not use. |
| `backend/src/core/auth.py`, `core/models.py`, `core/router.py`, `core/schemas.py`, `core/service.py` | Clinic users and JWT. `core/auth.py` imports `jose` and `passlib`, which are not in `requirements.txt`, so importing it fails. |
| `backend/src/doctors/`, `backend/src/appointments/` | Clinic modules. Not mounted. |
| `backend/src/patients/models.py` | Second `patients` table on the live `Base`. Not imported. |

`backend/src/core/config.py` and `backend/src/core/database.py` **are** live: they hold settings, the engine, `SessionLocal`, `get_db`, and `ensure_schema`. The rest of `backend/src/core/` is not.

`backend/src/api/main.py` is the live app. It mounts these routers under `/api/v1`:

| Router | Routes |
| --- | --- |
| `auth` | `POST /auth/login`, `GET /auth/me`, `POST /auth/logout` |
| `pharmacies` | list, get, create, update |
| `inventory` | medicines list/get/create/update/delete, CSV import, add batch, adjust batch, expiring list |
| `patients` | list/search, get, create, update, delete |
| `prescriptions` | list, get, create, dispense, cancel |
| `dashboard` | shop summary, with optional `day_start` for "today's sales" in local time |
| `billing` | sales list with date range and summary, get, create, void |

Startup (`lifespan` in `main.py`, since phase 02) runs `run_migrations()` (Alembic `upgrade head`, with a backup first when a migration is pending). If `PHARMACARE_DEMO_DATA=1`, it then seeds sample data into an empty pharmacy table. Nothing else writes on startup. Before phase 02 it ran `create_all`, `ALTER TABLE` patches, two sample-data backfills, and re-created a default manager.

```
Shop PC (development, two processes started by hand)

  Electron (desktop/electron/main.js)
    contextIsolation: true
    nodeIntegration: false
    dev: loads http://127.0.0.1:5173 (Vite)
    packaged: loads desktop/dist/index.html
    preload exposes apiBase, print, printPrescription
    ipc "pharmacare:print" -> silent A4 print to the default printer
         |
         | HTTP JSON, Bearer token, http://127.0.0.1:8000
         v
  FastAPI (backend/run.py, 127.0.0.1:8000, reload on, CORS "*")
    auth middleware on /api/v1/* except /auth/login and /auth/setup
    service modules under backend/src/*/service.py
    every write: business_transaction (row + audit commit together)
         |
         v
  SQLite  path from backend/src/core/paths.py
    dev: backend/data/pharmacy.db; installed: %LOCALAPPDATA%\PharmaCare
    schema: Alembic (backend/migrations), upgrade head on startup
    foreign_keys=ON, journal_mode=WAL on every connection
    backups: <data dir>/backups (backend/src/core/backup.py)
```

Electron does not start FastAPI. There is no owner dashboard and no installer for the live app. The local API starts a sync worker (phase 07 Part B); it uploads only after a device code is saved, and the shop works without one. The cloud API exists as `cloud-api/` (phase 07 Part A) but is not deployed. Backend tests: `cd backend && .venv/bin/pytest`. `desktop/index.html` loads fonts from Google Fonts, so with no internet the UI falls back to system fonts. The sync indicator is the only other UI that wants the network, and it fails soft.

### What the desktop UI actually calls

Since phase 03 the Inventory page has a **Stock** panel (`desktop/src/components/StockPanel.jsx`) for batches, manual adjustment with a reason, and movement history (`GET /inventory/medicines/{id}/movements`). These client methods still have no screen that calls them:

| Client method | API route | Effect |
| --- | --- | --- |
| `updatePatient` | `PUT /patients/{id}` | Patients cannot be edited from the UI yet. |
| `dispense` | `POST /prescriptions/{id}/dispense` | The prescription screen now offers **Create bill** instead. A sale with `prescription_id` marks the prescription dispensed. |
| `pharmacies` | `GET /pharmacies/` | Shop details come from the login response instead. |

`removePatient` (`DELETE /patients/{id}`) is used by **Remove patient** on the patient page since phase 04; it sets a tombstone.

## Target architecture

```
+--------------------------- one shop PC ---------------------------+
|                                                                   |
|  Electron UI (existing React screens)                             |
|    talks only to 127.0.0.1                                        |
|    shows sync status; work continues if sync is down              |
|         |                                                         |
|         v                                                         |
|  Local FastAPI                                                    |
|    auth, inventory, patients, prescriptions, billing              |
|    business services own every write                              |
|         |                                                         |
|         | one SQLite transaction                                  |
|         v                                                         |
|  SQLite in the Windows app-data directory                         |
|    operational source of truth                                    |
|    business rows + sync_outbox                                    |
|         |                                                         |
|         v                                                         |
|  Background worker (in the local Python process)                  |
|    every 5 minutes, batches of up to 100                          |
|    exponential backoff; never blocks the counter                  |
+------------------------------|------------------------------------+
                               | HTTPS, device credential
                               | one way: shop -> cloud
                               v
+----------------------------- Railway -----------------------------+
|  Cloud FastAPI                                                    |
|    POST /api/v1/sync/push     (device credential)                 |
|    GET  /api/v1/admin/...     (owner only)                        |
|         |                                                         |
|         v                                                         |
|  PostgreSQL                                                       |
|    all shops, keyed so local ids cannot collide                   |
+------------------------------|------------------------------------+
                               | HTTPS, owner session
                               v
+----------------------------- Vercel ------------------------------+
|  Next.js + TypeScript owner dashboard                             |
|    read-only for products, patients, prescriptions                |
|    browser never receives database credentials                    |
+-------------------------------------------------------------------+
```

## Current versus target

| Area | Current | Target |
| --- | --- | --- |
| Desktop UI | Electron + React + Vite. Screens for dashboard, billing (list, counter, bill detail), inventory, patients, prescriptions, and sync. English, Urdu (RTL), and Roman Urdu. The shell shows a sync pill. No screens for manual stock adjustment or patient editing. **Sync indicator done in phase 07 Part B.** | Keep these screens. |
| Local API | FastAPI on 127.0.0.1:8000, started manually. | Same API. Packaged backend starts with the app and binds only to 127.0.0.1 on an ephemeral port. |
| Process model | Two terminals in development. | Electron owns the backend child process, waits for health, and stops it on quit. |
| Database | One path helper (`backend/src/core/paths.py`): `backend/data/` in development, the per-user app-data folder when installed, `PHARMACARE_DATA_DIR` to override. Foreign keys and WAL on. Backups and restore exist. **Done in phase 02.** | Same. Electron must set `PHARMACARE_ENV=production` (or run the frozen binary) in phase 09. |
| Startup writes | Migrations only, plus sample data when `PHARMACARE_DEMO_DATA=1` on an empty file. **Done in phase 02.** | Same. |
| Schema changes | Alembic, `upgrade head` on startup, backup before a pending migration. **Done in phase 02.** | Same. |
| Identity | Integer primary keys plus `public_id` UUIDs on pharmacies, medicines, batches, patients, prescriptions, prescription items; `version` on medicines, patients, prescriptions. **Done in phase 02.** | Sales and movements get ids in later phases. |
| Stock | Batches and FIFO kept. Every quantity change writes a `stock_movements` row in the same transaction (`change_batch_quantity`). **Done in phase 03.** | Keep batches and FIFO. Add an append-only stock movement for every quantity change. |
| Auth | Shop manager session token (random hex, 14 days, in `staff_sessions`). Argon2id. First-run setup with a chosen password; no default account. Old PBKDF2 hashes upgrade on sign-in. Logins and writes are audited. **Done in phase 02.** | Owner auth is separate and adds TOTP. |
| Sync | Transactional `sync_outbox` (phase 06) plus a background worker, bootstrap, device-code file, and desktop indicator. **Done in phase 07 Part B.** Uploads only when a device code and a cloud address exist. | Same. Deploy the cloud when the owner asks. |
| Cloud | `cloud-api/`: FastAPI + SQLAlchemy + Alembic on PostgreSQL. Sync ingest (`POST /api/v1/sync/push`, device credentials), owner login, shop and device management, six read-only admin routes. Tested on local PostgreSQL. **Not deployed** (`docs/RAILWAY_DEPLOYMENT.md`). Done in phase 07 Part A. | Deployed on Railway after an explicit go-ahead. |
| Owner UI | `dashboard/`: Next.js owner app. Read-only shops, inventory, patients, prescriptions, and sync freshness. TOTP sign-in. Session cookie is HttpOnly on the Next.js origin. **Not deployed** (`docs/VERCEL_DEPLOYMENT.md`). Done in phase 08. | Deploy on Vercel after an explicit go-ahead. |
| Packaging | Root `package.json` builds the unused "My Store" app. Live desktop has no electron-builder config. Fonts load from Google. | PyInstaller + electron-builder + NSIS for PharmaCare. Fonts bundled. |
| Tests | `backend/tests/` (pytest), 99 tests after phase 07 Part B. `cloud-api/tests/` 27 tests on PostgreSQL. No desktop tests. | Automated tests per phase. PostgreSQL for cloud integration tests. |

## Local request path

1. React calls `desktop/src/api/client.js`.
2. The client sends `Authorization: Bearer` from `localStorage` key `pharmacare_token`.
3. `require_store_manager` in `backend/src/api/main.py` checks `staff_sessions` for every path under `/api/v1` except `/api/v1/auth/login`. `/`, `/health`, and the docs pages are public.
4. Routers call service functions, which commit through `business_transaction`. The middleware also records the signed-in manager's `pharmacy_id`. Patient routes (phase 04) and prescription routes (phase 05) enforce it through `backend/src/core/scope.py`. Inventory and billing routes still take `pharmacy_id` from the query or body and trust it; with one pharmacy per database this is harmless, but it should be enforced the same way before multi-pharmacy use.

UI components must not open SQLite. New writes go through the service layer so a later phase can insert an outbox row in the same transaction.

## Cloud request path

1. The worker reads a prefix of pending `sync_outbox` rows. Bootstrap rows go before live rows.
2. `POST /api/v1/sync/push` authenticates the device and derives `shop_id` from that credential.
3. The cloud applies new events once, stores processed event ids, and commits.
4. The worker marks events synchronized only after `applied` or `already_processed`.
5. The owner dashboard (phase 08) will call admin read APIs with the owner session. Device credentials cannot call those routes.

## Repository layout to grow into

Keep the live tree. Add siblings. Do not start a second desktop app.

```
backend/          local FastAPI (existing). Stays runnable with no cloud.
cloud-api/        Railway FastAPI + PostgreSQL models, sync ingest, admin reads.
dashboard/        Next.js owner dashboard.
desktop/          existing Electron app.
docs/             these documents.
phases/           one prompt per implementation phase.
```

Shared event schema can live in one importable module used by `backend/` and `cloud-api/`. The local app must still start when that cloud package is absent.

## Packaging shape (later)

```
PharmacyManager-Setup-x.y.z.exe
  Electron shell
  PyInstaller FastAPI executable
  migrations
  no live shop database
  no production secrets
```

Local data path, separate from the install directory:

```
%LOCALAPPDATA%\PharmaCare\pharmacy.db
%LOCALAPPDATA%\PharmaCare\backups\
```

Development on macOS can keep using `backend/data/pharmacy.db`. The path helper must branch by environment so developers do not have to use a Windows path on a Mac.

## Assumptions

- The files under `backend/src/` that `main.py` imports are the product. Leftover store-system and clinic files are not a second product to merge.
- Billing stays in the shop app even though the owner's required views are inventory, patients, and prescriptions.
- One installation is one shop. Multi-shop on one PC is not a requirement.
- The owner is a single operator of this product, not a staff hierarchy inside each shop.
- Railway and Vercel are the hosts. Free tiers are not assumed to be enough for real shops. Vercel Hobby is not for commercial production.
- Sync remains one-way until a future project explicitly adds cloud-to-shop updates.

## Risks

- Integer primary keys will collide in PostgreSQL if used as global ids. Sync identity has to be a UUID (or a shop-scoped key), not the local integer alone.
- Resolved in phase 02: `create_all` and the `ALTER` patching are gone; Alembic is the only schema path.
- `backend/src/patients/models.py` declares another `patients` table on the same SQLAlchemy `Base`. Importing it into the live app will clash with `backend/src/models.py`. Do not import it.
- Sample seed data and the default manager account are development conveniences. They must not ship as the production login.
- Resolved in phase 03: dispense, sales, voids, receipts, and adjustments all write `stock_movements`. History before the ledger is only the opening balance plus `sale_allocations`.
- Electron currently trusts a fixed `http://127.0.0.1:8000`. Packaging must use a per-launch loopback port and a per-launch secret so another local process cannot call the API.
- Tokens live in `localStorage`. Acceptable only for the local single-user app; the owner dashboard must use HTTP-only cookies instead.
- Resolved in phase 04: patient removal is a tombstone (`deleted_at`), never a physical delete.
- Backups exist (phase 02) but are manual or pre-migration only. Nothing copies them off the PC, so a disk failure still loses the shop unless the owner copies a backup elsewhere.
- Resolved in phase 02: the sample-data backfills and `ensure_store_manager` were deleted.
- Resolved in phases 02 and 04: deleting a patient no longer fails with a 500 or orphans bills; it now sets a tombstone and keeps all history.
- The billing feature, the expiry-aware stock allocator, and these `docs/` and `phases/` files were uncommitted in git as of 26 November 2026. The last commit is `67c7275`. Commit before later phases change the schema.
- Sample seed data uses Indian addresses and phone numbers (Bengaluru), while prices and UI are for Pakistan (PKR, Urdu). It is development data only.
