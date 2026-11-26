# Phase 07 — Cloud backend and sync worker

Status: not started.
Depends on: `phases/06-sync-outbox.md` marked done.

This file has two parts. Complete **Part A**, run the review, and stop. Start **Part B** only when the user explicitly says to continue. Do not build the Vercel dashboard or the Windows installer in either part.

Read `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/SYNC_PROTOCOL.md`, `docs/DECISIONS.md`, and `docs/PROGRESS.md` before either part.

The local app in `backend/` must keep starting with no cloud configured.

---

## Part A — Railway API and PostgreSQL

### Goal

Add a separate `cloud-api/` application that can receive a batch of versioned events and store them in PostgreSQL. It must be testable without the desktop app and without a real Railway deploy.

### Layout

```
cloud-api/
  app/
    api/            routes
    auth/           device credentials and owner auth skeleton
    sync/           ingest and apply
    models/
    services/
    config/
  alembic/
  tests/
```

Reuse the event field names from `docs/SYNC_PROTOCOL.md`. You may import a shared schema module. The local app must not fail if `cloud-api` is not installed.

### Database

Alembic migrations for PostgreSQL:

- shops
- shop_devices
- products
- stock_movements
- patients
- prescriptions
- prescription_items
- audit_logs
- processed_sync_events
- synchronization_state

Every business row includes `shop_id`. Uniqueness for a business entity is `(shop_id, public_id)`. Two shops may use the same local integer id and the same accidental UUID must still be rejected per shop by the unique constraint on that shop's `public_id`.

`processed_sync_events` has a unique constraint on `(shop_id, event_id)`.

### Shop credentials

- The owner can register a shop and issue a revocable device credential.
- Store only a hash of the device secret.
- `shop_id` on an event is taken from the authenticated device. A mismatched body `shop_id` is `invalid_event`.
- Device credentials cannot call admin routes.
- No cloud database password in any response.

Owner accounts exist so admin routes can be protected in this part. The login UI is phase 08. Provide a way to create the first owner from an environment variable or a one-off command. Passwords are hashed. TOTP enrollment can be completed in phase 08, but admin routes must already reject anonymous and device callers.

### Sync API

`POST /api/v1/sync/push`

1. Authenticate the shop.
2. Validate each event against schema version 1.
3. Skip events already in `processed_sync_events` with result `already_processed`.
4. Enforce version and dependency rules from `docs/SYNC_PROTOCOL.md`.
5. Apply the event.
6. Insert the processed-event row.
7. Commit.
8. Return per-event results only after commit.

Results: `applied`, `already_processed`, `retryable_error`, `ordering_conflict`, `invalid_event`.

A retried stock movement must not change quantity twice. A retried patient or prescription must not insert a duplicate. A prescription whose patient is absent is not applied. Concurrent requests with the same `event_id` result in one apply and one `already_processed`.

Document in `docs/SYNC_PROTOCOL.md` which events in a mixed batch are acknowledged. Invalid events become `invalid_event` so one bad payload cannot block the shop forever without a diagnosis.

### Owner read API

Protected, read-only:

- `GET /api/v1/admin/shops`
- `GET /api/v1/admin/overview`
- `GET /api/v1/admin/inventory`
- `GET /api/v1/admin/patients`
- `GET /api/v1/admin/prescriptions`
- `GET /api/v1/admin/sync-status`

Support pagination and shop filters. These routes must not accept a device credential.

### Deploy prep, without deploying

Write `docs/RAILWAY_DEPLOYMENT.md` with:

- Dependency file and the production start command.
- Railway service settings and the PostgreSQL environment variables.
- Health check path.
- Alembic upgrade command.
- Example env vars with placeholders, not real secrets.
- Logging that omits patient clinical text and secrets.

Do not deploy. Do not hard-code secrets.

### Tests

Use PostgreSQL. If it is not available, do not pretend the tests passed. Record that they were skipped.

- Valid product, movement, patient, and prescription events.
- Duplicate `event_id` does not double-apply stock.
- Stale version and missing patient.
- Transaction rollback leaves no partial prescription.
- Unknown device is rejected.
- Shop A cannot write shop B's rows or read them with shop A's credential.
- Admin route rejects a missing owner token and rejects a device token.
- Two concurrent pushes of the same event apply once.

### Part A review, then stop

1. Run `cloud-api` tests and the local backend suite.
2. Update `docs/SYNC_PROTOCOL.md`, `docs/DATABASE.md`, and `docs/PROGRESS.md` with real results.
3. Next step, only after the user asks: Part B of this file.
4. Stop. Do not start the worker, the dashboard, or packaging.

---

## Part B — Automatic synchronization

Start this only after Part A is marked done and the user says to continue.

### Goal

A background worker inside the local Python process uploads pending `sync_outbox` rows to the cloud API. The shop remains fully usable offline.

### Worker

- Starts after the local API starts. One worker. No overlap.
- Default every 5 minutes. Batch size up to 100.
- Authenticated HTTPS, with a timeout.
- On `applied` or `already_processed`, mark that event `synced`.
- On timeout or connection loss, leave the event pending.
- Exponential backoff with jitter for offline, DNS, connection errors, timeouts, HTTP 429, and HTTP 5xx.
- Honor `Retry-After` when present.
- `invalid_event` is marked failed and is not retried forever. The diagnostic view can show the event id and error code, not the patient payload.
- Do not use Celery, Redis, or Kafka.

Do not acknowledge event N+1 when it depends on a failed event N. Patient before prescription. Movement payload must be self-contained so it can apply once the product exists.

### Activation and bootstrap

- The manager can use the app before the shop is activated.
- Activation is owner-controlled: the cloud issues a device credential, and the desktop stores it with platform protection. On Windows that means DPAPI or an equivalent. On a Mac development machine, use a local secret file outside git with permissions documented. Do not put the secret in the repository.
- After activation, sync runs without a Railway login.
- Initial bootstrap uploads existing rows idempotently, in dependency order, preserving `public_id`, and can resume after a restart. Local writes during bootstrap also create outbox events and must not be lost.
- After bootstrap, only incremental sync runs.

### Reconciliation and UI

Track last success, last acknowledged sequence, pending count, failed count, and last error locally.

Add a small indicator on the existing Electron shell: Synced, Syncing, Waiting for internet, Sync error. Work is never blocked. Detailed errors live in a diagnostic view and must not show patient data or the device secret.

The cloud sync-status payload is last-known. Do not display a disconnected shop as "zero pending".

### Tests

Against the test cloud API and PostgreSQL when available:

- Events created while offline upload after the client can connect.
- A duplicate retry and a lost acknowledgement do not double-apply.
- Restarting with pending rows continues from those rows.
- A large pending batch (at least a few thousand events in a test) drains in order.
- A prescription is not applied before its patient.
- Bootstrap interruption resumes without duplicate patients.
- A 5xx leaves events pending and a later success marks them synced.
- An invalid event stops retrying and does not block an unrelated later product event once ordering rules allow.
- Two shops sync into isolated rows.

### Part B review, then stop

1. Run worker tests and the local suite.
2. Update `docs/SYNC_PROTOCOL.md` and `docs/PROGRESS.md`.
3. Next file, only in a later session: `phases/08-admin-dashboard.md`.
4. Stop. Do not build the dashboard.
