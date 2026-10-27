"""Run the web UI backend:  uv run python -m probeforge.server [--port 8000]"""

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run("probeforge.server.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
