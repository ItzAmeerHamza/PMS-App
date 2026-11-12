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

First API start creates `backend/data/pharmacy.db` and seeds City Care Pharmacy with sample medicines, patients, and prescriptions.

## What is in this scaffold

- Inventory: medicines, batches, expiry, reorder alerts
- Patients: profile + visit history
- Prescriptions: record a visit, then dispense (stock is reduced FIFO by expiry)
- Dashboard: low stock, expiring batches, recent visits
