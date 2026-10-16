# Railway deployment checklist

## 1. Confirm you deployed THIS project

The screenshot UI (**"Expense Tracker"** with Description / Amount / Select Category form) is **not** from this codebase.

This app shows:
- Title: **Finza** (dark/light theme)
- Sign-in via Telegram **`/dashboard`** magic link
- Pages: Overview, Charts, Expenses, Reports

**Verify after deploy:**

```bash
curl https://YOUR-SERVICE.up.railway.app/healthz
```

Expected:

```json
{
  "status": "ok",
  "app": "finza",
  "version": "0.1.0",
  "webhook_path": "/webhook/your-secret"
}
```

If you see a different UI or `healthz` does not return `"app": "finza"`, Railway is running **another repository or service**. Fix that in Railway before debugging Telegram.

---

## 2. Railway environment variables

Set these in **Variables** (not only in local `.env`):

| Variable | Example |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `DATABASE_URL` | Supabase pooler URI (`postgresql://...`) |
| `SECRET_KEY` | long random string |
| `WEBHOOK_SECRET` | random string (must match webhook path) |
| `APP_TZ` | `America/Sao_Paulo` |
| `OPENROUTER_API_KEY` | optional |

**`APP_URL` on Railway:** You can omit it or set it to your Railway URL. When `RAILWAY_ENVIRONMENT` is set, the app **auto-uses** `https://$RAILWAY_PUBLIC_DOMAIN` so the Telegram webhook is not left pointing at `localhost` or ngrok.

---

## 3. Telegram webhook debug

After deploy:

```bash
curl https://YOUR-SERVICE.up.railway.app/api/webhook-info
```

Check:
- `telegram_url` should equal `expected_url`
- `last_error_message` should be empty

If `telegram_url` is empty or points to ngrok/localhost, redeploy (startup re-registers the webhook) or fix `APP_URL` / Railway domain.

Webhook endpoint Telegram calls:

```
POST https://YOUR-SERVICE.up.railway.app/webhook/<WEBHOOK_SECRET>
```

---

## 4. Redeploy steps

1. Push latest code to the repository.
2. Railway → correct service → **Settings** → confirm GitHub repo root is this project.
3. **Redeploy**.
4. Open **Deploy Logs** → look for `webhook_registered` and `migrations_applied`.
5. Message your bot: `/start` then `Uber 340`.

---

## 5. Dashboard or bot issues

Check database connectivity:

```bash
curl https://YOUR-SERVICE.up.railway.app/api/db-check
```

Expected: `{"status":"ok","database":"connected"}`

Railway logs (search these keys only — not shown to users):

- `overview_load_failed` — dashboard data query failed (shows empty overview)
- `auth_failed` — magic link sign-in failed
- `bot_error` — Telegram handler failed
- `database_connection_failed` — startup DB check failed

---

## 6. Local vs Railway dashboard

| | Local | Railway |
|---|--------|---------|
| URL | `http://localhost:8000` | `https://….up.railway.app` |
| Sign-in | `/dashboard` in Telegram → open link | Same; link uses Railway `APP_URL` |
| Bot webhook | ngrok HTTPS required | Auto on Railway |

Locally you only see the full dashboard after `/dashboard` + magic link. Visiting `/` alone shows the login page — not the manual "Expense Tracker" form.
