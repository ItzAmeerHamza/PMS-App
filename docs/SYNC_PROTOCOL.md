# Offline synchronization rules

Status: the local outbox exists (phase 06). The cloud ingest API exists (phase 07 Part A, tested on PostgreSQL, not deployed). The local worker, activation, bootstrap, and desktop indicator exist (phase 07 Part B, `backend/src/sync/`). The shop makes no network call until a device code is stored. Where the implementation differs from the design below, see the implementation notes at the end.

## Direction

```
Shop SQLite  --event-->  Railway PostgreSQL  --read-->  owner dashboard
```

Synchronization is asynchronous and one-way. The owner dashboard does not update shop inventory or prescriptions. That avoids conflict resolution while a shop is offline.

SQLite remains the source of truth for shop operations. The cloud is a replica built by applying events. A cloud outage does not roll back a local commit.

## When an event is written

On every relevant create, update, or delete:

1. Open one SQLAlchemy transaction.
2. Save the business change, including any stock movement.
3. Insert one `sync_outbox` row.
4. Commit both, or roll both back.
5. Return success to Electron.

Do not write the event in an `after_commit` hook or a second transaction. Nested service calls must not emit a second event for the same change.

The local API returns success without contacting Railway.

## Outbox row

| Field | Rule |
| --- | --- |
| id | Local integer primary key. |
| sequence | Monotonic local integer. This is the shop's order. Do not order only by timestamps. |
| event_id | UUID, unique. |
| shop_id | The pharmacy `public_id`. |
| entity_type | `product`, `stock_movement`, `patient`, `prescription`, `audit_log`. |
| entity_id | That row's `public_id`. |
| operation | `created`, `updated`, `deleted`. |
| entity_version | Integer version after this change. Movements stay at 1. |
| schema_version | Integer. Starts at 1. |
| payload | Immutable JSON snapshot. Never updated after insert. |
| created_at | UTC. |
| status | `pending`, `synced`, `retryable_error`, `failed`. |
| retry_count | Integer, starts at 0. |
| next_attempt_at | UTC, null when pending and ready. |
| last_error | Short diagnostic. No patient clinical text, no secrets. |
| synced_at | UTC, set only after the cloud acknowledges the event. |

Indexes: pending retrieval by `(status, next_attempt_at, sequence)`, and a unique constraint on `event_id`.

Do not delete a row the moment it is acknowledged. Keep it for a configurable retention period.

## Event names

Payloads use schema version 1.

| Event | Payload strategy |
| --- | --- |
| product.created / product.updated | Full product snapshot, including current batch balances as read-only context. |
| product.deleted | Tombstone: `public_id`, version, deleted_at. The local row stays. |
| stock.movement_created | Immutable movement. This is how stock changes, including receipt, adjustment, dispense, sale, and void. |
| patient.created / patient.updated | Full patient snapshot. |
| patient.deleted | Tombstone. Do not hard-delete before the tombstone can sync. |
| prescription.created / prescription.updated | Full prescription snapshot including items. |
| prescription.deleted | Tombstone plus the prescription `public_id`. Items are not synced as separate events in v1. |

`stock.movement_created` is an insert. The cloud applies the delta once. Replaying the same `event_id` must not change quantity again.

Product snapshots include batch balances so the cloud can show current stock, but the movement events are the authority for how stock changed. If a snapshot and a movement disagree, the cloud keeps the movement ledger and can flag the snapshot for reconciliation. The cloud must not apply a product snapshot as a second stock delta.

## Cloud interpretation

`POST /api/v1/sync/push` accepts a batch of these events.

For each event the cloud:

1. Authenticates the device and sets `shop_id` from the credential.
2. Rejects a body `shop_id` that does not match.
3. Validates `schema_version` and required payload fields.
4. If `(shop_id, event_id)` already exists in `processed_sync_events`, returns `already_processed` and does not apply it again.
5. Applies the event only when ordering rules pass.
6. Inserts the processed-event row in the same transaction as the business write.

Per-event results, returned only after commit:

| Result | Meaning | Worker action |
| --- | --- | --- |
| applied | Stored. | Mark `synced`. |
| already_processed | Duplicate delivery. | Mark `synced`. Do not send a corrective write. |
| retryable_error | Transient or missing dependency. | Keep `pending`, increment retry, set `next_attempt_at`. |
| ordering_conflict | An older version arrived after a newer one, or a dependency is missing. | Do not mark `synced`. Surface it. Do not skip ahead in a way that applies a prescription before its patient. |
| invalid_event | Schema or business rule will never succeed. | Mark `failed`. Stop retrying forever. Keep the payload for diagnosis. |

A batch may mix results. Only events whose result is `applied` or `already_processed` are acknowledged. A failure of event N does not acknowledge events after N when those later events depend on N. Independent events in the same batch may be acknowledged if the implementation documents that clearly and tests it. When in doubt, acknowledge a prefix of the batch in `sequence` order and leave the rest pending.

The unique key `(shop_id, event_id)` plus a transaction around apply-and-record makes concurrent duplicate requests safe.

## Ordering rules

- Process a shop's events by `sequence`.
- A prescription event whose patient `public_id` is not in the cloud yet returns `retryable_error` or `ordering_conflict`, not a partial prescription.
- An update with `entity_version` less than or equal to the stored version is `already_processed` if the event id was stored, and `ordering_conflict` if the event id is new but the version is stale.
- An update with a version gap (cloud has version 2, event says version 5) is `ordering_conflict` until the missing versions arrive.
- Wall-clock timestamps are informational. They are not the sort key.

## Worker behavior (phase 07 Part B)

- Starts with the local API. One worker per process. A lock prevents overlap.
- Default interval: 5 minutes.
- Batch size: up to 100 pending events.
- HTTPS, timeouts, authenticated with the device credential.
- Exponential backoff with jitter for offline, DNS, connection, timeout, HTTP 429, and HTTP 5xx.
- Honor `Retry-After` when the server sends it.
- Never mark `synced` on a timeout or a lost response. The next attempt is safe because of `event_id`.
- Do not require the manager to sign in to Railway.

Shop activation is owner-controlled. The manager can work offline before activation. Device secrets are stored with Windows protection (DPAPI or an equivalent local secret store). They are not stored in the installer and not stored in plaintext in PostgreSQL.

## Initial bootstrap

Shops may already have months of rows before sync is turned on.

- One idempotent, resumable upload of existing rows.
- Preserve `public_id` values.
- Order: shop, products and batches, opening stock movements, patients, prescriptions with items.
- Local writes during bootstrap also go to the outbox and must not be dropped.
- After bootstrap, only incremental outbox sync runs.
- Interruptions resume from the last acknowledged sequence.

## Reconciliation

Track last successful sync, last acknowledged sequence, pending count, failed count, and last error. A disconnected shop does not report a live pending count. The dashboard shows last-known figures and the time they were reported.

Repair may upload missing local events. It must not overwrite newer local rows with older cloud rows.

## What is not synced in v1

- Staff passwords, session tokens, and device secrets.
- Owner credentials.
- The SQLite file itself.
- Another shop's rows.

Billing invoices are not required in the owner dashboard for v1. Their stock effect is synced as `stock.movement_created`.

## Implementation notes (phase 06)

How the local outbox was built, and where it differs from the design above.

**Where events come from.** Services call `emit_event()` inside `business_transaction`, after flushing the business change and before the audit row. The event commits or rolls back with the change (tested by forcing a failure after both inserts).

| Business action | Events written |
| --- | --- |
| Create medicine | `product.created` (batches empty), then one `stock.movement_created` per starting batch |
| Edit medicine (a real change) | `product.updated` |
| Delete medicine (allowed only without history) | `product.deleted` tombstone |
| Add batch, CSV import row, manual adjustment | `stock.movement_created` (import also `product.created`) |
| Sale, void, old dispense endpoint | one `stock.movement_created` per batch touched |
| Create / edit / remove patient | `patient.created` / `patient.updated` / `patient.deleted` tombstone |
| Create prescription | `prescription.created` (items inside) |
| Cancel, dispense, bill, or void a billed prescription | `prescription.updated` (status change) |

**Differences from the design, and why:**

1. **Medicine tombstone.** `product.deleted` says the local row stays, but medicines were physically deleted. Migration `0005` adds `medicines.deleted_at`; deleting sets it and `is_active = false`. Deleted medicines are hidden from inventory lists. Their SKU stays taken.
2. **`prescription.deleted` is never emitted.** The app has no way to delete a prescription (only cancel, which emits `prescription.updated`). The event name is reserved.
3. **`audit_log` events are not emitted.** The design lists `audit_log` as an entity type; the phase 06 requirements do not include it, and audit rows stay local in v1.
4. **No events for pre-existing rows or the dev seed.** Rows that existed before migration `0005`, and rows created by `PHARMACARE_DEMO_DATA=1`, have no events. They are uploaded by the initial bootstrap (phase 07 Part B), as the design's bootstrap section already expects.
5. **Batches travel inside movements.** Batches have no events of their own. Each `stock.movement_created` payload carries `batch` (public_id, batch_number, expiry_date, quantity after, prices) and `medicine_public_id`, so the cloud can create a batch on its first movement. Product snapshots still list batch balances as read-only context.
6. **Movement source.** The payload has `source_type` and `source_ref`: the prescription `public_id` for a dispense, the invoice number for a sale or void, otherwise null. Local integer ids are not sent. The invoice number is now assigned as soon as the sale row exists, so the sale's movements can carry it.
7. **No-op updates emit nothing.** Saving a patient or medicine with unchanged values does not bump `version` and writes no event or audit row. Reading screens never writes events.
8. **Duplicate guard.** Within one transaction, a second `emit_event()` for the same entity, operation, and version is ignored, so nested service calls cannot double an event.
9. **Sequence.** `MAX(sequence) + 1`, counted per transaction. It is unique and increasing, but may have gaps (for example when a CSV row's savepoint rolls back). Order by it; do not expect contiguity.
10. **Payload shape.** JSON with sorted keys; an extra top-level `"event"` field carries the public event name. Datetimes are UTC ISO-8601 with `Z`; money is a string. Patient and prescription payloads contain personal and clinical data: they live only in the local database and the cloud, never in logs.
11. **Read model for the worker** (no HTTP yet): `list_pending(db, limit=100)` returns pending and due retryable rows by `sequence`; `counts(db)`; `acknowledge(db, results)` marks synced only for `applied` and `already_processed` and ignores other results and unknown ids; `record_error(db, event_id, code, retryable=True)` increments `retry_count`, stores a ≤255-character code, and sets `next_attempt_at` with backoff 30 s, 60 s, 120 s … capped at 1 h (the worker adds jitter), or marks the row `failed`; `purge_synced(db, older_than_days)` deletes only acknowledged rows older than the retention period (`settings.outbox_retention_days`, default 30). Purge is never run automatically.

## Implementation notes (phase 07 Part A, cloud ingest)

Code: `cloud-api/app/sync/` (`schemas.py` validation, `apply.py` per-entity rules, `service.py` push processing), `cloud-api/app/auth/`.

**Shop identity.** A cloud shop's id is the desktop pharmacy's `public_id`, the value already in `sync_outbox.shop_id`. The owner registers it (`POST /api/v1/admin/shops`). The device credential decides the shop; an event whose `shop_id` differs is `invalid_event` / `shop_id_mismatch`.

**Device credential.** `Authorization: Bearer pcd_<device id>.<secret>`. The secret is 256 random bits; the cloud stores only its SHA-256 hash. Revoked devices and disabled shops get 401. Device tokens get 403 on every admin route.

**Request.** `POST /api/v1/sync/push` with `{"events": [...], "outbox": {"pending": n, "failed": n}}`. Events are the desktop's `serialize_event` output; extra fields (such as the top-level `event` name) are ignored. At most 500 events (413 above that). `outbox` is optional and stored as last-known counts. Response: `{"shop_id": ..., "results": [{"event_id", "result", "code"?}]}` in the same order as the request, returned after every commit.

**Per event,** in its own PostgreSQL transaction: lock the shop's `synchronization_state` row (serializes applies per shop) → `already_processed` if `(shop_id, event_id)` exists → validate → check shop → check version and dependencies → apply → insert `processed_sync_events` → commit. A unique-constraint race with a concurrent request rolls back and reports `already_processed`.

**Results and codes** (codes name a field or rule, never a value):

| Result | When | Example codes |
| --- | --- | --- |
| `applied` | Stored. | — |
| `already_processed` | Event id seen before for this shop. | — |
| `invalid_event` | Will never succeed: bad schema, wrong `schema_version`, payload not matching the envelope, wrong shop. | `schema:schema_version`, `schema:event`, `payload:first_name`, `payload:public_id_mismatch`, `payload:version_mismatch`, `shop_id_mismatch`, `payload:batch_belongs_to_another_product` |
| `ordering_conflict` | Not applicable now: a dependency is missing or the version does not follow. | `missing_patient`, `missing_product`, `entity_missing`, `entity_exists`, `stale_version`, `version_gap` |
| `retryable_error` | Transient, or not attempted. | `database_unavailable`, `internal_error`, `blocked_by_earlier_event` |

**Which events in a mixed batch are acknowledged.** Events are processed in `sequence` order, whatever order the request lists them in. Every `applied` and `already_processed` result is final and may be marked synced. After the first `ordering_conflict` or `retryable_error`, the remaining events are not attempted and return `retryable_error` / `blocked_by_earlier_event`, so a prescription can never be applied ahead of a patient that failed before it. `invalid_event` does not block the batch: it can never succeed, the worker marks it `failed`, and later events that depend on it will themselves return `ordering_conflict`. Effectively the shop gets an acknowledged prefix plus any later events after invalid ones.

**Version rules as built.** `created` requires that the entity does not exist (any version ≥ 1 is accepted, so a bootstrap snapshot at version N can create it). `updated` and `deleted` require exactly stored version + 1. Stock movements are `created` only, with version 1; a movement `public_id` seen before under a new event id is `ordering_conflict` / `entity_exists` and never a second delta.

**Stock.** Batches are created by their first movement (the payload carries batch number, expiry, prices). Quantity changes only by applied deltas. Product snapshots update catalog fields only; their `batches` list is ignored. If the cloud quantity after a movement differs from the shop's `quantity_after`, both are stored (`cloud_quantity_after`) for reconciliation.

**Deletes.** Tombstones set `deleted_at` (and `is_active = false` for products) and bump the version. Rows are kept.

**Logging.** One INFO line per push: shop id, event count, result counts. No payloads.

## Implementation notes (phase 07 Part B, the worker)

Code: `backend/src/sync/` (`worker.py`, `bootstrap.py`, `transport.py`, `secrets.py`, `service.py`), migration `0006_sync_state`. The desktop indicator is `desktop/src/components/SyncIndicator.jsx` and the page is `desktop/src/pages/Sync.jsx`.

**When it runs.** The worker thread starts with the local API (`PHARMACARE_SYNC_AUTOSTART=0` turns it off; tests do). One thread, and a lock makes a second cycle return immediately. Default every 300 seconds (`PHARMACARE_SYNC_INTERVAL_SECONDS`), up to 100 events (`PHARMACARE_SYNC_BATCH_SIZE`), 30 second timeout (`PHARMACARE_SYNC_TIMEOUT_SECONDS`). The manager can also press **Sync now**, which ignores the backoff timer. The sale, stock, and patient screens do not wait for a cycle.

**No cloud, no code.** With no device code the indicator is "Not activated" and nothing is uploaded. The shop works. The cloud address is `PHARMACARE_CLOUD_API_URL`, else `CLOUD_API_URL`, else the address saved on the activation screen. An empty address is `cloud_not_configured` and the events stay pending.

**Device code.** The owner still issues it from `POST /api/v1/admin/shops/{id}/devices` (the dashboard that does this is phase 08). The manager pastes `pcd_<device id>.<secret>` on the Sync page. Windows stores it with DPAPI (`CryptProtectData`, current user). macOS and Linux store it in `<data dir>/secrets/device-credential`, directory mode 0700, file mode 0600, outside git. It is not written to SQLite, not returned by the status API, and not logged. Replacing the code does not restart bootstrap.

**What gets sent first.** `sync_outbox.origin` is `live` for a counter change and `bootstrap` for the one-time snapshot of rows that had no event (pre-migration data and the dev seed). While any bootstrap row is still pending or waiting to retry, or the scan is not finished, only bootstrap rows are uploaded. Live rows, including ones written during the scan, wait. Within one origin the worker sends a sequence prefix and stops before an event whose `next_attempt_at` is still in the future, so it does not skip ahead. Failed rows are not in that prefix, so an invalid event does not hold a later one.

**Bootstrap.** Order: products, then every stock movement that has no event yet (opening balances included), then patients, then prescriptions with their items. The shop row itself is not an event; the owner registers that `public_id` before issuing the code. A row that already has a live `created` event is skipped. A row whose first live event is an update or a delete gets a predecessor `created` at version − 1 so the cloud can apply the real events afterwards. Event ids are a UUID5 of shop, entity, and version, so repeating a scan does not insert a second row. The cursor is `sync_state.bootstrap_stage` plus `bootstrap_cursor`, committed in the same transaction as the events. After the scan, only live events run.

**Results.** `applied` and `already_processed` mark the row synced and set `last_acknowledged_sequence`. `invalid_event` marks that row `failed` and stores `invalid_event:<code>`. `ordering_conflict` and `retryable_error` leave the row pending, store the code on the row, and set `last_error`; they are not skipped. A timeout, DNS failure, connection error, HTTP 429, or HTTP 5xx leaves every row pending, stores a short code (`offline`, `timeout`, `dns`, `http_503`, …), and waits. The wait is `Retry-After` when the server sends one (capped at one hour), otherwise half to all of the 30s, 60s, 120s … backoff, with jitter. A lost response is safe: the next push is `already_processed` and stock does not move twice.

**What the screen shows.** `not_activated`, `syncing` (a cycle is running, or rows are waiting and the last error is not a connection problem), `waiting` (offline, DNS, timeout, 429, 5xx), `error` (a failed event, a rejected device code, a missing address, or an ordering conflict), `synced` (activated, nothing pending, nothing failed). The diagnostic list is event id, entity type, sequence, and the error code. No payload, no patient text, no device secret. The cloud's `reported_pending` stays whatever the shop last sent; a shop that has not reported has `null`, not zero.

**Logging.** One INFO line per cycle: shop id, event count or the failure code. No body, no token.

