# Backup and recovery

Written in phase 02 (26 November 2026). Code: `backend/src/core/paths.py`, `backend/src/core/backup.py`, `backend/src/backup_cli.py`, `backend/src/core/migrate.py`. Tests: `backend/tests/test_startup_and_backup.py`.

The shop's SQLite file holds patient and prescription data. Every copy of it, including backups, is sensitive. Keep backups on the shop computer or on storage the owner controls, and do not email or upload them to shared folders.

## Where the database lives

`backend/src/core/paths.py` is the only place that decides the path.

| Situation | Data folder | Database file |
| --- | --- | --- |
| `PHARMACARE_DATA_DIR` is set | that folder | `<folder>/pharmacy.db` |
| Installed build on Windows (`PHARMACARE_ENV=production` or a PyInstaller binary) | `%LOCALAPPDATA%\PharmaCare` | `%LOCALAPPDATA%\PharmaCare\pharmacy.db` |
| Installed build on macOS | `~/Library/Application Support/PharmaCare` | `.../PharmaCare/pharmacy.db` |
| Installed build on Linux | `$XDG_DATA_HOME/PharmaCare` or `~/.local/share/PharmaCare` | `.../PharmaCare/pharmacy.db` |
| Development (default) | `backend/data` | `backend/data/pharmacy.db` |

The folder is outside the install directory, so uninstalling or updating the app does not delete it. Backups go to a `backups` folder inside the data folder.

Because the database runs in WAL mode, you will often see `pharmacy.db-wal` and `pharmacy.db-shm` next to `pharmacy.db`. They are part of the live database. Never copy only `pharmacy.db` with Explorer or Finder while the app is running, and never delete the `-wal` file: it can hold the most recent changes.

## Automatic backups

- **Before every schema migration.** On startup, if the database already has tables and a migration is pending, the app writes `backups/pharmacy-<UTC time>-pre-migration-<revision>.db` before changing anything.
- The newest 30 backups are kept; older ones are deleted automatically.

There is no scheduled daily backup yet. Until there is, take a manual backup at the end of each working day.

## Take a backup by hand

Safe while the app is running. It uses SQLite's backup API, which copies a consistent snapshot including anything still in the `-wal` file.

```
cd backend
.venv/bin/python -m src.backup_cli create
```

On a Windows installed build, run the same module with the bundled Python once packaging exists (phase 09). Until then the command runs from the developer checkout.

Each backup is a single standalone `.db` file. It is checked with `PRAGMA integrity_check` before it is kept. To store a backup elsewhere, copy that one file to a USB drive or other storage the owner controls.

List backups, newest first:

```
.venv/bin/python -m src.backup_cli list
```

## Restore a backup

Restoring replaces the live database. Anything entered after the backup was taken is not in the restored file.

1. Close PharmaCare completely, including the backend process. Restore refuses to run without `--yes`, which confirms you did this.
2. Pick the backup: `.venv/bin/python -m src.backup_cli list`
3. Restore it:

   ```
   .venv/bin/python -m src.backup_cli restore <path-to-backup.db> --yes
   ```

   The tool:
   - checks the backup's integrity and refuses a damaged file;
   - folds the current `-wal` into the current database and keeps it as `pharmacy.db.before-restore-<UTC time>` (nothing is deleted);
   - removes the old `-wal` and `-shm` files;
   - copies the backup into place and checks it again.
4. Start PharmaCare. If the backup is older than the current code, startup migrates it forward (and takes another `pre-migration` backup first).
5. Sign in and check today's bills, recent prescriptions, and a few stock levels.

If the restored data is wrong, stop the app and restore the `pharmacy.db.before-restore-...` file the same way.

### Manual restore without the tool

Only if the tool cannot run:

1. Stop PharmaCare.
2. Rename `pharmacy.db`, `pharmacy.db-wal`, and `pharmacy.db-shm` (if present) by adding `.old`. Do not delete them.
3. Copy the backup file into the data folder and name it `pharmacy.db`.
4. Start PharmaCare.

## Upgrading an existing development database

The first start after phase 02 migrates `backend/data/pharmacy.db` from the pre-Alembic schema to the current revision, after writing a `pre-migration-legacy` backup. An existing manager password keeps working; it is re-hashed with Argon2id on the next successful sign-in.

## What was tested

- Backup taken while recent writes were still in the WAL contained those writes.
- Restore brought back deleted rows and kept the replaced database beside it.
- A corrupt backup was refused and the live file was left unchanged.
- Startup twice on an existing file kept the same file (same inode) and the same rows.
- A copy of the developer database migrated with all rows kept and a `pre-migration-legacy` backup written.

Not tested: Windows paths on a real Windows machine, restore while the app is still running (the procedure forbids it), and disk-full or power-loss during a backup.
