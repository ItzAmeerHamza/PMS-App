"""HTTPS push to the cloud sync API. Stdlib only, so the shop app gains no HTTP dependency.

Timeouts and connection failures raise TransportError. The event rows stay pending;
the worker decides when to try again. Nothing here logs the token, the URL's user
info, or the request body.
"""

import json
import socket
import urllib.error
import urllib.request


class TransportError(Exception):
    def __init__(self, code: str, *, retryable: bool = True, retry_after: float | None = None):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after


class HttpTransport:
    def push(self, base_url: str, token: str, body: dict, timeout: float) -> dict:
        url = base_url.rstrip("/") + "/api/v1/sync/push"
        payload = json.dumps(body).encode()
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "PharmaCare-Sync",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            retry_after = _retry_after(exc.headers.get("Retry-After") if exc.headers else None)
            if exc.code == 429 or 500 <= exc.code <= 599:
                raise TransportError(f"http_{exc.code}", retry_after=retry_after) from None
            if exc.code in (401, 403):
                raise TransportError("device_rejected") from None
            raise TransportError(f"http_{exc.code}") from None
        except (TimeoutError, socket.timeout):
            raise TransportError("timeout") from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise TransportError("timeout") from None
            if isinstance(reason, socket.gaierror):
                raise TransportError("dns") from None
            raise TransportError("offline") from None
        except OSError:
            raise TransportError("offline") from None
        try:
            parsed = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TransportError("bad_response") from None
        if not isinstance(parsed, dict) or not isinstance(parsed.get("results"), list):
            raise TransportError("bad_response")
        return parsed


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return seconds
