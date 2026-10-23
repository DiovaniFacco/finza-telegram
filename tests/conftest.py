"""Configuração de testes: variáveis de ambiente mínimas para importar o app."""

from __future__ import annotations

import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/finza")
os.environ.setdefault("SECRET_KEY", "test-secret")
