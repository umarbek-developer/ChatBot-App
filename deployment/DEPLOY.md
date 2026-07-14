# ChatBot-App — Server Deployment

Real-time messaging platform: Django + DRF + **Channels/WebSocket** (Daphne) +
**Celery** (Redis broker). Because of WebSocket, it is served by an **ASGI**
server (Daphne), **not** plain WSGI/gunicorn.

## Required services
| Service | Role |
|---|---|
| PostgreSQL | Primary DB (`DB_TYPE=psql`) |
| Redis | Celery broker/result (db 0), Channels layer (db 1), realtime presence (db 2) |
| Daphne | ASGI app server (HTTP + WebSocket) — systemd `daphne.service` |
| Celery worker | Background tasks (OTP email, invite cleanup) — systemd `celery.service` |
| Nginx | Reverse proxy + TLS + static/media |

## 1. System packages
```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
    postgresql redis-server nginx libpq-dev
```

## 2. Code + virtualenv
Assume project at `/srv/ChatBot-App` (repo root, containing `src/` and `deployment/`).
```bash
cd /srv/ChatBot-App
python3 -m venv venv
./venv/bin/pip install -U pip
./venv/bin/pip install -r src/requirements/production.txt
```

## 3. PostgreSQL
```bash
sudo -u postgres psql -c "CREATE DATABASE chatbot;"
sudo -u postgres psql -c "CREATE USER chatbot WITH PASSWORD 'strong-password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE chatbot TO chatbot;"
```

## 4. Environment file
```bash
cp src/.env.example src/.env
```
Edit `src/.env` for production (see `# PROD:` notes in the file). Minimum:
```
DEBUG=0
SECRET_KEY=<random 64+ chars>
ALLOWED_HOSTS=yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com
DB_TYPE=psql
DB_NAME=chatbot
DB_USER=chatbot
DB_PASSWORD=strong-password
DB_HOST=localhost
DB_PORT=5432
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=          # set if Redis has requirepass
EMAIL_HOST=you@gmail.com
EMAIL_PASSWORD=<gmail app password>
```

## 5. Migrate + static
```bash
cd /srv/ChatBot-App/src
../venv/bin/python manage.py migrate
../venv/bin/python manage.py collectstatic --noinput   # -> src/static
../venv/bin/python manage.py createsuperuser
```

## 6. systemd services
```bash
sudo cp deployment/daphne.service /etc/systemd/system/
sudo cp deployment/celery.service /etc/systemd/system/
# Edit WorkingDirectory / ExecStart paths + User if not /srv/ChatBot-App or www-data.
sudo chown -R www-data:www-data /srv/ChatBot-App
sudo systemctl daemon-reload
sudo systemctl enable --now redis-server daphne celery
sudo systemctl status daphne celery
```

## 7. Nginx
```bash
sudo cp deployment/nginx.conf /etc/nginx/sites-available/chatbot
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
# Edit server_name + static/media paths.
sudo nginx -t && sudo systemctl reload nginx
# TLS:
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```
Once HTTPS works, set `SECURE_SSL=1` in `src/.env` and restart daphne to enable
the SSL redirect, secure cookies and HSTS:
```bash
sudo systemctl restart daphne
```

## Notes / gotchas
- **Daphne serves HTTP too** — you do NOT also need gunicorn. `gunicorn`+`uvicorn`
  are in `production.txt` only as an optional alternative.
- WebSocket needs the nginx `Upgrade`/`Connection` headers in the `/ws/` block —
  already set in `nginx.conf`.
- `AllowedHostsOriginValidator` in `config/asgi.py` rejects WS from origins not in
  `ALLOWED_HOSTS` — keep your domain there.
- Redis dbs are separated (0 Celery / 1 Channels / 2 realtime); a single Redis
  instance is enough. Set `REDIS_PASSWORD` if `requirepass` is enabled.
- No Celery **beat** is configured (no periodic schedule) — only a worker is run.
