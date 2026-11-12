# PharmaCare API

FastAPI backend for the pharmacy desktop app. Inventory, patients, and prescriptions are scoped per pharmacy.

## Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

API docs: http://127.0.0.1:8000/docs

SQLite database is created at `backend/data/pharmacy.db` on first start, with sample medicines, patients, and prescriptions.
