# Contributing to Finza

Thanks for taking the time to contribute! This guide covers how to set up the project, the
conventions we follow, and how to get a change merged.

## Ways to contribute

- 🐛 **Report a bug** — open an issue with steps to reproduce, expected vs. actual behaviour, and logs.
- 💡 **Suggest a feature** — open an issue describing the problem it solves.
- 📝 **Improve docs** — README, SETUP, DEPLOYMENT and docstrings are all fair game.
- 🔧 **Send code** — bug fixes, new parsers, categories, dashboard widgets, tests.

## Development setup

```bash
git clone https://github.com/DiovaniFacco/finza-telegram.git
cd finza-telegram

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
pip install ruff

cp .env.example .env        # then fill in your values
alembic upgrade head
uvicorn app.main:app --reload
```

You need a PostgreSQL database and a Telegram bot token from [@BotFather](https://t.me/BotFather).
The AI providers (Groq / OpenRouter) are optional — parsing degrades gracefully without them.
See [SETUP.md](SETUP.md) for the full walkthrough.

## Before you open a PR

Run the same checks CI runs:

```bash
ruff check .                 # lint
python -m compileall -q app  # syntax check
```

Keep the lint green — PRs with a red `CI` check won't be reviewed until it's fixed.

## Workflow

1. **Fork** the repository (or create a branch if you have write access).
2. Create a **descriptive branch**: `feat/pdf-weekly-report`, `fix/voice-timeout`, `docs/setup-typo`.
3. Make your change in **small, focused commits**.
4. Write a clear **PR description**: what changed, why, and how you tested it. Link the issue it closes.
5. Make sure `CI` passes. A maintainer will review.

### Commit messages

We loosely follow [Conventional Commits](https://www.conventionalcommits.org/): a `type(scope): summary`
subject line in the imperative mood, e.g.

```
feat(parser): handle amounts written as "1.000,50"
fix(dashboard): keep chart tooltips in BRL
docs(readme): document GROQ_API_KEY
```

## Code conventions

- **Python 3.12+**, fully type-hinted where practical; `from __future__ import annotations` at the top of modules.
- **Async all the way**: database access goes through `AsyncSession` (SQLAlchemy 2 async).
- **Line length: 100.** Formatting is not enforced by a formatter, so keep lines reasonable.
- **Money** is a `Decimal` in the database and formatted with `app.utils.money.format_brl` for display — never hardcode a currency symbol.
- **Categories** are PT-BR (`Alimentação`, `Transporte`, `Investimento`, …). New merchant rules go in
  `app/services/categorizer.py` (`HARDCODED_RULES`) **and** as a new Alembic migration seeding `category_rules`.
- **Logging**: use the structured logger (`from app.utils.logging import get_logger`), never `print`.
- **Secrets**: environment variables only (`app/config.py` / `.env`). Never commit credentials or a `.env` file.
- **Security**: every dashboard query must be scoped to the authenticated `user_id`.

## Adding a migration

```bash
alembic revision --autogenerate -m "short description"
alembic upgrade head
```

Commit the generated file in `app/migrations/versions/`. Migrations run automatically on deploy.

## Reporting security issues

Please **do not** open a public issue for security problems. Contact the maintainer directly
(see the repository profile) so it can be fixed before disclosure.

## Code of conduct

Be kind, be constructive, assume good faith. Harassment or disrespectful behaviour is not welcome here.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
