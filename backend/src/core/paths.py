"""Where PharmaCare keeps its SQLite file and backups.

Every part of the app asks this module for paths. Nothing else builds a database path.

Resolution order:
1. ``PHARMACARE_DATA_DIR`` if set (tests, packaging, or a manual override).
2. Installed builds (``PHARMACARE_ENV=production`` or a frozen PyInstaller binary):
   the per-user application-data directory, outside the install folder.
     Windows: %LOCALAPPDATA%\\PharmaCare
     macOS:   ~/Library/Application Support/PharmaCare
     Linux:   $XDG_DATA_HOME/PharmaCare or ~/.local/share/PharmaCare
3. Development: ``backend/data`` in the source tree.
"""

import os
import sys
from pathlib import Path

APP_DIR_NAME = "PharmaCare"
DB_FILENAME = "pharmacy.db"
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def is_production() -> bool:
    return os.environ.get("PHARMACARE_ENV", "").lower() == "production" or bool(getattr(sys, "frozen", False))


def _user_data_root() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME


def data_dir() -> Path:
    override = os.environ.get("PHARMACARE_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif is_production():
        path = _user_data_root()
    else:
        path = BACKEND_ROOT / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / DB_FILENAME


def backup_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path
