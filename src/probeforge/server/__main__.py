"""Run the web UI backend:  uv run python -m probeforge.server [--port 8000]

Behind a reverse proxy (docs/DEPLOY.md): PROBEFORGE_HOST (default 127.0.0.1; 0.0.0.0 in the container) and
PROBEFORGE_FORWARDED_ALLOW_IPS, the proxy's address. Only then are X-Forwarded-For headers read, and only from that
address, so the per-address connection limit sees the visitor, not the proxy, and a visitor cannot pick an address.
"""

import argparse
import os

import uvicorn


def uvicorn_options(env=os.environ) -> dict:
    """The uvicorn settings: limits for every mode, proxy headers only from the configured proxy."""
    proxy = env.get("PROBEFORGE_FORWARDED_ALLOW_IPS", "").strip()
    return {"limit_concurrency": 100,  # requests and sockets at once, beyond the app's own caps
            "ws_max_size": 65536,  # every client message is small JSON (audit S2: the default is 16 MiB)
            "timeout_keep_alive": 10,
            "proxy_headers": bool(proxy),
            "forwarded_allow_ips": proxy or None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("PROBEFORGE_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PROBEFORGE_PORT", "8000")))
    args = ap.parse_args()
    uvicorn.run("probeforge.server.app:app", host=args.host, port=args.port, **uvicorn_options())


if __name__ == "__main__":
    main()
