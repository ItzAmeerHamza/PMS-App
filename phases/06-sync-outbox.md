# Phase 06 — Sync outbox

Status: not started.
Depends on: `phases/05-prescriptions.md` marked done.
This phase is the local half of synchronization. Execute it only, then stop.

## Read first

`docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/SYNC_PROTOCOL.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`.

## Goal

Whenever the manager changes inventory, a patient, or a prescription, the app writes a durable sync event in the same SQLite transaction as the business change. Saving locally never contacts the network.

Do not implement HTTP, Railway, or the background worker. Those are phase 07.

## Requirements

### Table

Add `sync_outbox` through an Alembic migration, matching `docs/SYNC_PROTOCOL.md`:

`id`, `sequence`, `event_id`, `shop_id`, `entity_type`, `entity_id`, `operation`, `entity_version`, `schema_version`, `payload`, `created_at`, `status`, `retry_count`, `next_attempt_at`, `last_error`, `synced_at`.

- `event_id` is a UUID with a unique constraint.
- `sequence` is monotonic for this database and is the ordering key.
- Timestamps are UTC.
- Index `(status, next_attempt_at, sequence)` for pending reads.

### Writes

Integrate event creation into the existing services. One transaction does all of this:

1. Apply the business change.
2. Insert the outbox row.
3. Commit, or roll back both.

Cover:

- product.created, product.updated, product.deleted
- stock.movement_created
- patient.created, patient.updated, patient.deleted
- prescription.created, prescription.updated, prescription.deleted

Use the payload rules in `docs/SYNC_PROTOCOL.md`. Stock changes are immutable movement events. Products, patients, and prescriptions use full snapshots. Deletes are tombstones. Do not physically discard a row before its tombstone exists.

Prescription snapshots include items. A sale or void does not need its own invoice event in this phase, but the stock movement it creates must have an outbox event.

Bump `version` on each successful update of a mutable entity. Repeated updates produce increasing versions. Do not rely on timestamps for order.

Guard against duplicate events if one service calls another. One business action produces the events that action actually implies (for example a receipt produces one movement event, not also a second product update that pretends to be a stock delta).

### Read model for the future worker

Implement a local service that can:

- List pending events in `sequence` order.
- Count pending, retryable, and failed events.
- Mark an event synced only when a caller supplies an acknowledgement. This phase's tests can call that function directly. There is no HTTP client.
- Record an error, increment `retry_count`, and set `next_attempt_at`.
- Leave acknowledged rows in place. Retention is configurable. Do not delete them immediately.

No frontend change is required beyond not breaking current screens. Do not add a sync indicator yet.

## Tests

- A product create commits the medicine and exactly one outbox row.
- Forcing a failure after the business insert and before commit leaves neither row.
- Two updates of one patient produce versions 2 and 3, in sequence order.
- Pending order is deterministic across a new session.
- A prescription snapshot contains its items and the patient `public_id`.
- A stock adjustment payload contains the delta, batch `public_id`, and medicine `public_id`.
- A second call that only reloads the screen does not create another event.
- Historical prescriptions remain after a new one is added, and only the new one has a new created event.

## Docs

Update `docs/SYNC_PROTOCOL.md` if the implementation had to differ from the design. Say why. Update `docs/PROGRESS.md`.

## Out of scope

- Any HTTP call to a cloud API.
- Worker loop, retry against the network, shop activation UI, bootstrap upload.
- Owner dashboard and Windows packaging.

## Done when

The local database can contain pending events for a patient, a prescription, and a stock change, and those rows survive a restart. Tests were run.

## Review, then stop

1. Run the outbox tests and the existing local suite.
2. Confirm no code path imports a Railway URL.
3. Update `docs/PROGRESS.md`. Next file: `phases/07-cloud-backend.md` Part A only.
4. Stop. Do not begin phase 07.
