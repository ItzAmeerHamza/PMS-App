# Phase 08 — Owner dashboard

Status: not started.
Depends on: `phases/07-cloud-backend.md` Part A marked done. Part B should already be done so the dashboard has data to show, but the dashboard itself only reads the cloud API.
Execute this phase only, then stop.

## Read first

`docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/SYNC_PROTOCOL.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`, and the cloud admin routes.

## Goal

A private Next.js dashboard where the owner can view synchronized inventory, patients, and prescriptions for every shop. Business records are read-only. The browser never connects to PostgreSQL and never sees the database password.

## Technology

- `dashboard/` Next.js app, TypeScript, Tailwind, a simple component set such as shadcn/ui.
- Data comes from the Railway FastAPI admin API.
- No extra background jobs on Vercel. Railway keeps doing ingest.

## Authentication

Implement owner login against the cloud API:

- Argon2id or the hash already chosen for the owner in phase 07.
- TOTP MFA.
- HTTP-only, Secure, SameSite session cookie.
- Session expiry and logout.
- Login rate limiting.
- CSRF protection on cookie-authenticated mutations (login, logout, MFA).
- Admin routes enforce the owner on the server. A shop device credential still cannot call them.
- Next.js server-side code holds the session. Do not put the Railway admin secret or database URL in client JavaScript.

If phase 07 left owner endpoints incomplete, add the missing auth endpoints in `cloud-api/` now. Do not fork a second API inside Vercel.

## Pages

Use a plain admin layout: sidebar, cards, tables, search, filters, pagination, loading, empty, and error states. Clarity over decoration.

### Home

Total shops, products, patients, prescriptions, stock summary, recent movements, recent prescriptions, and each shop's last sync. Shop selector and date filters.

### Shops

Name, shop id, registration date, last sync time, last event, sync status. Stale data is labeled with the time it was last reported. Do not treat a silent shop as empty or fully synced.

### Inventory

Shop filter, product search, detail, current quantity, low stock, movement history, date filter. Server-side pagination.

### Patients

Search by name and phone, filter by shop, detail, visit history, prescriptions in chronological order. Behind login. No patient portal.

### Prescriptions

List, patient, date, medicines, quantities, instructions, shop filter, date filter. Use the API's real fields.

### Sync

Per shop: last successful sync, last event, reported errors, freshness, and pending backlog only when the shop actually reported it. Separate "last known" from "live".

## Deployment prep, without deploying

Write `docs/VERCEL_DEPLOYMENT.md` with build command, environment variable names, the Railway API base URL, cookie settings for production, and a note that the Vercel Hobby plan is not the assumption for commercial use.

Do not deploy unless the user explicitly asks in a later session.

## Tests

- Login and logout.
- MFA success and a wrong code.
- Anonymous request to a dashboard page or admin API is rejected.
- Shop filter changes the inventory, patients, and prescriptions shown.
- Pagination.
- API failure shows an error state and no stale data presented as fresh.
- A disconnected shop's sync card does not say the backlog is zero.

## Out of scope

- Editing products, stock, patients, or prescriptions from the dashboard.
- Windows installer.
- Pushing data from the dashboard back to a shop.

## Done when

The dashboard runs locally, an owner can sign in, select a shop, and read data that was written to PostgreSQL by the sync API. Test results are in `docs/PROGRESS.md`.

## Review, then stop

1. Run dashboard tests and cloud admin auth tests.
2. Confirm no client bundle contains a database URL or device secret. Search the client build output if a build was produced.
3. Update `docs/PROGRESS.md` and `docs/VERCEL_DEPLOYMENT.md`.
4. Next file, only in a later session: `phases/09-testing-and-deployment.md` Part A.
5. Stop.
