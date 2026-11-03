# Deploying the public demo

From a fresh Ubuntu 24.04 VPS (4 vCPU, 6 to 8 GB RAM, any provider) to ProbeForge's public demo running 24/7 behind
HTTPS, with room for a second website on the same server. Nothing here needs the repository's history or a build
tool on your own machine: the server builds the image from a clone of the public repository.

## 1. What runs where

```
visitor ──HTTPS──> Caddy (container, ports 80/443, automatic certificates)
                     └──> app (container, port 8000 inside the Docker network only, PROBEFORGE_PUBLIC=1)
                            └──> volume probeforge-runs (/app/runs): public spend ledger, visitor traces,
                                 Compare records, UI run list: kept across restarts and redeploys
```

- The app runs as a non-root user in a read-only container with no build tools, one uvicorn process (the sessions
  live in memory). Only Caddy publishes ports.
- The app reads X-Forwarded-For only from Caddy's fixed address (172.30.0.10), so the per-address limit (two open
  sessions) counts the visitor, not the proxy, and a visitor cannot choose an address.
- The Origin check and the host check accept only the demo's own origin and host name, from the env file.
- The public spend limits are the defaults: $30 in total for the public ledger, $5 per day, $0.75 per run.
- At every start the app first simulates what a visitor would otherwise wait for: every candidate fault of the default
  saved read, the Engineer suggestion and the twin signatures. Until that is
  done, `/api/ready` answers 503, and Caddy, which checks it every 5 s, shows visitors a starting page that reloads
  itself (`deploy/status/starting.html`) instead of sending them to the app. `/api/health` stays the liveness check
  (Docker's health check) and also reports `ready`. The warm-up takes 2 to 3 minutes on a fast machine and up to
  about 10 on a small shared VPS (8.5 minutes measured on a 4 vCPU Contabo VPS), so every restart or redeploy shows
  the starting page that long; the first visitor afterwards waits for nothing.

## 2. What the image contains

Every path the server reads at run time, checked inside the image by `deploy/check_image.py` (the CI runs it on every
push):

| Path | Read by | Why |
|---|---|---|
| `src/probeforge/` | everything | the code (installed editable at `/app`: the server finds its data relative to it) |
| `scenarios/circuits/*.yaml` | the benches | the ATS and motor starter netlists |
| `scenarios/ats/*.yaml` | ATS sessions | the 12 dev cases |
| `scenarios/transcriptions/ats/*.yaml` | Hybrid | the two saved drawing reads |
| `scenarios/transcriptions/star_delta_*.yaml`, `scenarios/photos/` | motor starter Hybrid | local use only (hidden in public mode) |
| `scenarios/s*.yaml`, `scenarios/holdout_clean.yaml` | motor starter | local use only |
| `scenarios/engineer_traces/` | Compare | recorded engineer traces |
| `results/runs/` | ATS meta | the never-tier count under the action limits |
| `docs/ATS_TROUBLESHOOTING.json` | the troubleshooting sheet | |
| `web/dist/` | the page | built in the image |
| `runs/` | written | the volume |

Never in the image (`.dockerignore`, checked by `deploy/check_image.py`): `.env`, `docs/vendor/` (the vendor
drawings and their crops; without them the live re-read is unavailable, which public mode turns off anyway),
`docs/NEXT_STEPS.md`, `runs/`, `.git/`, the tests and scripts, `node_modules/`, the web sources.

## 3. Prepare the server (once)

As root on the fresh server, then never again as root:

1. A deploy user with your SSH key (public key only; the private key stays on your machine):
   ```
   adduser deploy
   usermod -aG sudo deploy
   install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
   install -m 600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
   ```
   Log in as `deploy` in a second terminal before the next step, and keep it open until SSH is tested.
2. SSH: keys only, no root login. Create `/etc/ssh/sshd_config.d/10-hardening.conf`:
   ```
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   PermitRootLogin no
   PubkeyAuthentication yes
   ```
   then `sudo sshd -t && sudo systemctl reload ssh`, and check a fresh `ssh deploy@<server>` works.
3. Firewall: only SSH, HTTP and HTTPS.
   ```
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow 22/tcp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw allow 443/udp
   sudo ufw enable
   ```
   Docker publishes container ports around ufw: that is why only Caddy publishes anything (80 and 443, allowed above),
   and the app has no published port.
4. fail2ban for SSH: `sudo apt install -y fail2ban`, then `/etc/fail2ban/jail.d/sshd.local`:
   ```
   [sshd]
   enabled = true
   backend = systemd
   ```
   and `sudo systemctl restart fail2ban`.
5. Security updates: `sudo apt install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades`
   (security updates only, the Ubuntu default).
6. Docker Engine and the compose plugin from Docker's own apt repository (docs.docker.com, "Install Docker Engine on
   Ubuntu"). Do not add `deploy` to the `docker` group (that is root-equivalent): the commands below use `sudo`, which
   also lets compose read the root-only env file.

## 4. Domain

HTTPS needs a domain name. Create an `A` record (and `AAAA` if the server has IPv6) for the demo's name, for example
`demo.example.org`, pointing at the server's address. Caddy then gets and renews a Let's Encrypt certificate on its own
the first time it starts; ports 80 and 443 must be reachable for that.

Until the domain points at the server, an IP-only test works over plain HTTP (section 6); do not share that address:
it has no HTTPS. Everything works over HTTP, including the WebSocket, the Origin check and the session token.

## 5. Settings and the key

Two files on the server, neither in the repository:

1. `/etc/probeforge/probeforge.env`, the app's env file, owned by root, mode 600. It holds the Meta API key and the
   allow-lists. Create it from `deploy/probeforge.env.example`:
   ```
   sudo install -d -m 700 /etc/probeforge
   sudo install -m 600 deploy/probeforge.env.example /etc/probeforge/probeforge.env
   sudo nano /etc/probeforge/probeforge.env
   ```
   Fill in, on the server only:
   - `META_API_KEY`: the demo's Meta API key. Type or paste it into this file and nowhere else (not in the repository,
     not in a chat, not in a shell command that ends up in the history).
   - `PROBEFORGE_TOKEN_SECRET`: a random value, `openssl rand -hex 32`, so session tokens survive a restart.
   - `PROBEFORGE_ALLOWED_ORIGINS=https://demo.example.org` and `PROBEFORGE_ALLOWED_HOSTS=demo.example.org`: the demo's
     origin and host name; the server accepts nothing else.
2. `deploy/.env`, compose's settings (not secret), from `deploy/compose.env.example`: `PROBEFORGE_DOMAIN`,
   `PROBEFORGE_TAG`, `PROBEFORGE_ENV_FILE`, `PROBEFORGE_CADDYFILE`. No ACME e-mail is needed: Caddy gets and renews
   the certificate without one (you only miss Let's Encrypt's expiry notices, which automatic renewal makes moot).

## 6. First start

As `deploy`:

```
git clone https://github.com/swd07/probeforge.git ~/probeforge
cd ~/probeforge/deploy
git rev-parse --short HEAD                        # the tag for this build
cp compose.env.example .env && nano .env          # the domain, PROBEFORGE_TAG=<that hash>
sudo docker compose up -d --build --wait
sudo docker compose ps                            # app: healthy, caddy: running
sudo docker compose exec app python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
                                                  # "ready": false while warming up, then true
```

For the first minutes after every start (2 to 3 on a fast machine, up to about 10 on a small shared VPS) the site shows
the starting page (section 1); that is expected.

IP-only test before the domain points here: in `deploy/.env` set `PROBEFORGE_CADDYFILE=Caddyfile.http`; in the env
file set `PROBEFORGE_ALLOWED_ORIGINS=http://<server IP>` and `PROBEFORGE_ALLOWED_HOSTS=<server IP>`; then
`sudo docker compose up -d --wait` and open `http://<server IP>/`. When the domain points at the server, switch back
(`PROBEFORGE_CADDYFILE=Caddyfile`, the https origin and the host name in the env file) and run the same command.

Then, from your own machine, the smoke test (no key, no paid call):

```
uv run python scripts/smoke_deploy.py https://demo.example.org --headers --browser
```

It first waits until the warm-up is done (checking the starting page if it sees it), then checks the health endpoint
and public mode, the page and its script, the 12 dev cases, the saved Hybrid read, the
never-tier count, the drawing SVG, the troubleshooting sheet, that repo files are not served, the security headers,
the WebSocket through Caddy (a foreign Origin refused, a missing or forged token refused, an Engineer session opened
and a reading taken), whether paid runs are open, and the page in Chromium with no console error. The spend ledger
itself is read on the server: `sudo docker compose exec app cat /app/runs/public_spend.json`.

## 7. Browser checklist (manual, after the smoke test)

On the public URL, at 1920x1080 and 1440x900:

- [ ] Only the ATS bench is shown (no Motor starter button); the drawing note under the header.
- [ ] Engineer, dev-07: the suggestion, an **approval** card (Isolate sources), the manual operation check after
      isolation, the diagnosis, then the intervention: the cut-off contact and the coil (pills "adjusted",
      "replaced", the relubrication recommendation), Restore sources with the **strong approval** (two clicks),
      "Transfer verified" at 6:17.
- [ ] Engineer, dev-07, before isolation: Manual operation check is **blocked** by the policy (red message, 1 blocked,
      no UPS time used).
- [ ] Hybrid, dev-07, saved read: the planner's steps, its approval cards ("Planner's reason"), the result card with
      the explanation labelled "Muse Spark" (about $0.01).
- [ ] Agent, dev-07: approvals during the run, the result card (about $0.12).
- [ ] **Compare** on one of these results (after the Agent run it is free).
- [ ] Live re-read is shown disabled with its reason.
- [ ] The **cap message**: set `PROBEFORGE_PUBLIC_TOTAL_USD=0.01` in the env file, `sudo docker compose up -d --wait`,
      start a Hybrid run: "The public demo's model budget is used up ...; Engineer mode still works", and an Engineer
      run still works. Remove the line again and run the same command.
- [ ] A third tab from the same address: "This address already has 2 open ProbeForge sessions ...".

## 8. Update and rollback

Update to the current `main` (or any commit):

```
cd ~/probeforge && git pull
cd deploy && nano .env                            # PROBEFORGE_TAG=<new short commit hash>
sudo docker compose up -d --build --wait
```

then the smoke test from your machine (it waits for the warm-up, up to about 10 minutes). Each tag stays as a local image, and the volume keeps the ledger and the
traces, so a redeploy never resets the caps.

Rollback: `git checkout <previous commit>` (if the compose or Caddy files changed), set `PROBEFORGE_TAG` back to the
previous hash in `deploy/.env`, `sudo docker compose up -d --wait` (no build: the old image is still there). Old images:
`sudo docker image ls probeforge`; remove the ones you will not roll back to with `sudo docker image rm probeforge:<tag>`.

## 9. Running it

- Logs: `sudo docker compose logs -f app` (rotated at 10 MB, five files per container).
- Restarts: both containers restart on their own (`unless-stopped`), also after a reboot.
- Spend: `sudo docker compose exec app cat /app/runs/public_spend.json`. The provider-side limit on the key is the
  real cap; the ledger is the per-server guard.
- Backup of the volume: `sudo docker run --rm -v probeforge_probeforge-runs:/runs -v "$PWD":/backup alpine tar czf
  /backup/runs-$(date +%F).tar.gz -C /runs .`
- Your website later: point its domain at the server, put the files in `deploy/site/`, uncomment the second block in
  `deploy/Caddyfile` with its domain, then `sudo docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`.
- Changing the key: edit the env file, `sudo docker compose up -d --wait` (the app container is recreated).
