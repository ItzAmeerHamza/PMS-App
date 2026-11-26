# Phase 02 — Local database

Status: not started.
Depends on: `phases/01-project-foundation.md` marked done.
You are a senior backend engineer. Execute this phase only, then stop.

## Read first

`docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`, `docs/TESTING.md`, and `backend/src/models.py`.

## Goal

Make the existing SQLite database reliable without rebuilding inventory, patients, prescriptions, or billing. Later phases add stock-movement behavior, patient rules, and prescription rules on top of this foundation. Phase 06 adds the outbox into the same transactions.

## Keep working

- Live models stay in `backend/src/models.py`. Do not switch the app to `backend/src/patients/models.py` or the clinic `User` model.
- Integer primary keys and existing foreign keys stay.
- `backend/data/pharmacy.db` must survive startup if it already exists. Never delete and recreate it.
- Electron still talks only to the local FastAPI app. Do not call Railway or Vercel.
- Billing, FIFO allocation, and the current screens keep working.

## Requirements

### Identity

- Add `public_id` (UUID, unique, not null) to `pharmacies`, `medicines`, `stock_batches`, `patients`, `prescriptions`, and `prescription_items`.
- Generate it once for existing rows. Never regenerate it on startup.
- Add an integer `version` to mutable business rows (`medicines`, `patients`, `prescriptions`), starting at 1.
- The pharmacy `public_id` is the stable shop identity.

### Schema mechanics

- Introduce Alembic for the local app. New schema changes are migrations.
- After Alembic is in place, startup runs migrations. It does not keep a second ad-hoc `ALTER TABLE` path for the same changes.
- Enable SQLite `foreign_keys=ON` on every connection.
- Enable WAL where appropriate.
- Timestamps are UTC.
- Preserve existing rows. Test a migration against a database that already contains pharmacies, medicines, patients, and prescriptions.

### Sessions and transactions

- One session per request, closed afterward.
- Add a single service-layer pattern for a business transaction so later phases can insert an outbox row before commit.
- A failed operation rolls back the whole transaction.
- Do not create `sync_outbox` in this phase.

### Auth

- Shop-manager passwords use Argon2id, or another modern password hash if Argon2id cannot be installed. Document the choice in `docs/DECISIONS.md`.
- Verify existing PBKDF2 hashes until those users change passwords, or migrate them with an explicit, tested path. Do not lock out the current development database without a documented step.
- Remove the hard-coded default password in `backend/src/auth/service.py`. First run with no manager must require a chosen password. Do not ship `store` credentials in source.
- Sessions stay local. No owner login in this phase.

### Storage and backup

- Put the SQLite path behind one helper. Development may keep `backend/data/pharmacy.db`. The Windows target path is the application-data directory, outside the install folder. Document both in `docs/BACKUP_AND_RECOVERY.md`.
- Implement a SQLite backup using the SQLite backup API or an equivalent safe copy that does not copy a half-written WAL incorrectly.
- Document restore steps in `docs/BACKUP_AND_RECOVERY.md`.
- Do not log patient names, phones, allergies, or prescription text.

### Audit

- Add `audit_logs` as specified in `docs/DATABASE.md`. Write an audit row for manager login and for the business operations you touch. No clinical text in the audit payload.

## Tests

Add automated tests for:

- Migration preserves existing rows and fills `public_id` once.
- Foreign key enforcement rejects an orphan insert.
- A failed transaction rolls back.
- Startup does not delete an existing database.
- Backup and restore round-trip.
- Password verification, including rejection of a wrong password.
- The source tree no longer contains a hard-coded manager password.

## Out of scope

- Stock movement ledger and inventory UI changes (phase 03).
- Patient matching rules (phase 04).
- Prescription behavior changes beyond a safe migration (phase 05).
- `sync_outbox`, Railway, Vercel, packaging.
- Deleting leftover store-system or clinic files. Leave them unused.

## Done when

- The app still serves the existing API against migrated SQLite.
- Tests listed above were run, and results are in `docs/PROGRESS.md`.
- `docs/DATABASE.md` and `docs/BACKUP_AND_RECOVERY.md` match the code.

## Review, then stop

1. Run the new tests and the app's existing startup path against a copy of the database, not by deleting the real file.
2. Check migrations, imports, and that billing, inventory, patients, and prescriptions still load.
3. Update `docs/PROGRESS.md`: completed work, test command, test results, known issues, next file `phases/03-inventory-management.md`.
4. State anything you could not verify.
5. Stop. Do not begin phase 03.
