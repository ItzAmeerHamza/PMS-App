"""Device credential storage.

The cloud shows a device token once. This module stores it on the shop PC and
reads it back for the worker. It never logs the token and never puts it in SQLite.

- Windows: DPAPI (CryptProtectData), current user. The file holds the protected blob.
- macOS and Linux: a file outside the repository, mode 0600, in the data directory.
  The directory is mode 0700. Development data lives in ``backend/data/secrets/``,
  which is git-ignored.

Anyone who can log in as the same Windows user, or who can read the file on macOS,
can read the token. That is the same trust boundary as the shop's SQLite file.
"""

import base64
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

from ..core.paths import data_dir

FILE_NAME = "device-credential"
SCHEME_FILE = "file"
SCHEME_DPAPI = "dpapi"


class CredentialError(ValueError):
    pass


def secrets_dir() -> Path:
    path = data_dir() / "secrets"
    path.mkdir(parents=True, exist_ok=True)
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o700)
    return path


def credential_path() -> Path:
    return secrets_dir() / FILE_NAME


def _use_dpapi() -> bool:
    return sys.platform.startswith("win")


def parse_device_token(token: str) -> str:
    """Return the stripped token, or raise CredentialError. Does not echo the value."""
    token = (token or "").strip()
    if not token.startswith("pcd_") or "." not in token:
        raise CredentialError("Enter the device code from the owner. It starts with pcd_.")
    device, secret = token[4:].split(".", 1)
    if len(secret) < 16:
        raise CredentialError("Enter the device code from the owner. It starts with pcd_.")
    try:
        uuid.UUID(device)
    except ValueError:
        raise CredentialError("Enter the device code from the owner. It starts with pcd_.") from None
    return token


def check_cloud_url(url: str) -> str:
    """Accept http or https with a host and no password embedded in the address."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
    ):
        raise CredentialError("Enter an http or https address without a password in it.")
    return url


def cloud_base_url(stored: str | None) -> str:
    """Environment wins over the address saved at activation, so tests and deploys can override it."""
    env = os.environ.get("PHARMACARE_CLOUD_API_URL", "").strip() or os.environ.get("CLOUD_API_URL", "").strip()
    return (env or (stored or "")).strip().rstrip("/")


def store_credential(token: str) -> None:
    token = parse_device_token(token)
    scheme = SCHEME_DPAPI if _use_dpapi() else SCHEME_FILE
    blob = _protect(token.encode()) if scheme == SCHEME_DPAPI else token.encode()
    body = json.dumps({"v": 1, "scheme": scheme, "token": base64.b64encode(blob).decode("ascii")})
    path = credential_path()
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".device-credential.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        if not sys.platform.startswith("win"):
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        if not sys.platform.startswith("win"):
            os.chmod(path, 0o600)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def read_credential() -> str | None:
    path = credential_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        blob = base64.b64decode(data["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    scheme = data.get("scheme")
    try:
        if scheme == SCHEME_DPAPI:
            raw = _unprotect(blob)
        elif scheme == SCHEME_FILE:
            raw = blob
        else:
            return None
        return raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _protect(plain: bytes) -> bytes:
    return _crypt(plain, protect=True)


def _unprotect(protected: bytes) -> bytes:
    return _crypt(protected, protect=False)


def _crypt(data: bytes, *, protect: bool) -> bytes:
    """DPAPI. The input buffer stays referenced until the call returns."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data, len(data))
    incoming = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    outgoing = DATA_BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    # Declare pointer-sized arguments so a 64-bit address is not truncated.
    blob_ptr = ctypes.POINTER(DATA_BLOB)
    descr = ctypes.c_wchar_p()
    if protect:
        function = crypt32.CryptProtectData
        function.argtypes = [blob_ptr, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_ptr]
        second = None
    else:
        function = crypt32.CryptUnprotectData
        function.argtypes = [blob_ptr, ctypes.POINTER(ctypes.c_wchar_p), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_ptr]
        second = ctypes.byref(descr)
    function.restype = wintypes.BOOL
    ok = function(ctypes.byref(incoming), second, None, None, None, 0, ctypes.byref(outgoing))
    if not ok:
        raise OSError(ctypes.get_last_error() or "Windows could not protect the device credential")
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel32.LocalFree(outgoing.pbData)
        if descr:
            kernel32.LocalFree(descr)
