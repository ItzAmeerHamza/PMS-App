# Architectural decisions

These decisions are already made. A phase may not reverse one of them without an explicit request. Record any new decision here and in `PROGRESS.md`.

## 1. Extend the live PharmaCare app

The product is `backend/` plus `desktop/`. Do not rebuild it as a new Electron app, and do not revive the root store-system (`src/`, `public/`, root `package.json`) or the unused clinic modules (`doctors`, `appointments`, `backend/src/patients/models.py`, `backend/auth.py`).

Reason: those trees are a different application and a different schema. Merging them would destroy the working pharmacy screens.

## 2. One shop, one computer, SQLite is the source of truth

Each installation has one pharmacy row and one SQLite file. The manager can complete inventory, patient, prescription, and billing work with no network.

Reason: shops in this product operate independently, and connectivity is not reliable enough to put PostgreSQL on the critical path.

## 3. Sync is one-way, and the owner dashboard is read-only

Events flow shop → Railway. The dashboard reads PostgreSQL through the cloud API. It does not edit stock or prescriptions.

Reason: an owner edit while a shop is offline would require conflict resolution. That is a later project.

## 4. Transactional outbox, no message broker

The business write and the `sync_outbox` insert commit together. A single background loop in the local Python process uploads batches. Celery, Redis, and Kafka are out of scope unless a measured test shows the simple loop cannot keep up. That is unlikely for one PC.

Reason: the shop has one process and no operator to run extra services.

## 5. Keep batches; add a movement ledger

`stock_batches` stays the quantity used for expiry and FIFO. A new `stock_movements` row records every delta, including sale, void, and dispense.

Reason: the current overwrite of `quantity` is not an audit trail, but collapsing batches into one number would drop expiry behavior the app already has.

## 6. UUIDs beside integer keys

Add `public_id` to business entities. Keep integer primary keys and existing foreign keys.

Reason: the React client and SQLAlchemy relationships already use integers. Replacing primary keys risks data loss. The cloud unique key is `(shop_id, public_id)`, so two shops can both have local `id = 1`.

## 7. Billing stays local

Sales, voids, and batch allocations stay. They are not an owner-dashboard feature in v1. They must emit stock movements so cloud inventory matches the counter.

Reason: deleting billing would remove working counter behavior. Syncing full invoices is unnecessary for the owner's stated views.

## 8. Local auth and owner auth are different

The shop manager authenticates to the local API only. The owner authenticates to the cloud API with a password hash and TOTP, HTTP-only cookies, and CSRF protection. Device credentials can push events and cannot call admin routes. The desktop app never receives cloud database credentials or the owner password.

Reason: a shop computer should not be an admin console for every other shop.

## 9. No hard-coded production password

Done in phase 02. There is no default account and no password in source. First-run setup (`GET`/`POST /api/v1/auth/setup`, setup screen in `desktop/src/pages/Login.jsx`) creates the manager with a password the manager types, minimum 8 characters, and is refused once a manager exists.

**Hash: Argon2id** via `argon2-cffi` (`PasswordHasher()` defaults, the RFC 9106 low-memory profile). It installed cleanly on macOS with Python 3.14; it ships wheels for Windows, so PyInstaller packaging is expected to work, to be confirmed in phase 09.

**Existing PBKDF2 hashes** (`<salt>$<digest>`, SHA-256, 120,000 rounds) are still verified. On the next successful sign-in the hash is replaced with Argon2id in the same transaction and an `auth.password_rehashed` audit row is written. Nobody is locked out and no manual step is needed. Tested in `tests/test_auth.py::test_legacy_pbkdf2_hash_still_signs_in_and_is_upgraded`.

## 10. Schema changes go through Alembic

`create_all` plus startup `ALTER TABLE` is the current mechanism. After the local-database phase, migrations own the schema. Startup may run `upgrade head`. It may not delete the database.

## 11. Patient data stays out of routine logs

Sync errors, the desktop sync indicator, and application logs may include event id, entity type, and a short error code. They may not include patient name, phone, allergies, diagnosis, or prescription lines. Backups that contain the SQLite file must be protected. Document the restore steps.

## 12. Hosting

Railway runs the cloud FastAPI app and PostgreSQL. Vercel runs the Next.js dashboard. Do not deploy without credentials and an explicit request. Do not assume Railway's free resources or the Vercel Hobby plan are acceptable for commercial shop data. The dashboard should not add a second backend of serverless jobs; Railway remains the API.

## 13. Packaging

PyInstaller for the local API, electron-builder with NSIS for the installer. The installer does not include a populated shop database. Code signing is documented, not skipped silently. Ordinary startup does not require internet.

## 14. Phase order is mandatory

Foundation, then local reliability, then the outbox, then the cloud API, then the worker, then the dashboard, then packaging, then the final review. Do not skip the outbox phase or the worker phase. Do not start the next phase in the same session after a phase file says stop.

## 15. Documentation names

Use these files. Do not create parallel documents with the older names.

| Use this | Do not also create |
| --- | --- |
| `docs/DATABASE.md` | `docs/DATABASE_DESIGN.md` |
| `docs/PROGRESS.md` | `docs/IMPLEMENTATION_STATUS.md` |
| `docs/ARCHITECTURE.md` | a second architecture file |
| `docs/SYNC_PROTOCOL.md` | a second sync spec |

Deployment notes from later phases are added as `docs/RAILWAY_DEPLOYMENT.md`, `docs/VERCEL_DEPLOYMENT.md`, `docs/WINDOWS_PACKAGING.md`, `docs/BACKUP_AND_RECOVERY.md`, and `docs/LOCAL_DEVELOPMENT.md` when that phase starts. Until then, do not invent them. `docs/BACKUP_AND_RECOVERY.md` exists since phase 02, `docs/LOCAL_DEVELOPMENT.md` since phase 05, `docs/RAILWAY_DEPLOYMENT.md` since phase 07 Part A.

## 16. One baseline migration absorbs every pre-Alembic file (phase 02)

`0001_baseline` creates missing tables, adds the columns the old startup patched in, and runs the old startup data fixes once. It does not use `alembic stamp`. Every database, empty or old, goes through the same `upgrade head`.

Reason: shop files exist in several pre-Alembic shapes (with and without sales tables, with patched columns at the end). One idempotent baseline handles all of them and is tested against each shape.

## 17. Sample data only on request (phase 02)

`seed_if_empty` runs only when `PHARMACARE_DEMO_DATA=1` and the pharmacy table is empty, and creates no staff. The startup backfills that edited sample rows were deleted.

Reason: they matched real shop rows by SKU or diagnosis text and overwrote them.

## 18. Patients with history cannot be deleted, until tombstones exist (phase 02) — superseded by 21

Phase 02 made `DELETE /patients/{id}` return 409 for patients with history. Phase 04 replaced that with tombstones (decision 21).

Reason: with foreign keys enforced the old path failed with a 500, and deleting a patient with bills would orphan them.

## 19. Stock changes go through one function and one ledger (phase 03)

`change_batch_quantity()` in `backend/src/inventory/service.py` is the only code that changes `stock_batches.quantity`, and it always appends a `stock_movements` row in the caller's transaction. New batches start at 0 and receive their quantity as a `receipt`. Existing stock entered the ledger as one `opening_balance` row per batch in migration `0003`. The database also enforces `quantity >= 0`.

Reason: one write path makes "every quantity change has a movement" true by construction and gives phase 06 one place to add the outbox event.

## 20. Manual adjustments need a reason; products with stock history are not deleted (phase 03)

`POST /inventory/batches/{id}/adjust` requires a non-zero `quantity_delta` and a `reason` (1–255 characters), stored on the movement. A medicine with any stock movement returns 409 on delete; it can be marked inactive. A medicine that never had stock can still be deleted.

Reason: the ledger is append-only (decision 5), so deleting a product would delete its history. This matches the existing rule for medicines on prescriptions or bills.

## 21. Patient removal is a tombstone for every patient (phase 04)

`DELETE /patients/{id}` sets `patients.deleted_at` and increments `version`; the row is never physically deleted, even for a patient with no prescriptions. Removed patients disappear from list and search but stay readable by id with their prescriptions and bills. They cannot be edited or given new prescriptions or bills.

Reason: the phase prefers a deleted flag over a physical delete, and sync (phase 06) needs a row to emit `patient.deleted` from. One rule for all patients is simpler than two.

## 22. Patient routes use the signed-in pharmacy, not the one in the request (phase 04)

The auth middleware stores the manager's `pharmacy_id` on the request. Patient list, search, read, create, update, and delete only touch that pharmacy: another `pharmacy_id` in a list or create returns 403, and another pharmacy's patient id returns 404 (existence is not revealed).

Reason: patient records are the most sensitive data in the app. Other modules still trust the request's `pharmacy_id`; apply the same pattern there before any multi-pharmacy use.

## 23. Patient history is oldest first; worklists are newest first (phase 05)

`GET /prescriptions/` takes `order=asc|desc` (default `desc`). The patient page asks for `asc` and says "Oldest visit first." The Prescriptions page and the dashboard keep newest first. New prescriptions get a Python-side UTC timestamp with microseconds, and every ordering breaks ties on `id`.

Reason: the phase asks for chronological history, while the counter needs the latest work on top. Second-resolution database timestamps made visits created together sort unpredictably.

## 24. Prescriptions use the same pharmacy scope as patients (phase 05)

`backend/src/core/scope.py` (`signed_in_pharmacy`, `visible`) is shared by patients and prescriptions. Inventory and billing still trust the request's `pharmacy_id` (see decision 22).

## 25. Medicines are tombstoned too (phase 06)

Deleting a medicine (still allowed only when it has no prescription, bill, or stock history) sets `medicines.deleted_at` and clears `is_active`. The row stays and `product.deleted` is emitted. The SKU stays reserved.

Reason: `SYNC_PROTOCOL.md` requires the local row to stay for a delete event. Freeing the SKU would need the unique constraint to ignore tombstoned rows; not worth it for products that never had stock.

## 26. Pre-existing rows and the dev seed write no events (phase 06)

Migration `0005` does not backfill events, and `seed_if_empty` runs with the outbox disabled. Those rows reach the cloud through the initial bootstrap (phase 07 Part B).

Reason: the bootstrap exists for exactly this, and backfilling events in a migration would mix two ordering schemes.

## 27. Unchanged saves are not changes (phase 06)

Updating a patient or medicine with the values it already has does not bump `version`, emit an event, or write an audit row (`Session.is_modified`).

Reason: a screen that re-saves a form must not create sync traffic or version gaps the cloud would treat as ordering conflicts.

## 28. A cloud shop's id is the desktop pharmacy's public_id (phase 07 Part A)

`shops.id` in PostgreSQL is the same UUID the desktop writes into `sync_outbox.shop_id`. The owner registers a shop with that id and then issues a device credential for it.

Reason: events already carry it, so the cloud can check every event against the device's shop without a mapping table, and a reinstall that keeps the database keeps its identity.

## 29. Device secrets are high-entropy and stored as SHA-256 (phase 07 Part A)

Device tokens are `pcd_<device id>.<secret>` with a 256-bit random secret; only `sha256(secret)` is stored. Owner passwords use Argon2id. Owner session tokens are random and stored as SHA-256.

Reason: a slow password hash protects guessable secrets; a 256-bit random secret cannot be guessed, and a fast hash keeps every push cheap.

## 30. A push stops at the first conflict, not at invalid events (phase 07 Part A)

Events are applied in `sequence` order. After the first `ordering_conflict` or `retryable_error`, the rest of the batch is returned as `retryable_error` / `blocked_by_earlier_event` without being attempted. `invalid_event` does not stop the batch.

Reason: `SYNC_PROTOCOL.md` says to acknowledge a prefix when in doubt, so dependent events cannot jump ahead; invalid events would otherwise block a shop forever.

## 31. Cloud has stock_batches, owners, and owner_sessions beyond the planned list (phase 07 Part A)

`stock_batches` gives the owner per-batch quantity and expiry; movements are still the only way quantities change. `owners` and `owner_sessions` let admin routes reject anonymous and device callers now; TOTP and cookie sessions come in phase 08.

## 32. The device secret stays out of SQLite (phase 07 Part B)

Windows uses DPAPI for the current user. macOS and Linux use a mode-0600 file in `<data dir>/secrets/`, which is git-ignored. The status API and the logs never return it. The cloud address may be saved on `sync_state`; an environment variable overrides it.

Reason: the outbox database is backed up and sometimes copied for debugging. A secret in that file would travel with the copy. The same user who can read the pharmacy database can read this file; that is the shop PC's trust boundary until phase 09.

## 33. Bootstrap is a second origin in the same outbox (phase 07 Part B)

Pre-existing rows are inserted as `sync_outbox` rows with `origin='bootstrap'`, in dependency order, with a UUID5 event id. The worker uploads every unsent bootstrap row before any `live` row. A cursor on `sync_state` makes a restart continue the scan, and the stable event id makes a repeated scan harmless.

Reason: live writes during the scan must not be dropped or reordered ahead of the patient or product they depend on, and the cloud already knows how to apply these events once.

## 34. A connection failure backs off the worker, not each event (phase 07 Part B)

Timeouts, DNS, connection loss, HTTP 429, and HTTP 5xx leave the rows `pending` and set `sync_state.backoff_until`. `Retry-After` is honored, capped at one hour. An `ordering_conflict` also leaves the row pending and at the front of the prefix, so a later event is not sent past it. Only `invalid_event` becomes `failed`.

Reason: putting `next_attempt_at` on the one row that failed would make `list_pending` skip it and send the next row, which is how a prescription would jump ahead of its patient.

## 35. The owner session stays on the Next.js server (phase 08)

Password check and TOTP stay on the cloud API. The dashboard server stores the resulting session token in an HttpOnly cookie on its own origin and calls Railway with `Authorization: Bearer`. The browser receives `{ok: true}` after the code is accepted, not the token. Login, the code step, and sign-out must echo a CSRF value. Eight failed passwords for one email in 15 minutes return 429.

Reason: a token in page JavaScript could be read by any script on the page. The database URL never belongs on Vercel.

