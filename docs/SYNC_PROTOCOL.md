# Offline synchronization rules

Status: design only. No `sync_outbox` table, worker, or cloud API exists yet. Phase 06 creates the local outbox. Phase 07 Part A creates the cloud ingest API. Phase 07 Part B creates the worker. Do not implement any of that before those phases.

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
