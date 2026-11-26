# Phase 05 — Prescriptions

Status: not started.
Depends on: `phases/04-patient-management.md` marked done.
Execute this phase only, then stop. This phase finishes the offline desktop work that must be stable before any cloud code.

## Read first

`docs/PRD.md`, `docs/DATABASE.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`, `docs/TESTING.md`, `backend/src/prescriptions/service.py`, and `desktop/src/pages/PrescriptionForm.jsx`.

## Goal

The manager can record a prescription for a patient, with medicines and quantities, and can read that patient's prescriptions from oldest to newest. Adding a prescription never updates or deletes an older one.

## Requirements

- Create a prescription only for a patient in the same pharmacy, with at least one medicine from that pharmacy's active catalog.
- Store dosage, frequency, duration, quantity, and instructions on the line. Keep the copied medicine name, salt, and manufacturer so later catalog edits do not rewrite history.
- Listing supports pharmacy scope, patient filter, and chronological order.
- Status values that already exist (`recorded`, `dispensed`, `cancelled`) stay. Dispense still uses FIFO and, after phase 03, writes `dispense` movements in the same transaction. If stock is insufficient, the prescription stays `recorded` and no batch changes are committed.
- Cancelling a dispensed prescription stays forbidden.
- The manager is the only user. Do not add patient login.
- The local API must work with no `CLOUD_API_URL` and with no network.
- Business writes go through the service layer in one transaction. Do not add outbox rows yet.

Reuse `Prescriptions.jsx`, `PrescriptionForm.jsx`, and `PrescriptionDetail.jsx`.

## Tests

Cover this phase and confirm the earlier local tests still pass:

- Create a prescription with two items. Both are stored.
- A second prescription for the same patient leaves the first unchanged.
- History for that patient is chronological.
- A medicine from another pharmacy is rejected.
- Dispense with enough stock writes movements and sets `dispensed`.
- Dispense without enough stock rolls back.
- Creating a prescription, adjusting stock, and looking up a patient all succeed when no cloud host is configured.

## Also update

- `docs/PROGRESS.md` so a reader can see that the offline shop app is feature-complete for local inventory, patients, and prescriptions, and that sync is not started.
- `docs/LOCAL_DEVELOPMENT.md` with the exact commands to run the API and the Electron app, how the database path is chosen, and how to run tests.

## Out of scope

- `sync_outbox`, Railway, Vercel, the sync worker, and the Windows installer.

## Done when

A manager can use inventory and prescriptions offline, restart the API, and see the same rows. Tests were run and the results are in `docs/PROGRESS.md`.

## Review, then stop

1. Run the backend test suite.
2. Check for missing imports, a migration that recreates tables, and any write path that still changes stock without a movement.
3. Confirm billing void still restores stock.
4. Update `docs/PROGRESS.md`. Next file: `phases/06-sync-outbox.md`.
5. State anything you could not verify in the UI.
6. Stop. Do not begin phase 06.
