# Setup & Run Guide

Step-by-step instructions to run Finza end-to-end, locally and on Railway.

---

## 1. Prerequisites

Install once on your machine:

| Tool       | Version  | Notes                                                              |
| ---------- | -------- | ------------------------------------------------------------------ |
| Python     | `>=3.12` | `python3 --version`                                                |
| pip        | latest   | comes with Python                                                  |
| PostgreSQL | `>=14`   | Local install, Docker, or a [Supabase](https://supabase.com) project |
| ngrok      | any      | Only needed for local Telegram webhook testing                     |
| git        | any      | for cloning / deploying                                            |

You will also need:

- A Telegram bot token from [@BotFather](https://t.me/BotFather).
- (Optional) An [OpenRouter](https://openrouter.ai/) API key for the AI fallback.

---

## 2. Get a Telegram bot token

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, follow the prompts (name + username).
3. Copy the token it returns — looks like `7891234567:AAH...`. Keep it safe; this is your `TELEGRAM_BOT_TOKEN`.

---

## 3. Provision a database

### Option A — Local Postgres

```bash
createdb expenses
```

Connection string:

```
postgresql://<your-os-user>@localhost:5432/expenses
```

### Option B — Docker

```bash
docker run --name expense-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=expenses \
  -p 5432:5432 -d postgres:16
```

Connection string:

```
postgresql://postgres:postgres@localhost:5432/expenses
```

### Option C — Supabase (recommended for prod, easy free tier)

1. Create a new project at [supabase.com](https://supabase.com).
2. Go to **Project Settings → Database → Connection string → URI**.
3. Use the **Transaction pooler** URL — append `?sslmode=require` if your driver complains.

---

## 4. Clone & install

```bash
git clone <your-repo-url> personal_expense_logger_bot
cd personal_expense_logger_bot

python3 -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -e .
```

This installs FastAPI, python-telegram-bot, SQLAlchemy, ReportLab, matplotlib, APScheduler, and friends — all listed in `pyproject.toml`.

---

## 5. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
TELEGRAM_BOT_TOKEN=7891234567:AAH...
OPENROUTER_API_KEY=sk-or-v1-...        # optional; leave blank to disable AI fallback
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/expenses
APP_URL=https://<your-ngrok-or-railway-url>
SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')
WEBHOOK_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(24))')
APP_TZ=America/Sao_Paulo
LOG_LEVEL=INFO
```

> Tip: run those `python -c` snippets in a terminal first and paste the output into `.env`.

| Variable             | Required | Purpose                                                |
| -------------------- | :------: | ------------------------------------------------------ |
| `TELEGRAM_BOT_TOKEN` |    yes   | Auth with Telegram                                     |
| `OPENROUTER_API_KEY` |    no    | Enables AI fallback when regex/rules fail              |
| `DATABASE_URL`       |    yes   | Postgres URL (sync form; the app converts to asyncpg)  |
| `APP_URL`            |    yes   | Public base URL for webhook + magic links              |
| `SECRET_KEY`         |    yes   | Signs JWT magic tokens and session cookies             |
| `WEBHOOK_SECRET`     |    yes   | Path segment for `/webhook/<secret>`                   |
| `APP_TZ`             |    yes   | Timezone for "today" and the 9 PM scheduler            |
| `LOG_LEVEL`          |    no    | `DEBUG` / `INFO` / `WARNING`                           |

---

## 6. Apply database migrations

```bash
alembic upgrade head
```

This creates `users`, `expenses`, `category_rules`, `daily_reports` and seeds default category rules (Uber → Transporte, iFood → Alimentação, etc.).

To inspect:

```bash
alembic current        # current revision
alembic history        # all revisions
alembic downgrade -1   # roll back one (if needed)
```

---

## 7. Run the app locally

### Terminal 1 — start the server

```bash
uvicorn app.main:app --reload --port 8000
```

You should see:

```
INFO  webhook_set url=https://.../webhook/...
INFO  scheduler_started tz=America/Sao_Paulo
```

### Terminal 2 — expose to Telegram with ngrok

```bash
ngrok http 8000
```

Copy the `https://<random>.ngrok-free.app` URL it prints, paste it into `.env` as `APP_URL`, then **restart uvicorn** so it re-registers the webhook.

### Test it

1. Open your bot in Telegram.
2. Send `/start`.
3. Send `Uber 340` — you should get back `Logged R$ 340,00 · Uber · Transporte`.
4. Send `/today` to see today's totals.
5. Send `/dashboard` and click the link — the dashboard opens, signed in.

---

## 8. Health check

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

---

## 9. Deploy to Railway

1. Push this repo to GitHub.
2. On [Railway](https://railway.app), **New Project → Deploy from GitHub**.
3. Add environment variables in **Variables** (same names as `.env.example`). For `DATABASE_URL`, use the Supabase pooler URL.
4. Set the **Start command** to:
   ```
   alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
   (or rely on `railway.json`'s default `uvicorn ...` and run migrations manually once.)
5. Once deployed, set `APP_URL` to your Railway public URL (e.g. `https://expense-bot.up.railway.app`).
6. Trigger a redeploy. The app re-registers the webhook on startup.

Health check: Railway probes `/healthz` automatically.

---

## 10. Verify the daily 9 PM job

The scheduler runs at `21:00 APP_TZ`. To verify locally without waiting:

```bash
python - <<'PY'
import asyncio
from app.bot.application import build_application
from app.scheduler.daily import send_daily_reports

async def main():
    app = build_application()
    await app.initialize()
    await app.start()
    await send_daily_reports(app)
    await app.stop()
    await app.shutdown()

asyncio.run(main())
PY
```

Every user with an expense today will receive the summary text and the PDF.

---

## 11. Common issues

| Symptom                                              | Fix                                                                                              |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `ValidationError: TELEGRAM_BOT_TOKEN`                | `.env` not loaded — run from project root, ensure `.env` exists.                                 |
| `webhook_set_failed`                                 | `APP_URL` must be HTTPS and reachable; for local dev use ngrok.                                  |
| Telegram says "Bad Request: bad webhook"             | `APP_URL` is not publicly reachable yet. Restart after ngrok is up.                              |
| `psycopg`/`asyncpg` SSL errors on Supabase           | Append `?sslmode=require` to `DATABASE_URL`.                                                     |
| Dashboard redirects to `/login` immediately          | Cookie didn't set — your magic link was opened on a different domain. Use the same `APP_URL`.    |
| AI fallback never runs                               | That is expected for parseable inputs. It triggers only when both amount and merchant are missing.|
| `ImportError: cannot import name 'X' from 'app...'`  | Restart uvicorn; `--reload` sometimes misses moves.                                              |

---

## 12. Project commands cheat sheet

```bash
# Install deps
pip install -e .

# Migrations
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "your message"

# Run server (dev)
uvicorn app.main:app --reload

# Run server (prod-like)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Tunnel for local Telegram webhook
ngrok http 8000

# Trigger daily report ad hoc (see step 10)
```

---

That's it. Send your bot `Uber 340` and watch it land on the dashboard.
