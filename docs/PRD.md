# Product requirements

PharmaCare is an offline-first Windows desktop application for independent pharmacy and medical shops. The owner later reviews synchronized records from every shop in a private web dashboard. This document is the product contract. Technical design lives in `ARCHITECTURE.md`, `DATABASE.md`, and `SYNC_PROTOCOL.md`.

## Users

| User | Where they work | What they can do |
| --- | --- | --- |
| Shop manager | One Windows computer in one shop | Inventory, patients, prescriptions, and the existing billing screens. No patient-facing app. |
| Owner | Private web dashboard | Read inventory, patients, prescriptions, and sync status for every shop. Cannot change shop stock or prescriptions in this version. |

Each shop operates independently. A shop cannot read or change another shop's products, patients, prescriptions, or bills.

## Problem

Shops must keep selling and dispensing when the internet is down. The owner still needs a later view of what each shop holds and what was prescribed. Cloud failure must never block the counter.

## Product scope

### In this version

1. **Inventory.** Products, current stock, stock additions, stock reductions, manual adjustments, search, filters, and a movement history. Quantity changes are auditable. The existing batch, expiry, and FIFO behavior stays.
2. **Patients.** Create and search patients, recognize repeat visitors, and keep visit history. Only the shop manager uses this. There is no patient login or patient portal.
3. **Prescriptions.** Record a prescription against a patient, record medicines and quantities, and keep every past prescription when a new one is added. History is chronological.
4. **Offline operation.** Every shop function works with no internet. The desktop UI talks only to the local API.
5. **One-way sync.** Local saves are immediate. A background job later uploads changes to the central database. Sync is Shop → cloud only.
6. **Owner dashboard.** Read-only view of synchronized inventory, patients, prescriptions, and sync freshness across shops.
7. **Windows install.** A shop manager installs an `.exe` and launches the app. Python, Node.js, and SQLite are not separate installs.

### Already in the desktop app, and must be kept

Billing is implemented: counter sales, prescription-linked bills, FIFO stock allocation, and voids that restore the same batches. The owner dashboard does not need billing in this version. Stock changes caused by sales, voids, and dispensing must still be recorded, or the owner's inventory will be wrong.

### Out of scope

- Patient login, patient portal, or doctor portal.
- Cloud edits that push back into a shop.
- Conflict resolution between owner edits and offline shop edits.
- Shops reading each other's data.
- Celery, Redis, Kafka, or any distributed job system.
- Bundling a real shop database, production secrets, or cloud database credentials into the installer.

## Operating rules

- One computer per shop. One local database for that shop.
- SQLite is the operational source of truth at the shop.
- A local save succeeds before any network call.
- No internet is required for normal shop work, including before the shop is activated in the cloud.
- If the cloud is down, the manager can still add products, adjust stock, find a patient, create a prescription, and bill.
- The cloud learns the shop identity from the device credential, not from a shop id sent in the body and trusted blindly.
- The dashboard never connects to PostgreSQL from the browser. It uses the cloud API.
- The dashboard is read-only for business records. One-way sync stays in place until a later, separate project adds cloud-to-shop updates.

## Success criteria

- A manager can restart the app and still see inventory, patients, prescriptions, and bills.
- Days without internet do not lose local records or the events waiting to sync.
- The same event uploaded twice does not double-apply a stock movement or duplicate a patient or prescription.
- Two shops can use the same local numeric ids without overwriting each other in the central database.
- The owner can sign in, choose a shop, and see that shop's synchronized data, with a clear distinction between last-known sync time and live data.
- A fresh Windows PC can install and run the app without developer tools.

## Compliance note

Patient and prescription data is sensitive. Logs, sync status, and error screens must not include patient details or secrets. Pakistani pharmacy, health-record, privacy, and retention rules need external verification before production use. See `DECISIONS.md`.
