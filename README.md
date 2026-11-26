# PharmaCare

Desktop pharmacy app for **per-pharmacy inventory** and **patient prescription history**.

```
backend/   FastAPI + SQLite
desktop/   Electron + React
```

Older store-POS and clinic files under `src/`, `public/`, and `client/` are leftover and not used by this scaffold.

## Run locally

Terminal 1 — API:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Terminal 2 — desktop:

```bash
cd desktop
npm install
npm run start:ui      # browser at http://127.0.0.1:5173
# or
npm run dev           # Electron window
```

The first API start creates `backend/data/pharmacy.db` (or migrates an existing one, after writing a backup to `backend/data/backups/`). The app then shows a **Set up this shop** screen where you enter the pharmacy details and choose the manager's username and password. There is no default account.

For sample medicines, patients, and prescriptions in development, start the API with `PHARMACARE_DEMO_DATA=1 python run.py` on an empty database. You still create the manager on the setup screen.

Tests: `cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`

Full local setup, database location, migrations, and tests: `docs/LOCAL_DEVELOPMENT.md`.

Backups and restore: see `docs/BACKUP_AND_RECOVERY.md`. Data location: `backend/src/core/paths.py` (set `PHARMACARE_DATA_DIR` to use another folder).

## What is in this scaffold

- Inventory: medicines, batches, expiry, reorder alerts
- Patients: profile + visit history
- Prescriptions: record a visit, then dispense (stock is reduced FIFO by expiry)
- Dashboard: low stock, expiring batches, recent visits
