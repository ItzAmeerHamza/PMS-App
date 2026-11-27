# Local development

Written in phase 05 (26 November 2026). Commands were run on macOS with Python 3.14.6 and Node.js 24.3.0. Windows has not been tried yet; on Windows use `.venv\Scripts\python` where this page says `.venv/bin/python`.

The desktop app needs no internet and no cloud settings to sell, stock, and record patients. It talks only to the local API on `127.0.0.1:8000`. A sync worker starts with that API and does nothing until the Sync page has a device code. Set `CLOUD_API_URL` (or `PHARMACARE_CLOUD_API_URL`) to the cloud API origin, for example `http://127.0.0.1:8800`, or type that address on the Sync page. `PHARMACARE_SYNC_AUTOSTART=0` leaves the worker thread off.

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

## Cloud API (`cloud-api/`, phase 07 Part A)

Separate app with its own virtualenv. The desktop backend does not import it and starts without it.

```bash
cd cloud-api
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

It needs PostgreSQL. On the development Mac, Homebrew PostgreSQL 14 runs on `localhost:5432` with two databases created for this project: `pharmacare_cloud_dev` (manual runs) and `pharmacare_cloud_test` (tests; its schema is dropped and rebuilt on every test run).

Run it:

```bash
cd cloud-api
export DATABASE_URL=postgresql://localhost/pharmacare_cloud_dev
.venv/bin/alembic upgrade head
OWNER_PASSWORD='<at least 12 characters>' .venv/bin/python -m app.cli create-owner --email you@example.com
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8800
```

API docs: `http://127.0.0.1:8800/docs`. Owner sign-in is a password step and then a TOTP code (`GET /api/v1/owner/csrf`, then `POST /api/v1/owner/login`, then `POST /api/v1/owner/totp`). The first sign-in shows an authenticator key. Register a shop and issue a device token as in `docs/RAILWAY_DEPLOYMENT.md`.

## Owner dashboard (`dashboard/`)

```bash
cd dashboard
npm install
CLOUD_API_URL=http://127.0.0.1:8800 npm run dev
```

Opens `http://127.0.0.1:3000`. The page talks to the Next.js server. That server calls the cloud API. `npm test` runs the dashboard checks. `npm run build` writes `.next/`.

Tests:

```bash
cd cloud-api
.venv/bin/pytest            # uses CLOUD_TEST_DATABASE_URL, default postgresql+psycopg://localhost/pharmacare_cloud_test
```

If PostgreSQL is not reachable, every cloud test is reported as skipped with the reason; none is reported as passed.

`tests/fixtures/desktop_events.json` holds synthetic events exported from the real desktop outbox. Regenerate it after changing an event payload on the desktop:

```bash
cd backend && .venv/bin/python ../cloud-api/tests/make_desktop_fixture.py
```

