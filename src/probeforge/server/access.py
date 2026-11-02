"""Who may use the WebSocket (audit S2), in every mode: browsers only from an allowed Origin, and every run started
with a session token the served page fetched from GET /api/session-token (an HMAC of its issue time, valid for 10
minutes). A missing Origin header is a non-browser client: the token still applies to it.

Deployed (docs/DEPLOY.md), PROBEFORGE_ALLOWED_ORIGINS lists the demo's origin (https://demo.example.org) and only
those origins are accepted; without it (a local server) the page served by this server is allowed (same host).
PROBEFORGE_ALLOWED_HOSTS lists the host names the server answers for (server/app.py)."""

import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlparse

TOKEN_TTL_S = 600
_SECRET = os.environ.get("PROBEFORGE_TOKEN_SECRET", "").encode() or secrets.token_bytes(32)
# the Vite dev server proxies the UI from :5173; the page served by this server is always allowed (same host)
CONFIGURED_ORIGINS = {o.strip().rstrip("/").lower() for o in os.environ.get("PROBEFORGE_ALLOWED_ORIGINS", "").split(",")
                      if o.strip()}
ALLOWED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173", *CONFIGURED_ORIGINS}
ALLOWED_HOSTS = [h.strip().lower() for h in os.environ.get("PROBEFORGE_ALLOWED_HOSTS", "").split(",") if h.strip()]


def origin_allowed(origin: str | None, host: str | None, configured: set[str] | None = None) -> bool:
    configured = CONFIGURED_ORIGINS if configured is None else configured
    if not origin:
        return True
    if configured:  # deployed: exactly the demo's origins
        return origin.rstrip("/").lower() in configured
    if origin.rstrip("/") in ALLOWED_ORIGINS:
        return True
    return bool(host) and urlparse(origin).netloc.lower() == host.lower()


def issue(now: float | None = None) -> str:
    ts = str(int(now if now is not None else time.time()))
    return f"{ts}.{hmac.new(_SECRET, ts.encode(), hashlib.sha256).hexdigest()[:32]}"


def valid(token, now: float | None = None) -> bool:
    if not isinstance(token, str) or "." not in token:
        return False
    ts, mac = token.split(".", 1)
    if not ts.isdigit():
        return False
    age = (now if now is not None else time.time()) - int(ts)
    expected = hmac.new(_SECRET, ts.encode(), hashlib.sha256).hexdigest()[:32]
    return 0 <= age <= TOKEN_TTL_S and hmac.compare_digest(mac, expected)
