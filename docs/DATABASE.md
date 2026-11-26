# Database schema and relationships

Updated at the end of phase 02 (26 November 2026). The live models are in `backend/src/models.py`. Schema changes go only through Alembic and must keep existing rows.

## How the schema is managed

- Migrations live in `backend/migrations/versions/`. Alembic config: `backend/alembic.ini` and `backend/migrations/env.py`.
- `0001_baseline` brings any database to the pre-Alembic schema: it creates missing tables (older files have no sales tables), adds the columns the old startup patched in with `ALTER TABLE`, and runs the old startup `UPDATE` fixes once. The DDL is the exact SQL the old `create_all` produced.
- `0002_identity_and_audit` adds `public_id` and `version` and creates `audit_logs`.
- `0004_patient_tombstone` (phase 04) adds `patients.deleted_at` (indexed).
- `0003_stock_movements` (phase 03) creates `stock_movements`, writes an `opening_balance` movement for every non-empty batch, and adds `CHECK (quantity >= 0)` to `stock_batches`.
- Startup (`lifespan` in `backend/src/api/main.py`) calls `run_migrations()` in `backend/src/core/migrate.py`. It runs `upgrade head`, nothing else. `create_all`, `ensure_schema`, the sample-data backfills, and `ensure_store_manager` are gone.
- If the file already has tables and a migration is pending, `run_migrations()` first writes a backup labelled `pre-migration-<revision or legacy>`.
- After upgrading it runs `PRAGMA foreign_key_check` and logs table names and counts only.
- `env.py` turns foreign keys off while migrations run (SQLite batch operations copy tables) and back on afterwards.
- Test `tests/test_migrations.py` compares the migrated schema with the models (`alembic.autogenerate.compare_metadata`); it must stay empty.

Every connection sets `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`, and `synchronous=NORMAL` (`_sqlite_pragmas` in `backend/src/core/database.py`). The engine uses `hide_parameters=True`, so SQL errors do not echo row values into logs.

The file location comes from `backend/src/core/paths.py`. See `BACKUP_AND_RECOVERY.md`.

Timestamps are UTC. `server_default=func.now()` stores SQLite `CURRENT_TIMESTAMP`, which is UTC text with no offset. Code that sets times in Python uses `datetime.now(timezone.utc)`. The desktop reads offset-less timestamps as UTC (`parseDate` in `desktop/src/lib/format.js`).

## Identity and versions

| Table | `public_id` | `version` |
| --- | --- | --- |
| pharmacies | yes (the stable shop identity) | no |
| medicines | yes | yes |
| stock_batches | yes | no |
| patients | yes | yes |
| prescriptions | yes | yes |
| prescription_items | yes | no |
| audit_logs | yes | no |
| stock_movements | yes | `version` column, always 1 (immutable) |

- `public_id` is `VARCHAR(36)` UUID text, `NOT NULL`, with a unique index `ix_<table>_public_id`. New rows get `uuid4()` at insert (`models.new_public_id`). Existing rows got one in migration `0002`, which fills only rows where it is null. Nothing regenerates it.
- `version` is `INTEGER NOT NULL DEFAULT 1`. SQLAlchemy `version_id_col` adds 1 on every ORM `UPDATE` of that row. Adding a batch or a prescription does not change the parent's version.
- `stock_movements` also has `public_id` (phase 03); that is how sale, void, and dispense stock effects are identified for sync. The sales tables themselves still have no `public_id` (not synced in v1).

## Current local tables

```
pharmacies
  id PK, public_id
  name, address, phone, license_number, created_at
  |
  +-- staff (pharmacy_id FK)
  |     id PK, full_name, username UNIQUE, password_hash, role, is_active
  |     |
  |     +-- staff_sessions (staff_id FK)
  |           token PK, expires_at
  |
  +-- medicines (pharmacy_id FK, UNIQUE pharmacy_id + sku)
  |     id PK, public_id, version, sku, name, salt, generic_name, manufacturer, form, strength,
  |     pack_size, category, barcode, rack_location, unit_price, reorder_level,
  |     requires_prescription, notes, is_active, created_at, updated_at
  |     |
  |     +-- stock_batches (medicine_id FK)
  |           id PK, public_id, batch_number, expiry_date, quantity, cost_price,
  |           selling_price, created_at
  |
  +-- patients (pharmacy_id FK)
  |     id PK, public_id, version, deleted_at (tombstone), first_name, last_name, phone, date_of_birth, gender,
  |     address, allergies, notes, created_at, updated_at
  |     |
  |     +-- prescriptions (pharmacy_id FK, patient_id FK)
  |           id PK, public_id, version, doctor_name, complaint, diagnosis, notes, status,
  |           prescribed_at, dispensed_at, created_at
  |           |
  |           +-- prescription_items (prescription_id FK, medicine_id FK)
  |                 id PK, public_id, medicine_name, medicine_salt, medicine_company,
  |                 dosage, frequency, duration_days, quantity, instructions
  |
  +-- sales (pharmacy_id FK; nullable patient_id, prescription_id, staff_id FKs)
        id PK, invoice_number UNIQUE ("INV-" + zero-padded id),
        customer_name, customer_phone,
        subtotal, discount_percent, discount_amount, tax_percent, tax_amount,
        total, payment_method (cash | card | bank_transfer | other),
        amount_paid, change_due, notes, status (paid | void),
        voided_at, void_reason, created_at
        |
        +-- sale_items (sale_id FK, medicine_id FK)
        |     id PK, medicine_name, quantity, unit_price, line_total
        |     |
        |     +-- sale_allocations (sale_item_id FK, batch_id FK -> stock_batches)
        |           id PK, batch_number, expiry_date, quantity
        |
        +-- (prescriptions.sales is a view-only relationship back to sales)
```

Constraints that exist: primary keys, `UNIQUE(pharmacy_id, sku)` on `medicines`, `UNIQUE(username)` on `staff`, `UNIQUE(invoice_number)` on `sales`, unique `public_id` on the identity tables, and `NOT NULL` on the columns marked required in `models.py`. Foreign keys are enforced on every connection since phase 02 (`tests/test_database.py::test_foreign_keys_reject_orphan_insert`). `pharmacies` has no `updated_at`. `staff_sessions` also has `created_at`.

ORM cascades: deleting a medicine deletes its batches; deleting a prescription deletes its items; deleting a sale deletes its items and allocations; deleting a staff row deletes its sessions. Patients have no cascade.

Prescriptions (phase 05):

- `prescriptions.status` values in use: `recorded`, `dispensed`, `cancelled`. A dispensed prescription cannot be cancelled. Dispensing or billing a prescription with too little unexpired stock leaves it `recorded` with no batch change.
- A prescription is created only for a non-removed patient of the signed-in pharmacy, with 1–100 lines, each an active medicine of that pharmacy. Line limits: dosage and frequency ≤ 100 characters, instructions ≤ 500, duration 1–365 days, quantity 1–100,000.
- Each line copies `medicine_name`, `medicine_salt`, and `medicine_company` at creation, so later catalog edits do not change history. Creating a prescription never updates or deletes another one.
- New prescriptions set `prescribed_at` in Python (UTC, microseconds). Older rows have second resolution from SQLite's `CURRENT_TIMESTAMP`.
- `GET /prescriptions/?order=asc` lists oldest first (patient history); the default `desc` is newest first. Both break ties on `id`, so the order is stable.
- Listing, reading, dispensing, and cancelling use the signed-in pharmacy (another pharmacy's list or create: 403; another pharmacy's prescription: 404).

Billing: prices on bills come from `medicines.unit_price`. `stock_batches.selling_price` is stored but not used for billing. Prices on bills come from `medicines.unit_price`. `stock_batches.selling_price` is stored but not used for billing.

`Sale.invoice_number` is globally unique in the local file. That is fine for one shop.

Quantity on hand is the sum of `stock_batches.quantity`, including expired batches. The API also reports `sellable_quantity`, which counts only batches whose `expiry_date` is today or later. Since phase 03 every quantity change is ledger-backed: see "Stock movement ledger" below.

| Operation | Code | Batch change | Movement written |
| --- | --- | --- | --- |
| New medicine with first batch, add batch | `inventory/service.py` `receive_new_batch` | Batch created at 0, then raised to its quantity | `receipt`, source `batch` |
| CSV import row with a batch | `_import_rows` → `receive_new_batch` | same | `receipt`, source `import` |
| Demo seed batch | `seed.py` → `receive_new_batch` | same | `receipt`, source `seed` |
| Manual adjustment | `adjust_batch` → `change_batch_quantity` | Signed delta; must not be 0; result must not go below 0 | `adjustment` with the manager's required `reason` |
| Sale | `billing/service.py` `_create_sale` → `allocate_stock` | Unexpired batches, earliest expiry first; also recorded in `sale_allocations` | one `sale` per batch touched, source `sale` + sale id |
| Void | `void_sale` → `change_batch_quantity` | Each allocation added back to the same batch | one `void` per allocation, source `sale` + sale id |
| Dispense (old endpoint, no UI) | `prescriptions/service.py` `dispense_prescription` → `allocate_stock` | as for a sale | one `dispense` per batch, source `prescription` + id |

`allocate_stock` checks the total unexpired stock before changing anything; any later failure rolls back the whole `business_transaction`, so a short sale or dispense leaves no batch change and no movement (`tests/test_inventory_ledger.py::test_short_stock_sale_or_dispense_leaves_no_partial_change`).

Patients (phase 04):

- **Removal is a tombstone.** `DELETE /patients/{id}` (UI: **Remove patient** on the patient page) sets `deleted_at`, increments `version`, and writes `patient.deleted`. The row is never physically deleted, with or without history. Repeating it is a no-op (204).
- Removed patients are left out of the list and search, but `GET /patients/{id}` still returns them with `deleted: true`, and their prescriptions and bills stay readable. Editing them returns 409; new prescriptions or patient-linked bills for them are refused ("Patient not found").
- **Repeat visitor:** `is_repeat_visitor` is true when the patient has at least one prescription at this pharmacy (any status). The API also returns `prescription_count` and `last_visit`.
- **Pharmacy scope:** the auth middleware puts the signed-in manager's `pharmacy_id` on the request (`request.state` → `db.info["pharmacy_id"]`). Patient list, search, read, create, update, and delete use only that pharmacy: a list or create for another `pharmacy_id` returns 403, and another pharmacy's patient id returns 404. Other modules (inventory, prescriptions, billing) still trust the `pharmacy_id` they are sent.
- Search matches first name, last name, phone, and "first last".

Medicine delete is blocked when a prescription item, sale item, or stock movement references it.

```
audit_logs (phase 02)
  id PK, public_id UNIQUE, pharmacy_id FK (nullable), staff_id FK (nullable),
  action, entity_type, entity_public_id, created_at (UTC, indexed)
```

`audit_logs` holds ids and action names only. `record_audit()` in `backend/src/core/audit.py` has no parameter for names, phones, allergies, diagnoses, or prescription text. The staff id comes from the request (`request.state.staff_id` → `db.info["staff_id"]`). Actions written today:

| Area | Actions |
| --- | --- |
| Auth | `auth.setup`, `auth.login`, `auth.login_failed` (no username stored), `auth.logout`, `auth.password_rehashed` |
| Pharmacy | `pharmacy.created`, `pharmacy.updated` |
| Inventory | `medicine.created`, `medicine.updated`, `medicine.deleted`, `medicine.imported`, `batch.created`, `batch.adjusted` |
| Patients | `patient.created`, `patient.updated`, `patient.deleted` |
| Prescriptions | `prescription.created`, `prescription.cancelled`, `prescription.dispensed` |
| Billing | `sale.created`, `sale.voided` (no `entity_public_id` yet; sales have none) |

Every write in those services runs inside `business_transaction(db)` (`backend/src/core/transaction.py`): the row changes and the audit row commit together or roll back together. A nested `business_transaction` joins the outer one. Phase 06 adds the outbox insert inside the same block.

## Do not confuse these with the live schema

| File | Why it is not the live schema |
| --- | --- |
| `backend/src/patients/models.py` | Second `patients` table (user_id, blood type, insurance) on the same `Base`. Not imported by the API. |
| `backend/src/core/models.py` | Clinic `users` with roles admin, doctor, patient, nurse, receptionist. Not mounted. |
| `backend/src/doctors/models.py`, `backend/src/appointments/models.py` | Clinic module. Not mounted. |
| `public/back-end/database/migrations/` | Sequelize migrations for the unused MySQL store system. |

Do not import the unused models into `backend/src/api/main.py`. Do not point the live app at `backend/database.py`.

## Target local tables

Keep every current table. Add the following. Names in the phase prompts (`Shop`, `LocalUser`, `Product`, `Patient`) map onto the existing names below. Do not rename working tables just to match the prompt vocabulary.

| Prompt name | Live table | Target change |
| --- | --- | --- |
| Shop | `pharmacies` | **Done (phase 02):** `public_id`. |
| LocalUser | `staff` | **Done (phase 02):** Argon2id, no default account. |
| Product | `medicines` | **Done (phase 02):** `public_id`, `version`. Batches kept. |
| Stock batch | `stock_batches` | **Done (phase 02):** `public_id`. Quantity remains the current balance. |
| StockMovement | `stock_movements` | **Done (phase 03).** Append-only ledger. |
| Patient | `patients` | **Done (phases 02, 04):** `public_id`, `version`, `deleted_at` tombstone. |
| Prescription | `prescriptions` | **Done (phase 02):** `public_id`, `version`. |
| PrescriptionItem | `prescription_items` | **Done (phase 02):** `public_id`. Items travel inside the prescription event. |
| AuditLog | `audit_logs` | **Done (phase 02).** |
| — | `sales`, `sale_items`, `sale_allocations` | Keep. Stock movements must record sale, void, and dispense. |
| sync_outbox | new, phase 06 | See `SYNC_PROTOCOL.md`. Not created before that phase. |

`public_id` is the sync identity. Local integer primary keys stay so existing foreign keys and the React client do not have to be rewritten in one step. New rows get a UUID at insert. Existing rows get a UUID once, in a migration, and that value never changes.

## Stock movement ledger (phase 03)

```
stock_movements
  id PK, public_id UNIQUE, pharmacy_id FK, medicine_id FK, batch_id FK (NOT NULL),
  staff_id FK (nullable), movement_type, quantity_delta, quantity_after,
  reason, source_type, source_id, version (always 1), created_at (UTC, microseconds)
  CHECK quantity_delta != 0
  CHECK quantity_after >= 0
  CHECK movement_type IN ('opening_balance','receipt','adjustment','dispense','sale','void')
stock_batches
  CHECK quantity >= 0   (added in 0003)
```

| Column | Meaning |
| --- | --- |
| movement_type | `opening_balance` (written once by migration `0003`), `receipt`, `adjustment`, `dispense`, `sale`, `void`. |
| quantity_delta / quantity_after | Signed change and the batch quantity right after it. |
| reason | Required for `adjustment` (1–255 characters). Fixed text for `opening_balance`. Otherwise empty. |
| source_type, source_id | `batch` (receipt; id = batch), `import`, `seed`, `adjustment`, `sale` (id = sale), `prescription` (id = prescription), `migration`. |
| staff_id | The signed-in manager, from the request. |

Rules:

- `change_batch_quantity()` in `backend/src/inventory/service.py` is the only code that assigns `stock_batches.quantity`. It writes the movement in the caller's `business_transaction`, so the change and its movement commit together. Phase 06 adds the outbox row in the same block.
- Invariant: for every batch, `SUM(quantity_delta) = stock_batches.quantity`. Tested after migration, after the full sale/void flow, and on the developer database.
- The app never updates or deletes movement rows. A medicine with any movement cannot be deleted (409, "This medicine has stock history…"); mark it inactive instead.
- History: `GET /api/v1/inventory/medicines/{id}/movements`, ordered by `created_at`, then `id`. The desktop shows it newest first in the Stock panel.
- History before migration `0003` is not reconstructed. The opening balance is the batch quantity at migration time. Earlier sales are still described batch-by-batch by `sale_allocations`; earlier adjustments and old-endpoint dispenses are lost.

`audit_logs` exists as described above. Do not store allergies, diagnoses, phone numbers, or prescription item text in it.

## Constraints and session rules

- `PRAGMA foreign_keys = ON` on every SQLite connection. Done.
- WAL for the shop database (`journal_mode=WAL`). Done.
- Store timestamps in UTC.
- Business operations commit in one transaction: the row changes, the stock movement, the audit row, and later the outbox row.
- A failed transaction leaves none of those rows.
- Do not call `create_all`. Alembic owns the schema; `create_all` is no longer called anywhere in the live app.
- Do not delete `backend/data/pharmacy.db` on startup. Migrations must be additive and reversible where SQLite allows it.

## Cloud tables (later, PostgreSQL)

Every business row is stored per shop. Uniqueness is `(shop_id, public_id)`, not `public_id` alone and not the shop's integer id.

```
shops
shop_devices
products                  (shop_id, public_id) unique
stock_movements           (shop_id, public_id) unique
patients                  (shop_id, public_id) unique
prescriptions             (shop_id, public_id) unique
prescription_items        (shop_id, public_id) unique
audit_logs
processed_sync_events     (shop_id, event_id) unique
synchronization_state     one row per shop
```

`processed_sync_events` is the idempotency table. A retried event id inserts nothing the second time.

Cloud foreign keys point at cloud rows for the same `shop_id`. A patient `public_id` from shop A must not attach to a prescription from shop B.

Optional later tables, only if billing itself is synced: `sales`, `sale_items`, `sale_allocations`. Until then, sale and void stock effects still arrive as `stock_movements`.

## Ordering and versions

- `version` on a mutable entity increments by 1 on each successful update.
- Stock movements are inserts, not updates. Their order is the local monotonic sequence on the outbox, not the wall clock.
- Deletions become tombstones: the local row is marked deleted, `version` increments, and an event is written. The row stays until retention rules say it can go.

## Migration and data-loss risks

- Generating a new `public_id` on every startup would split one shop into many. Generate once and persist.
- Rebuilding the SQLite file loses patients and stock. Forbidden.
- Done in phase 03: existing batch quantities became `opening_balance` movements. Past adjustments cannot be recovered; `sale_allocations` remain the only detail for sales before the ledger.
- SQLite `ALTER` is limited. Prefer new columns and new tables over rewriting primary keys.
- Foreign keys are now enforced. Existing orphan rows are not deleted: `run_migrations()` reports them (table and count) and they stay until fixed by hand. Updating an orphan row will fail. On the copy of the developer database tested on 26 November 2026 there were none.
- The unused clinic `Patient` model must stay unimported, or `create_all` / Alembic autogenerate will try to rebuild `patients`.
- Resolved in phase 02: the startup sample-data backfills were deleted, `ensure_store_manager` was deleted, and the `ensure_schema` updates became a one-time step in `0001_baseline`. Sample data now loads only with `PHARMACARE_DEMO_DATA=1` and only into an empty pharmacy table, and creates no account.
- SQLite runs DDL outside a transaction, so a migration that fails part-way can leave a half-migrated file. That is why `run_migrations()` backs up first. Restore that backup rather than editing the file by hand.
- `0002` downgrade drops `public_id`. Upgrading again assigns new ids. Never downgrade a shop that has synced (phase 07 and later).
- Existing sales were created before any ledger exists. Their `sale_allocations` are the only batch-level history. Prescriptions dispensed through the old endpoint have no batch history at all.
