# Phase 03 — Inventory management

Status: not started.
Depends on: `phases/02-local-database.md` marked done.
Execute this phase only, then stop.

## Read first

`docs/PRD.md`, `docs/DATABASE.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`, `backend/src/inventory/service.py`, and `backend/src/billing/service.py`.

## Goal

Inventory stays auditable. The shop manager can create and edit products, see current stock, add stock, reduce stock, adjust stock, search and filter, and read movement history. This works with no internet.

## Keep working

- Products are the existing `medicines` table. Do not rename it.
- Batches, expiry dates, reorder levels, CSV import, and FIFO allocation stay.
- Quantity on hand remains the sum of batch quantities. Do not replace batches with a single overwritten number.
- Sales and voids keep using `allocate_stock` and `sale_allocations`.
- Reuse `desktop/src/pages/Inventory.jsx` and `desktop/src/api/client.js`. Extend them instead of replacing the page.

## Requirements

Add `stock_movements` as specified in `docs/DATABASE.md`.

Every change to a batch quantity writes one movement in the same transaction:

| Action | movement_type | quantity_delta |
| --- | --- | --- |
| New batch or stock receipt | receipt | positive |
| Manual increase or decrease | adjustment | signed |
| Dispense | dispense | negative |
| Sale | sale | negative |
| Void of a sale | void | positive |

`adjust_batch` must not update `quantity` without a movement. `allocate_stock` must not decrement a batch without a movement. If allocation fails because stock is short, no batch and no movement is saved.

Expose:

- Current inventory, including quantity and nearest expiry, as the UI already expects.
- Search and low-stock filter, already present; keep them correct after the ledger exists.
- A movement history endpoint for one product, chronological, with type, delta, batch, and time.

Manual adjustment from the UI asks for a direction and a quantity and records the reason on the movement.

All of this is local. No Railway client.

## Tests

- Create and update a product.
- Receipt, reduction, and adjustment write the expected movement and the expected batch quantity.
- A negative adjustment that would cross zero rolls back the batch and writes no movement.
- Dispense and sale decrement the earliest-expiring batch and write movements.
- Void restores the same batch and writes a void movement.
- History returns in a stable order.
- Search and low-stock filter still match the current API behavior.

## Out of scope

- Patient rules, except not breaking them.
- Outbox events. Structure the inventory transaction so phase 06 can add an event before commit, but do not insert outbox rows yet.
- Cloud, dashboard, packaging.

## Done when

- The inventory and billing stock paths are ledger-backed.
- Tests were run and recorded in `docs/PROGRESS.md`.
- `docs/DATABASE.md` describes `stock_movements` as implemented.

## Review, then stop

1. Run the inventory tests.
2. Check that a short-stock dispense or sale does not leave a partial decrement.
3. Update `docs/PROGRESS.md`. Next file: `phases/04-patient-management.md`.
4. Stop. Do not begin phase 04.
