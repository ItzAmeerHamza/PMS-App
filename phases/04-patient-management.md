# Phase 04 — Patient management

Status: not started.
Depends on: `phases/03-inventory-management.md` marked done.
Execute this phase only, then stop.

## Read first

`docs/PRD.md`, `docs/DATABASE.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`, `backend/src/patients/service.py`, and `desktop/src/pages/Patients.jsx`.

The live patient model is `Patient` in `backend/src/models.py`. Ignore `backend/src/patients/models.py`.

## Goal

The shop manager can create a patient, search existing patients, see who has visited before, and open a patient's history. Only the manager uses this. There is no patient login and no patient portal.

## Requirements

- Keep create, update, and search by first name, last name, and phone.
- A repeat visitor is a patient who already has at least one prescription at this pharmacy. The API already returns `prescription_count` and `last_visit`. Make that visible in the patient list and patient detail, and do not treat a brand-new patient as a repeat visitor.
- Search stays scoped to the signed-in pharmacy. Do not return another pharmacy's patients.
- Do not hard-delete a patient who has prescriptions. Deactivation or a tombstone flag is allowed. The historical prescriptions must remain readable.
- A patient with no prescriptions may be removed only if the row can still be represented later as a delete event. Prefer a deleted flag over a physical delete.
- Do not log allergies, notes, phone numbers, or names.
- No internet required.

Reuse the existing patient pages and client methods.

## Tests

- Create a patient and read it back.
- Search by last name and by phone finds the patient. An unrelated string does not.
- A patient with a prescription is reported as a repeat visitor. A patient without one is not.
- Deleting or deactivating a patient with a prescription does not remove the prescription.
- A patient query for pharmacy A does not return pharmacy B.

## Out of scope

- New prescription editor behavior (phase 05).
- Outbox events (phase 06). Leave the patient write path as one transaction.
- Cloud, dashboard, packaging.
- Any patient-facing screen.

## Done when

- Patient create, search, repeat-visitor display, and history-preserving removal match the rules above.
- Tests were run and recorded in `docs/PROGRESS.md`.

## Review, then stop

1. Run the patient tests.
2. Confirm inventory and billing tests from phase 03 still pass.
3. Update `docs/PROGRESS.md`. Next file: `phases/05-prescriptions.md`.
4. Stop. Do not begin phase 05.
