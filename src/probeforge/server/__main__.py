"""Run the web UI backend:  uv run python -m probeforge.server [--port 8000]"""

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    ap_limits = {"limit_concurrency": 100,  # requests and sockets at once, beyond the app's own caps
                 "ws_max_size": 65536,  # every client message is small JSON (audit S2: the default is 16 MiB)
                 "timeout_keep_alive": 10}
    uvicorn.run("probeforge.server.app:app", host=args.host, port=args.port, **ap_limits)


if __name__ == "__main__":
    main()
