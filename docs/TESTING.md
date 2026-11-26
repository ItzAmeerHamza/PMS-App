# Testing strategy

No automated tests exist yet. Each phase adds the tests listed in its file and records the command plus the result in `docs/PROGRESS.md`. A phase is not done if its tests were not run. If a test cannot be run on the current machine, say so. Do not invent a passing result.

## Rules

- Use synthetic patients only. No real names, phone numbers, or prescriptions.
- Tests must not point at a production Railway or Vercel project.
- Local tests use a temporary SQLite file. They must not delete `backend/data/pharmacy.db`.
- Cloud tests use PostgreSQL. Skip them with a clear message if PostgreSQL is not available, and say they were not verified.
- Do not mock the database for transaction, migration, or idempotency tests. Those tests are about real commits and rollbacks.
- HTTP tests for the local API must work with the network disabled or with the cloud base URL unset.
- Assertions on sync must prove a repeated `event_id` does not apply a stock delta twice.

## By phase

| Phase | Prove |
| --- | --- |
| 02 Local database | Migration on a database that already has rows. Foreign keys. Rollback of a failed business transaction. Password hash is not plaintext. Backup file can be restored. Startup does not recreate the file. |
| 03 Inventory | Create and edit a product. Receipt, reduction, and manual adjustment each write a movement and update the batch. Search and low-stock filter. History order. Sale and void still move the correct batches and now write movements. |
| 04 Patients | Create, search by name and phone, repeat visitor signal from prior prescriptions, update. Delete does not drop history that still needs a tombstone. |
| 05 Prescriptions | Create with items, second prescription does not erase the first, history is chronological, dispense fails cleanly when stock is short and writes nothing. |
| 06 Outbox | Business row and outbox row commit together and roll back together. One write, one event. Versions increase. Order by sequence. Restart leaves pending rows. Payload is enough to rebuild the entity. Nested calls do not duplicate events. |
| 07 Cloud API | Apply, duplicate, stale version, missing patient, shop isolation, bad credential, concurrent duplicate posts, stock movement applied once. |
| 07 Worker | Offline queue, upload after reconnect, lost acknowledgement, retry, invalid event stops retrying, bootstrap resumes, two shops stay isolated. |
| 08 Dashboard | Owner login, logout, MFA, rejected anonymous request, shop filter, pagination, empty and error states. Device credentials cannot open admin routes. |
| 09 Packaging | Covered by the packaging checklist. Automated tests still pass. Fresh-install checks that need Windows are listed as not verified when the build machine is not Windows. |
| 09 Final | End-to-end only with synthetic data. Record every failure. Production readiness is "not ready" until the critical checks have evidence. |

## Suggested layout

```
backend/tests/          local API, SQLite, outbox, worker with a fake cloud
cloud-api/tests/        PostgreSQL integration
dashboard/              unit and route tests next to the Next.js app
```

Put fixtures in code, not in the developer's real `pharmacy.db`.

## Commands

Record the exact commands in `PROGRESS.md` after they exist. Expected shape:

```
cd backend && .venv/bin/pytest
cd cloud-api && pytest
cd dashboard && npm test
```

Until those projects and configs exist, do not document them as already runnable.

## Definition of a passing phase

- New tests cover the acceptance criteria in that phase file.
- The full relevant suite was executed in this session.
- Failures are written down, not hidden by skipping.
- Existing inventory, patient, prescription, and billing behavior still passes.
