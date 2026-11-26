# Local development

Written in phase 05 (26 November 2026). Commands were run on macOS with Python 3.14.6 and Node.js 24.3.0. Windows has not been tried yet; on Windows use `.venv\Scripts\python` where this page says `.venv/bin/python`.

The desktop app needs no internet and no cloud settings. It talks only to the local API on `127.0.0.1:8000`. There is no `CLOUD_API_URL` yet; sync starts in phase 06.

## One-time setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # app deps + pytest + httpx2

cd ../desktop
npm install
```

`requirements.txt` is enough to run the API. `requirements-dev.txt` adds the test tools.

## Run the API

```bash
cd backend
.venv/bin/python run.py
```

- Serves `http://127.0.0.1:8000` (auto-reload on code changes). API docs: `http://127.0.0.1:8000/docs`.
- On startup it migrates the database to the latest revision. If a migration is pending and the file already has data, it first writes `backups/pharmacy-<UTC time>-pre-migration-<revision>.db` next to the database.
- An empty database shows **Set up this shop** in the app: enter the pharmacy details and choose the manager's username and password. There is no default account.
- Sample data for development (only into an empty pharmacy table, and no account):

  ```bash
  PHARMACARE_DEMO_DATA=1 .venv/bin/python run.py
  ```

## Run the desktop app

In a second terminal, with the API running:

```bash
cd desktop
npm run dev        # Vite on 127.0.0.1:5173 plus an Electron window
# or
npm run start:ui   # Vite only; open http://127.0.0.1:5173 in a browser
```

The UI reads the API address from the Electron preload (`desktop/electron/preload.js`) and falls back to `http://127.0.0.1:8000/api/v1` in a browser. Electron does not start the API yet; that is phase 09.

`npm run build` writes `desktop/dist/` for a packaged build.

## Where the database lives

One helper decides: `backend/src/core/paths.py`.

| Situation | Database file |
| --- | --- |
| `PHARMACARE_DATA_DIR=/some/folder` is set | `/some/folder/pharmacy.db` |
| `PHARMACARE_ENV=production`, or a frozen (PyInstaller) build | Windows `%LOCALAPPDATA%\PharmaCare\pharmacy.db`; macOS `~/Library/Application Support/PharmaCare/pharmacy.db`; Linux `~/.local/share/PharmaCare/pharmacy.db` |
| Otherwise (development) | `backend/data/pharmacy.db` |

Backups go to a `backups/` folder beside the database. `backend/data/*.db`, the backups folder, and SQLite's `-wal`/`-shm` files are git-ignored. Backup and restore: `docs/BACKUP_AND_RECOVERY.md`.

To try something on a throwaway database:

```bash
PHARMACARE_DATA_DIR=/tmp/pharmacare-try .venv/bin/python run.py
```

Development rules from `CLAUDE.md`: never delete or reset `backend/data/pharmacy.db`; synthetic test rows may be added to it; take a backup first (`.venv/bin/python -m src.backup_cli create`).

## Migrations

```bash
cd backend
.venv/bin/alembic current     # revision of the configured database
.venv/bin/alembic history     # all revisions
```

Prefer starting the API to apply migrations: it backs up first. A bare `.venv/bin/alembic upgrade head` does not take that backup. New schema changes are new files in `backend/migrations/versions/`; never call `create_all`.

## Tests

```bash
cd backend
.venv/bin/pytest            # whole suite
.venv/bin/pytest -v tests/test_prescriptions.py
```

- Each test uses its own temporary data folder and SQLite file. Tests never open `backend/data/pharmacy.db`.
- All test data is synthetic.
- `tests/test_prescriptions.py::test_works_with_no_cloud_host_and_no_network` blocks outgoing network calls and unsets `CLOUD_API_URL` while it creates a prescription, adjusts stock, and searches patients.
- There are no automated desktop (React) tests yet. `cd desktop && npx vite build` is the frontend check.

## Useful checks

```bash
cd backend
sqlite3 data/pharmacy.db ".tables"
.venv/bin/python -m src.backup_cli list
```
