# Deploying PlayClass on AWS EC2

This guide sets up **one EC2 instance** running PlayClass: FastAPI served by uvicorn behind nginx, with PostgreSQL on the
same box or on RDS. It is meant for **pilots**, such as a few schools at a time. It is not the scaled architecture in README §15.
To get there, the app must be ported into the monorepo (see `docs/MONOREPO-PORTING.md`).

> **Security first.** Set a random `REPORTS_KEY` (step 5). The app has no default code: without it, `/reports` stays
> locked ("reports not configured", HTTP 503) and a warning is logged at startup. Do **not** start the service with
> `scripts/run.sh`; its `reports123` fallback is for a developer laptop only. Never commit the `.env` file.

---

## 0. What you need

| Item | Recommendation |
|---|---|
| Instance | Ubuntu Server 24.04 LTS, `t3.small` (2 vCPU / 2 GB) for a pilot of about 5 classes at once. `t3.medium` if Postgres runs on the same box and more than 10 classes play at once |
| Disk | 20 GB gp3 |
| Region | `ap-southeast-1` (Singapore), closest to Malaysia and Indonesia |
| Domain | e.g. `playclass.solveeducation.org`, with an A record pointing to an Elastic IP. **HTTPS is strongly recommended** |
| Database | Local PostgreSQL 16 (simplest), or **RDS for PostgreSQL 16** (backups and failover handled for you) |

**Security group (inbound)**

| Port | Source | Why |
|---|---|---|
| 22 | your office IP only (or use SSM Session Manager and keep 22 closed) | admin |
| 80 | 0.0.0.0/0 | HTTP to HTTPS redirect and certbot |
| 443 | 0.0.0.0/0 | the app |

Do **not** open 5432 or 8000 to the internet.

---

## 1. Install system packages

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install python3 python3-venv python3-pip git nginx postgresql-16 postgresql-client-16 unzip
python3 --version   # 3.12 on Ubuntu 24.04 is fine (developed and tested on 3.11)
```

If you use RDS, skip `postgresql-16` and install only `postgresql-client-16`.

## 2. Create the app user and fetch the code

```bash
sudo adduser --system --group --home /opt/playclass playclass
sudo -u playclass -H bash -lc '
  cd /opt/playclass &&
  git clone --depth 1 --branch game-console --filter=blob:none --sparse \
      https://gitlab.solveeducation.org/solveearn/solveeducation.git repo &&
  cd repo && git sparse-checkout set apps/game-console'
```

The app is now at `/opt/playclass/repo/apps/game-console`. The steps below call this `APP`.
You need GitLab access: use a deploy token or deploy key with **read-only** rights, and never your personal password.

## 3. Python environment

```bash
APP=/opt/playclass/repo/apps/game-console
sudo -u playclass -H bash -lc "cd $APP && python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt"
```

## 4. Database

### Option A: PostgreSQL on the same instance

```bash
DBPASS="$(openssl rand -base64 24 | tr -d '/+=')"
echo "Save this password in SSM Parameter Store: $DBPASS"
sudo -u postgres psql -c "CREATE ROLE playclass LOGIN PASSWORD '$DBPASS';"
sudo -u postgres psql -c "CREATE DATABASE playclass OWNER playclass;"
sudo -u postgres psql -d playclass -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

### Option B: RDS

Create an RDS PostgreSQL 16 instance in the same VPC. Its security group should allow 5432 **only from the EC2 security group**.
Create the database `playclass` and run `CREATE EXTENSION IF NOT EXISTS pgcrypto;` once as the master user.

### Apply the schema and seed content

Every file in `db/` is **idempotent and non-destructive**, so applying them all again later (for example after `git pull`) is safe.

```bash
export DATABASE_URL="postgresql://playclass:$DBPASS@localhost:5432/playclass"   # or your RDS endpoint (?sslmode=require)
cd $APP
for f in $(ls db/*.sql | LC_ALL=C sort); do
  echo "== $f"; psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$f" || break
done
```

The seed files (`002`, `004`, `008`) load the ready-made quizzes: AI Basics, Using AI Safely & Smartly, Everyday English and
AI for Teachers. `002_seed.sql` also creates 5 demo users for the retired `/practice` page, and `002` / `004` contain
speaking questions from before the quiz-only decision. Nothing reads the users any more and speaking questions are never
picked, so both are harmless. The migrations stay as they are (they are history).

> `scripts/dev_db.sh` is for local development only (it creates a throw-away cluster in `./.pgdata`). Don't use it on EC2.

## 5. Configuration (`/etc/playclass.env`)

```bash
sudo tee /etc/playclass.env >/dev/null <<EOF
DATABASE_URL=postgresql://playclass:CHANGE_ME@localhost:5432/playclass
REPORTS_KEY=$(openssl rand -hex 16)
LIVE_PUBLIC_URL=https://playclass.solveeducation.org
# A whole class often shares ONE public IP (school NAT). Raise the per-IP join limit so 40 students can join at once:
LIVE_JOIN_LIMIT=80
LIVE_JOIN_WINDOW_SEC=10
LIVE_LOOKUP_LIMIT=200
EOF
sudo chown root:playclass /etc/playclass.env && sudo chmod 640 /etc/playclass.env
sudo grep REPORTS_KEY /etc/playclass.env   # give this code to the program team (for /reports)
```

For production, keep the secrets (`DATABASE_URL` password, `REPORTS_KEY`) in **SSM Parameter Store** as SecureString, and
render the file from there at boot, for example with an ExecStartPre that calls `aws ssm get-parameter --with-decryption`.
The instance role then needs `ssm:GetParameter` on those parameter names only.

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Postgres connection string (add `?sslmode=require` for RDS) |
| `REPORTS_KEY` | **required**: access code for `/reports` (program team). Unset → `/api/reports/*` answers 503 "reports not configured" |
| `LIVE_PUBLIC_URL` | public base URL used in join links shown to teachers |
| `LIVE_JOIN_LIMIT` / `LIVE_JOIN_WINDOW_SEC` | join rate limit per client IP (default 10 per 10 s is too low for a class behind NAT) |
| `LIVE_LOOKUP_LIMIT` | PIN lookup rate limit per IP |
| `QUIZ_CREATE_LIMIT` | teacher quiz creations per IP per hour (default 20) |
| `REPORTS_FAIL_LIMIT` | wrong `/reports` codes per IP before a lockout (default 10 per 300 s) |

## 6. systemd service

```bash
sudo tee /etc/systemd/system/playclass.service >/dev/null <<'EOF'
[Unit]
Description=PlayClass (FastAPI)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
User=playclass
Group=playclass
WorkingDirectory=/opt/playclass/repo/apps/game-console
EnvironmentFile=/etc/playclass.env
# ONE worker: the rate limiters are in-memory per process. SSE fan-out uses Postgres LISTEN/NOTIFY and already
# works across processes, but raising --workers would multiply every rate limit.
# --proxy-headers + forwarded-allow-ips makes per-IP limits see the real client IP from nginx.
ExecStart=/opt/playclass/repo/apps/game-console/.venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 \
  --timeout-keep-alive 75
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now playclass
curl -s localhost:8000/api/health    # {"ok":true,"db":true,...}
```

## 7. nginx (with Server-Sent Events)

The live leaderboard uses **SSE** (`/api/live/games/{pin}/events`). nginx must **not buffer** it, and must keep it open.

```bash
sudo tee /etc/nginx/sites-available/playclass >/dev/null <<'EOF'
server {
  listen 80;
  server_name playclass.solveeducation.org;
  client_max_body_size 1m;               # quiz answers are tiny JSON; there are no uploads

  location ~ ^/api/(live|class)/.*/events$ {   # SSE streams
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 1h;
    add_header X-Accel-Buffering no;
  }

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
  }
}
EOF
sudo ln -sf /etc/nginx/sites-available/playclass /etc/nginx/sites-enabled/playclass
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### HTTPS (Let's Encrypt)

```bash
sudo apt -y install certbot python3-certbot-nginx
sudo certbot --nginx -d playclass.solveeducation.org --redirect -m you@solveeducation.org --agree-tos -n
```

certbot renews automatically through its systemd timer.

## 8. Smoke test

1. Open `https://<domain>/`. You should see the **I'm a Teacher / I'm a Student** gate.
2. On a laptop, go to Teacher, pick "AI Basics", then **Create game**. A 6-digit PIN appears.
3. On a phone, go to Student, enter the PIN and a nickname. The name should appear in the lobby within a second, which proves SSE works through nginx.
4. Play one question. Instant results and the leaderboard should update.
5. Open `https://<domain>/reports` and enter the `REPORTS_KEY`. The game should be listed under its school. If the page
   says "Reports are not set up on this server yet", `REPORTS_KEY` is missing from `/etc/playclass.env`.

## 9. Operations

**Logs**
```bash
journalctl -u playclass -f
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

**Update to the latest `game-console` branch**
```bash
sudo -u playclass -H bash -lc 'cd /opt/playclass/repo && git pull --ff-only'
cd /opt/playclass/repo/apps/game-console
sudo -u playclass .venv/bin/pip install -r requirements.txt
set -a; . /etc/playclass.env; set +a
for f in $(ls db/*.sql | LC_ALL=C sort); do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$f" || break; done
sudo systemctl restart playclass
```

A restart ends open SSE connections. Clients reconnect automatically, and players and hosts resume from their saved tokens. Even so, avoid deploying during school hours.

**Backups** (local Postgres; RDS has automated snapshots)
```bash
sudo install -d -o postgres /var/backups/playclass
echo '15 2 * * * postgres pg_dump -Fc playclass > /var/backups/playclass/playclass-$(date +\%F).dump && find /var/backups/playclass -mtime +14 -delete' \
  | sudo tee /etc/cron.d/playclass-backup
```
Copy the dumps off the box, for example with a nightly `aws s3 cp` to a bucket that has versioning and SSE-KMS.

**Monitoring:** use the CloudWatch agent (CPU, memory, disk) plus a Route 53 health check or an uptime check on `/api/health`.

## 10. Known limits of this single-box setup

- Rate limits are **in memory**, so there is one worker. Horizontal scaling needs Redis (README §15), which comes with the monorepo port.
- Teachers and students have no accounts. Teacher quizzes are protected by per-quiz edit keys stored in the browser, and `/reports` by one shared code.
- The data includes students' nicknames and names typed by teachers (minors). Keep the instance private to the programme, use
  HTTPS, restrict SSH, and delete old games according to the programme's data-retention policy.
- This code is **not** merge-ready for the monorepo `main`: it is Python and vanilla JS, and the premerge gates will fail. The
  `game-console` branch is a prototype and staging branch. See `docs/MONOREPO-PORTING.md` for the porting plan.
