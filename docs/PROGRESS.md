# Current development status

Last updated: 26 November 2026, at the end of phase 05 (prescriptions).

**Where the project stands:** the offline shop app is feature-complete for local inventory, patients, prescriptions, and billing. It runs with no internet and no cloud settings (tested with the network blocked). **Sync has not started**: there is no `sync_outbox`, cloud API, sync worker, owner dashboard, or Windows installer yet. Those are phases 06–09.

This is the status file. At the end of every phase, replace the relevant section with what was actually completed, the tests that were run, and what could not be verified. Do not mark work complete without evidence.

## How to continue in a new session

1. Read `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/SYNC_PROTOCOL.md`, `docs/DECISIONS.md`, this file, and `docs/TESTING.md`.
2. Open the first phase file below whose status is not **done**.
3. Implement only that file. If the file has Part A and Part B, stop after Part A unless the user explicitly says to continue.
4. Run that phase's tests.
5. Update this file.
6. Stop. Do not start the next phase.

Suggested prompt:

```
Read docs/PROGRESS.md and the phase file it says to do next.
Follow that file only. Update docs/PROGRESS.md when you finish.
Stop when the phase file says stop.
```

## Phase board

| Order | File | Maps to | Status |
| --- | --- | --- | --- |
| 1 | `phases/01-project-foundation.md` | Inspect the repo, correct these docs, do not rewrite the app | **done** (26 Nov 2026) |
| 2 | `phases/02-local-database.md` | Migrations, identity, auth, backups, transaction boundaries | **done** (26 Nov 2026) |
| 3 | `phases/03-inventory-management.md` | Products, batches, stock movements | **done** (26 Nov 2026) |
| 4 | `phases/04-patient-management.md` | Patients and repeat visits | **done** (26 Nov 2026) |
| 5 | `phases/05-prescriptions.md` | Prescriptions, history, local test suite | **done** (26 Nov 2026) |
| 6 | `phases/06-sync-outbox.md` | Transactional outbox. No HTTP yet | not started |
| 7 | `phases/07-cloud-backend.md` Part A | Railway FastAPI + PostgreSQL ingest | not started |
| 8 | `phases/07-cloud-backend.md` Part B | Local sync worker, bootstrap, desktop indicator | not started |
| 9 | `phases/08-admin-dashboard.md` | Next.js owner dashboard | not started |
| 10 | `phases/09-testing-and-deployment.md` Part A | Windows installer | not started |
| 11 | `phases/09-testing-and-deployment.md` Part B | Final security and readiness review | not started |

Part B of a file starts only after Part A is marked done and the user asks to continue.

## Phase 01 — what was done

Docs corrected against the code:

- `docs/ARCHITECTURE.md`: added the full list of unused files (`client/my-electron-app/`, `backend/models.py`, `backend/schemas.py`, most of `backend/src/core/`), the mounted routes, the startup sequence, the production load path and print bridge in Electron, the desktop methods with no screen, the Google Fonts dependency, and new risks.
- `docs/DATABASE.md`: full `sales`, `sale_items`, and `sale_allocations` columns; the constraints and cascades that exist; the `ensure_schema` data updates; corrected `adjust_batch` (signed delta, not overwrite; `reason` discarded) and the dispense path; tested patient-delete behavior; startup data-write risks.
- `docs/SYNC_PROTOCOL.md` and `docs/DECISIONS.md`: checked, no factual errors, unchanged.

Evidence gathered by running, against a scratch copy of `backend/` with a fresh SQLite file (the developer's `backend/data/pharmacy.db` was not opened):

- The API starts, seeds, and creates exactly 11 tables: `medicines`, `patients`, `pharmacies`, `prescription_items`, `prescriptions`, `sale_allocations`, `sale_items`, `sales`, `staff`, `staff_sessions`, `stock_batches`.
- `PRAGMA foreign_keys` = 0, `PRAGMA journal_mode` = delete.
- Login with `manager` / `store123` succeeds. An unauthenticated `POST /api/v1/pharmacies/` returns 401.
- `DELETE /patients/{id}` returns 500 for a patient with prescriptions and 204 for one without.
- `cd desktop && npx vite build` succeeds.

Evidence from earlier the same day, when billing was added: a scripted HTTP run of the billing API (walk-in sale, duplicate lines merged, discount and tax, cash shortfall rejected, over-stock rejected with stock unchanged, expired batch skipped, prescription bill, re-bill rejected, void restores batches and prescription, date range, search, delete-blocked medicine, 401 without token), and an Electron-driven run of the login, dashboard, billing list, counter, bill detail, void, prescription-to-bill, and Urdu screens. Those scripts lived in a temporary directory and are **not** in the repository, so they are not automated tests.

Not verified by running:

- Electron with its real preload (`window.pharmacare`). The UI run loaded the Vite page directly, so printing used the browser fallback.
- Printing to a real printer.
- Anything on Windows. No packaged build exists.
- The developer's real `backend/data/pharmacy.db`: not opened, so its row counts, orphan rows, and whether the backfills have already touched it are unknown.

## Phase 02 — what was done

Code:

- **Paths.** `backend/src/core/paths.py` is the only place that decides where data lives: `PHARMACARE_DATA_DIR`, else the per-user app-data folder for installed builds (`%LOCALAPPDATA%\PharmaCare` on Windows), else `backend/data` in development.
- **Engine.** `backend/src/core/database.py`: `init_engine()`/`get_engine()`; every connection sets `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`; `hide_parameters=True` keeps row values out of SQL error logs. `get_db` gives one session per request and closes it, carrying the signed-in staff id.
- **Alembic.** `backend/alembic.ini`, `backend/migrations/`. `0001_baseline` absorbs every pre-Alembic file shape. `0002_identity_and_audit` adds `public_id` (6 tables), `version` (3 tables), `audit_logs`. Startup runs `run_migrations()` only (`backend/src/core/migrate.py`): backup first if a migration is pending, then `upgrade head`, then a foreign-key check that logs table names and counts only. `create_all`, `ensure_schema`, the sample backfills, and `ensure_store_manager` were removed.
- **Transactions.** `backend/src/core/transaction.py` `business_transaction(db)`. Every live service write (auth, pharmacies, inventory, patients, prescriptions, billing) now commits through it. Nested use joins the outer transaction. Phase 06 adds the outbox row inside this block.
- **Auth.** Argon2id (`argon2-cffi`). PBKDF2 hashes still verify and are re-hashed on the next good sign-in. No password in source. First-run setup: `GET/POST /api/v1/auth/setup` and a setup screen in `desktop/src/pages/Login.jsx` (English, Urdu, Roman Urdu). Minimum password length 8. Setup is refused once a manager exists.
- **Audit.** `audit_logs` plus `backend/src/core/audit.py`. Ids and action names only. Written for sign-in, failed sign-in, sign-out, setup, re-hash, and every write listed in `docs/DATABASE.md`.
- **Backups.** `backend/src/core/backup.py` (SQLite backup API, integrity check, keep 30) and `python -m src.backup_cli create|list|restore`. Procedure in `docs/BACKUP_AND_RECOVERY.md`.
- **Logs.** The uvicorn access log drops query strings (patient searches put names and phones there).
- **Sample data.** Only with `PHARMACARE_DEMO_DATA=1` on an empty pharmacy table; creates no account.
- **Patient delete.** Returns 409 when the patient has prescriptions or bills (was a 500, or an orphaned bill).
- **Dependencies.** `backend/requirements.txt` adds `alembic`, `argon2-cffi`. New `backend/requirements-dev.txt` adds `pytest`, `httpx2` (Starlette 1.x TestClient).

Docs updated: `docs/DATABASE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (9 completed; new 16–18), new `docs/BACKUP_AND_RECOVERY.md`, `README.md`.

## Phase 03 — what was done

Code (files changed):

- `backend/src/models.py`: `StockMovement` (append-only; checks on delta, quantity_after, and type) and `CHECK (quantity >= 0)` on `StockBatch`.
- `backend/migrations/versions/0003_stock_movements.py`: creates `stock_movements`, writes one `opening_balance` per non-empty batch, adds the batch quantity check.
- `backend/src/inventory/service.py`: `change_batch_quantity()` (the single write path for batch quantity), `receive_new_batch()`, `allocate_stock()` now writes `sale`/`dispense` movements, `list_movements()`. Receipts (create, add batch, CSV import), adjustments (reason required), and delete rule (409 when stock history exists) use it.
- `backend/src/inventory/schemas.py`, `router.py`: `StockAdjust` requires a non-zero delta and a reason; `StockMovementOut`; `GET /api/v1/inventory/medicines/{id}/movements`.
- `backend/src/billing/service.py`: sale movements; void writes `void` movements to the same batches. `backend/src/prescriptions/service.py`: `dispense` movements.
- `backend/src/seed.py`: demo batches arrive as receipts.
- `backend/src/core/migrate.py`: the pre-migration backup is written beside the database being migrated (bug found while migrating a copy: it went to the configured data folder).
- Desktop: new `desktop/src/components/StockPanel.jsx` (batches with expired badge, increase/decrease with reason, movement history); **Stock** button and "N expired" badge in `pages/Inventory.jsx`; "Expired" badge on the dashboard's expiring list; `api/client.js` (`medicine`, `movements`, `adjustBatch(…, reason)`); `components/Modal.jsx` (`wide`); strings in English, Urdu, Roman Urdu; CSS.
- Tests: new `backend/tests/test_inventory_ledger.py` (12); `tests/test_migrations.py` +3; `tests/test_audit_and_api.py` updated for the reason and delete rules.

Docs: `docs/DATABASE.md` (ledger implemented, stock operations table), `docs/DECISIONS.md` (19, 20), `docs/ARCHITECTURE.md`.

Evidence, 26 November 2026:

- `cd backend && .venv/bin/pytest` → **42 passed**, 0 failed.
- Phase test list covered: create/update product; receipt, increase, decrease write the expected movement and quantity; adjustment below zero rolls back with no movement; reason and non-zero delta enforced; database refuses a negative batch; sale and dispense take the earliest-expiring unexpired batch and write movements; void restores the same batches with `void` movements; history is chronological and stable; search and low-stock still match; short sale and short dispense leave no partial decrement and no movement (review step 2); every batch balances against its movements after migration and after the whole flow.
- Mutation checks (reverted): void writing the batch directly without a movement → `test_sale_takes_earliest_expiry_writes_movements_and_void_restores` failed. Pre-migration backup written to the configured folder → `test_pre_migration_backup_sits_beside_the_migrated_file` failed.
- Developer database: copy migrated first, then `backend/data/pharmacy.db` itself (`0002` → `0003`) with backup `backend/data/backups/pharmacy-20261126T103009998287Z-pre-migration-0002_identity_and_audit.db`. Batch quantities and row counts unchanged; 16 opening balances for 16 non-empty batches; 0 unbalanced batches; integrity ok; 0 foreign-key violations; the quantity check is enforced.
- Desktop (Electron driving the Vite page against the developer database): Inventory shows "N expired" badges; the Stock panel for "Testirizine 10mg" listed batches and history; a decrease of 2 on batch `TC-1` with reason "UI test: damaged strip" was saved and appeared at the top of the history (52 → 50); the dashboard showed "Expired" on the 3 past-date batches. Database afterwards: 16 `opening_balance` + 1 `adjustment`, still balanced.

Not verified: Windows; Electron with its real preload; concurrent writers; an adjustment on a batch whose medicine belongs to another pharmacy (one pharmacy per file today).

## Phase 04 — what was done

Code (files changed):

- `backend/src/models.py`, `backend/migrations/versions/0004_patient_tombstone.py`: `patients.deleted_at`.
- `backend/src/patients/service.py` (rewritten), `router.py`, `schemas.py`: removal sets the tombstone for every patient; removed patients are excluded from list/search but readable by id; edits to removed patients return 409; `is_repeat_visitor`, `public_id`, `deleted`, `deleted_at` in the API; search also matches "first last"; all patient operations scoped to the signed-in pharmacy (403 for another pharmacy's list or create, 404 for another pharmacy's patient).
- `backend/src/api/main.py`, `backend/src/core/database.py`: the signed-in manager's `pharmacy_id` on the request and session.
- `backend/src/prescriptions/service.py`, `backend/src/billing/service.py`: refuse new prescriptions and patient-linked bills for removed patients.
- Desktop: `pages/Patients.jsx` ("Returning" / "New" badge), `pages/PatientDetail.jsx` (badge, visit summary, **Remove patient** with confirmation, removed notice, actions hidden when removed), `api/client.js` (`removePatient`), strings in three languages.
- Tests: new `backend/tests/test_patients.py` (7); `tests/test_audit_and_api.py` updated (removal is now 204 and keeps history).

Docs: `docs/DATABASE.md`, `docs/DECISIONS.md` (18 superseded; 21, 22), `docs/ARCHITECTURE.md`.

Evidence, 26 November 2026:

- `cd backend && .venv/bin/pytest` → **49 passed**, 0 failed. Phase 03 inventory and billing tests (`test_inventory_ledger.py`, `test_audit_and_api.py`, `test_database.py`) → 21 passed (review step 2).
- Phase test list: create and read back; search by last name, phone, and full name, unrelated string finds nothing; repeat visitor only after a prescription (list and detail); removing a patient with a prescription keeps the prescription, its items, and patient history readable, and the row is a tombstone (`version` 2); a patient without history is also a tombstone; pharmacy A never sees pharmacy B's patients (list, search, read, update, delete, create).
- Patient names, phones, allergies, notes, and address do not appear in server logs or `audit_logs` during these operations. (The test client's own `httpx2` request log does contain the search URL; that logger is not part of the app, and the server access log drops query strings since phase 02.)
- Mutation checks (reverted): without the pharmacy filter, `test_queries_stay_inside_the_signed_in_pharmacy` failed; with a physical delete, 3 tombstone tests failed.
- Developer database: copy migrated first, then `backend/data/pharmacy.db` (`0003` → `0004`), backup `backend/data/backups/pharmacy-20261126T105420162534Z-pre-migration-0003_stock_movements.db`; row counts unchanged; integrity ok; 0 foreign-key violations.
- Desktop (Electron on the Vite page, developer database): patients with prescriptions show "Returning", a patient without shows "New"; a synthetic patient "Zara Testpatient" was added (badge "New", "No visits yet"), removed through the confirmation dialog, disappeared from the list, and her page still opened with the removed notice and no remove/new-prescription actions. The developer database now has 7 patients, 1 of them removed.

Not verified: Windows; Electron with its real preload; patient editing in the UI (no screen yet, out of scope).

## Phase 05 — what was done

Code (files changed):

- New `backend/src/core/scope.py` (`signed_in_pharmacy`, `visible`), now used by `backend/src/patients/service.py` and `router.py` (moved from phase 04 code, no behavior change) and by prescriptions.
- `backend/src/prescriptions/service.py`, `router.py`: list, read, create, dispense, and cancel scoped to the signed-in pharmacy (403 / 404); `order=asc|desc` with `id` tie-break; new prescriptions get a Python-side UTC `prescribed_at` with microseconds.
- `backend/src/prescriptions/schemas.py`: length and range limits on lines and header fields (dosage/frequency 100, instructions 500, duration 1–365, quantity ≤ 100,000, 1–100 lines).
- Desktop: `pages/PatientDetail.jsx` shows history oldest first with an "Oldest visit first." note; `api/client.js` passes `order`; one string in three languages.
- Tests: new `backend/tests/test_prescriptions.py` (9).
- Docs: new `docs/LOCAL_DEVELOPMENT.md`; `docs/DATABASE.md`, `docs/DECISIONS.md` (23, 24), `docs/ARCHITECTURE.md`, `README.md`.
- No schema change and no migration in this phase. The developer database stays at `0004_patient_tombstone`.

Evidence, 26 November 2026:

- `cd backend && .venv/bin/pytest` → **58 passed**, 0 failed (earlier phases' 49 included).
- Phase test list: two-item prescription stored with dosage, frequency, duration, quantity, instructions, and the copied name/salt/company; a second prescription and a later catalog rename leave the first byte-for-byte unchanged; history oldest first, stable, distinct times for visits in the same second, default newest first, bad `order` rejected; another pharmacy's medicine, patient, list, read, cancel, and dispense rejected with nothing written; empty, inactive-medicine, zero-quantity, zero-duration, and over-long lines rejected; dispense with enough stock writes a `dispense` movement and sets `dispensed`, and cancelling it is refused; dispense without enough stock leaves the prescription `recorded` (version 1), stock and movements unchanged; patient search, prescription create, stock adjustment, and dispense succeed with `CLOUD_API_URL` unset and every outgoing connection blocked; prescription, stock, and movement history are the same after the API restarts.
- Mutation checks (reverted): without the Python timestamp and `id` tie-break, the chronological test failed; without the pharmacy check on read, the scope test failed.
- Review step 2: all 30 live backend modules import; `compileall` clean (`pyflakes` is not installed, so unused imports were not linted). No upgrade migration drops or recreates a table outright; `0002` and `0003` use Alembic batch mode on SQLite (copy-and-swap that keeps rows; row counts verified by tests and on the developer database). The only code that assigns `stock_batches.quantity` is `change_batch_quantity` (`backend/src/inventory/service.py`).
- Review step 3: billing void still restores the same batches (`test_sale_takes_earliest_expiry_writes_movements_and_void_restores`, `test_core_screens_load_and_billing_round_trip`, `test_void_of_a_bill_made_before_the_ledger_keeps_it_balanced` pass).
- Desktop, against the developer database: a prescription for "Bilal Testpatient" was created through the prescription form (medicine chosen from search, dose, days, quantity, instructions), the API process was stopped and started again, and after the restart the patient page still showed it, last in an oldest-first history with the "Oldest visit first." note.

Not verified in the UI (review step 5):

- Running the desktop with the machine actually offline. The API and tests were checked with network calls blocked; the UI only talks to `127.0.0.1`, and its Google Fonts fall back to system fonts.
- Electron with its real preload and printing; Windows.
- Cancelling and the old dispense endpoint from the UI (the UI offers Create bill, not Dispense); covered by API tests only.
- The patient picker and the "new patient" path inside the prescription form (the run used `?patientId=`).

## Tests

Command:

```
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Result at the end of phase 02 (26 November 2026, macOS, Python 3.14.6, pytest 9.2.0, alembic 1.20.1, argon2-cffi 25.1.0): **27 passed**, 0 failed, 0 skipped. At the end of phase 03: **42 passed**. At the end of phase 04: **49 passed**. At the end of phase 05: **58 passed** (see the phase sections above).

| File | Proves |
| --- | --- |
| `tests/test_migrations.py` | Oldest unpatched, oldest patched, and pre-Alembic-with-billing files migrate with every row kept; `public_id` filled, unique, unchanged by re-running migrations or restarting the app; `version` = 1; backup taken before migrating; migrated schema equals the models (empty `compare_metadata`); empty file migrates; `0002` downgrade and re-upgrade keep rows. |
| `tests/test_database.py` | `foreign_keys` = 1 and `journal_mode` = wal on a fresh connection; orphan insert rejected; failed `business_transaction` leaves no rows and no audit row; nested transaction does not commit early; `version` increments and `public_id` stays; a failed sale changes no stock and writes no sale or audit row. |
| `tests/test_startup_and_backup.py` | Startup twice keeps the same file (same inode) and rows; a fresh start has no account, no sample data, and rejects `manager` / `store123`; backup taken with writes still in the WAL contains them; restore round-trip, with the replaced file kept; corrupt backup refused; CLI restore requires `--yes`. |
| `tests/test_auth.py` | Hash is `$argon2id$`, not plaintext; wrong password rejected; setup validation, setup then login, second setup 409; setup reuses an existing pharmacy; API needs sign-in; legacy PBKDF2 hash signs in and is upgraded, with audit rows; no `store123` or `MANAGER_PASSWORD` in `backend/src`, `backend/migrations`, `desktop/src`, `desktop/electron`. |
| `tests/test_audit_and_api.py` | Dashboard, inventory, patients, prescriptions, billing, prescription bill, void, patient update all still work; patient with history returns 409; audit rows contain none of the synthetic patient name, phone, allergy, diagnosis, instruction, or note; inventory writes audited in order; access log drops the query string. |

Mutation checks run once by hand on 26 November 2026, then reverted: with `foreign_keys=OFF` in the engine, two tests in `test_database.py` failed (an earlier version of the test missed this because the migration connection stayed pooled; fixed by disposing the engine first). With nested transactions committing at every depth, `test_nested_transaction_joins_the_outer_one` failed.

Other checks run on 26 November 2026:

- **Copy of the developer database** (`backend/data/pharmacy.db` copied to a scratch folder; the original was not opened for writing): startup migrated it from no revision to `0002_identity_and_audit`; wrote `pharmacy-…-pre-migration-legacy.db`; row counts identical for pharmacies 1, staff 1, medicines 8, stock_batches 8, patients 4, prescriptions 3, prescription_items 4; every identity row has a distinct `public_id`; the existing manager password signed in and was re-hashed to Argon2id; dashboard, medicines, patients, prescriptions, sales, and expiring endpoints returned 200; foreign-key violations 0; `integrity_check` ok; journal mode wal; no errors in the log.
- **Synthetic test data in the developer database** (user request, `CLAUDE.md` line 76). After a backup (`backend/data/backups/pharmacy-20261126T101822574998Z-manual.db`), a scripted run against the real API on `backend/data/pharmacy.db` exercised sign-in (wrong password, logout, re-login, second setup refused), pharmacy update, inventory (create, edit, batches, adjust, CSV import incl. DD/MM/YYYY and an impossible date, delete rules, search by name and barcode, low-stock, expiring), patients (create, search by name and phone, edit, delete rules), prescriptions (create, cancel, old dispense endpoint, validation), billing (walk-in cash with discount and tax, card, prescription bill, double bill, short cash, over-stock, expired batch skipped, void and double void, list filters), dashboard totals, audit coverage (18 action types, no patient details), `public_id` uniqueness, integrity, and foreign keys, each checked by reading SQLite directly. **70 passed, 0 failed** (one first-run expectation was wrong: the CSV importer intentionally accepts DD/MM/YYYY). Test rows left in the file: SKUs `TST-*`, patients `Ayesha/Bilal Testpatient`, invoices `INV-000001`–`INV-000004` (one void). Post-test backup `pharmacy-20261126T102039266636Z-manual.db`; a restore drill on a copy of it passed. Dashboard, Billing, Inventory, Patients, and Prescriptions screens all showed the test data.
- **First-run UI** (Electron driving the Vite page, fresh empty data folder): setup screen shown; 7-character password rejected with the localized message; setup created the shop and opened the dashboard; after sign-out the normal sign-in form appeared with no default credentials.
- `cd desktop && npx vite build` succeeded.

Not verified:

- Windows. The app-data path, WAL, and Argon2id are untested on Windows; there is no packaged build.
- Electron with its real preload; the UI checks loaded the Vite page directly.
- (Resolved later on 26 November 2026: the developer's real `backend/data/pharmacy.db` was migrated at the user's request. See "Developer database migrated" below.)
- Restore while the app is running (forbidden by the procedure), disk-full, and power loss during backup or migration.
- Concurrency beyond one desktop client.

## What already works

Verified by reading the code, by the phase 02 test suite, and by running the API on 26 November 2026.

- Local API: `python run.py` in `backend/` serves FastAPI on `127.0.0.1:8000`.
- Desktop UI: Electron + React with dashboard, billing (list, counter, bill detail), inventory, patients, and prescriptions in English, Urdu, and Roman Urdu.
- Auth: first-run setup with a chosen password, Argon2id, manager login, bearer token in `localStorage`, 14-day server session in `staff_sessions`, audit rows.
- Database: Alembic migrations on startup, foreign keys and WAL on, `public_id` and `version` on core rows, backup and restore.
- Inventory: medicines, CSV import, batches, expiry, reorder level, low-stock and expiring lists, expired badges. Stock is taken from unexpired batches only, earliest expiry first (`allocate_stock`). Every quantity change is in the `stock_movements` ledger; the Stock panel shows batches, history, and manual adjustment with a reason.
- Patients: create, search by name, phone, or full name, repeat-visitor badge, visit count and last visit, removal as a tombstone that keeps history, scoped to the signed-in pharmacy. Editing exists in the API only.
- Prescriptions: create with line items (copied medicine details), patient history oldest first, list newest first, cancel, scoped to the signed-in pharmacy. The UI dispenses by billing the prescription; the older dispense endpoint writes `dispense` movements.
- Billing: sales, invoice numbers, discounts and tax, payment methods, cash change, voids that restore the allocated batches, today's sales on the dashboard.
- Shop scoping columns exist (`pharmacy_id`) on the main business tables, but most routes trust the `pharmacy_id` they are sent.
- Electron preload uses context isolation and points the UI at the local API.

## Reuse in later phases

- Service modules: `backend/src/*/service.py`. New writes (movements, outbox) go inside the existing `business_transaction` block, beside `record_audit`.
- `backend/src/core/transaction.py`, `backend/src/core/audit.py`, `backend/src/core/migrate.py`, and new Alembic revisions in `backend/migrations/versions/` for any schema change.
- Test fixtures in `backend/tests/conftest.py` (temporary data dir, demo client, manager setup) and legacy builders in `backend/tests/legacy.py`.
- Routers and Pydantic schemas under `backend/src/*/`.
- `allocate_stock` in `backend/src/inventory/service.py` as the single place sales and dispensing reduce stock.
- `sale_allocations` as the pattern for recording which batch moved.
- React pages under `desktop/src/pages/` and the API client `desktop/src/api/client.js`.
- The i18n catalog `desktop/src/i18n/catalog.js` for any new UI text, in all three languages.

## What is missing

- `public_id` on sales, sale items, allocations (not needed for v1 sync; their stock effects sync as movements).
- Scheduled backups and copying backups off the PC.
- A screen to change the manager password (only first-run setup exists).
- Desktop (React) automated tests.
- `sync_outbox` and transactional event writes.
- Cloud API, PostgreSQL, shop device credentials.
- Background sync worker and desktop sync indicator.
- Owner dashboard, TOTP, and owner sessions.
- PharmaCare Windows installer. The root electron-builder config belongs to the unused store system.
- Electron does not launch or supervise FastAPI.
- Bundled fonts. The UI loads them from Google.
- Screens for manual stock adjustment and patient editing.

## Known hazards

- **Uncommitted work.** Billing, phases 02–05, `docs/`, and `phases/` are not committed. The last commit is `67c7275`. Snapshots of the tree from before phases 02–05 are in the session scratch folder only, which is temporary. Commit before phase 06.
- **Developer database migrated.** On 26 November 2026, at the user's request, `backend/data/pharmacy.db` was migrated from the pre-Alembic schema to `0002_identity_and_audit` with `run_migrations()`. Backup written: `backend/data/backups/pharmacy-20261126T101419430233Z-pre-migration-legacy.db`. Row counts unchanged (pharmacies 1, staff 1, medicines 8, stock_batches 8, patients 4, prescriptions 3, prescription_items 4); `public_id` present and unique on all 6 tables; integrity ok; WAL; 0 foreign-key violations. `alembic current` reports `0002_identity_and_audit (head)` and a second `alembic upgrade head` is a no-op. Its existing password keeps working and becomes Argon2id on the next sign-in. Backups and WAL files are git-ignored.
- **Backups are not encrypted.** `CLAUDE.md` requires encrypted SQLite backups with a tested restore. Phase 02 backups (`backend/src/core/backup.py`) are plain SQLite copies containing patient data. No phase file owns encryption yet. Decide where it lands (phase 03 supporting change, or phase 09 with Windows credential storage for the key) before real shop data exists.
- Resolved in phase 03: expired batches are marked "Expired" on the dashboard and in the Stock panel, and Inventory shows "N expired" beside Qty. Qty itself still includes expired units (by design: it is what is physically on the shelf); billing refuses them.
- **No password reset.** If the manager forgets the password there is no reset screen. Recovery today: restore a backup, or a developer edits the `staff` row. Plan a reset path before shops use the app.
- **Orphan rows are reported, not fixed.** If an old file has foreign-key violations, startup logs table names and counts; updating such a row will fail.
- Unused clinic models share table names with the live models. Do not import them.
- Unused store-system code must not be wired back in.
- Integer ids will collide across shops if used as global primary keys in PostgreSQL.
- Sample data (`PHARMACARE_DEMO_DATA=1`) uses Bengaluru addresses and is development data only.
- Removed patients cannot be restored from the UI (no un-remove action). A developer can clear `deleted_at`.
- Patient and prescription routes enforce the signed-in pharmacy; inventory and billing still trust the `pharmacy_id` in the request.
- The old dispense endpoint now writes `dispense` movements but still no sale or allocation row, so it cannot be voided. The UI does not call it.
- Pre-ledger history is only the opening balance plus `sale_allocations`.
- Installed builds must set `PHARMACARE_ENV=production` or run as a frozen binary, or the data goes to the source-tree default. Phase 09 must wire this.

## Next step

Execute `phases/06-sync-outbox.md`. Commit the current working tree first. Phase 06 is the first sync phase; the offline app should be committed as a known-good baseline before it starts.
