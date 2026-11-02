# ProbeForge public demo image (docs/DEPLOY.md). Three stages: the web build, the Python environment, the runtime.
# The runtime stage has no compilers, no node and no uv; it runs as a non-root user. No secret is ever copied in:
# the Meta API key reaches the container from the server's env file at run time.

FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS python
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock LICENSE NOTICE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
# editable install: the server finds scenarios/, results/ and web/ relative to /app/src, so the app stays at /app
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
# no package installer in the runtime (the app's packages come from the .venv built above)
RUN python -m pip uninstall -y pip setuptools wheel 2>/dev/null; rm -f /usr/local/bin/pip*
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin probeforge
WORKDIR /app
COPY --from=python /app/.venv ./.venv
COPY --from=python /app/src ./src
COPY pyproject.toml LICENSE NOTICE ./
COPY scenarios/ ./scenarios/
# the committed runs: the never-tier count shown under the action limits is computed from them at startup
COPY results/runs/ ./results/runs/
COPY docs/ATS_TROUBLESHOOTING.json ./docs/ATS_TROUBLESHOOTING.json
COPY --from=web /web/dist ./web/dist
# runs/ is the persistent volume: the public spend ledger, visitor traces, Compare records, the UI run list
RUN mkdir -p /app/runs && chown probeforge:probeforge /app/runs
USER probeforge
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PROBEFORGE_HOST=0.0.0.0 PROBEFORGE_PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status != 200)"]
CMD ["python", "-m", "probeforge.server"]
