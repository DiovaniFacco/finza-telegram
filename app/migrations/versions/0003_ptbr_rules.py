"""Regras de categoria em PT-BR.

Revision ID: 0003_ptbr_rules
Revises: 0002_uuid_defaults
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_ptbr_rules"
down_revision: str = "0002_uuid_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PT_RULES: list[tuple[str, str]] = [
    ("99", "Transporte"),
    ("acougue", "Alimentação"),
    ("agua", "Contas"),
    ("almoco", "Alimentação"),
    ("almoço", "Alimentação"),
    ("aluguel", "Moradia"),
    ("amazon", "Compras"),
    ("açougue", "Alimentação"),
    ("bar", "Lazer"),
    ("bico", "Freelance"),
    ("cafe", "Alimentação"),
    ("café", "Alimentação"),
    ("celular", "Contas"),
    ("cerveja", "Lazer"),
    ("cinema", "Lazer"),
    ("claro", "Contas"),
    ("coffee", "Alimentação"),
    ("combustivel", "Transporte"),
    ("combustível", "Transporte"),
    ("condominio", "Moradia"),
    ("condomínio", "Moradia"),
    ("curso", "Educação"),
    ("dentista", "Saúde"),
    ("dinner", "Alimentação"),
    ("dividendo", "Investimento"),
    ("doctor", "Saúde"),
    ("electricity", "Contas"),
    ("energia", "Contas"),
    ("escola", "Educação"),
    ("estacionamento", "Transporte"),
    ("exame", "Saúde"),
    ("faculdade", "Educação"),
    ("farmacia", "Saúde"),
    ("farmácia", "Saúde"),
    ("feira", "Alimentação"),
    ("financiamento", "Moradia"),
    ("freela", "Freelance"),
    ("freelance", "Freelance"),
    ("gasolina", "Transporte"),
    ("ifood", "Alimentação"),
    ("internet", "Contas"),
    ("investimento", "Investimento"),
    ("iptu", "Moradia"),
    ("jantar", "Alimentação"),
    ("jogo", "Lazer"),
    ("lanche", "Alimentação"),
    ("livro", "Educação"),
    ("lunch", "Alimentação"),
    ("luz", "Contas"),
    ("medico", "Saúde"),
    ("mensalidade", "Educação"),
    ("mercado", "Alimentação"),
    ("mercado livre", "Compras"),
    ("mercadolivre", "Compras"),
    ("metro", "Transporte"),
    ("metrô", "Transporte"),
    ("médico", "Saúde"),
    ("netflix", "Lazer"),
    ("oi ", "Contas"),
    ("onibus", "Transporte"),
    ("padaria", "Alimentação"),
    ("pagamento", "Salário"),
    ("pedagio", "Transporte"),
    ("pedágio", "Transporte"),
    ("pharmacy", "Saúde"),
    ("pizza", "Alimentação"),
    ("plano de saude", "Saúde"),
    ("prime", "Lazer"),
    ("rappi", "Alimentação"),
    ("remedio", "Saúde"),
    ("remédio", "Saúde"),
    ("rendimento", "Investimento"),
    ("rent", "Moradia"),
    ("restaurante", "Alimentação"),
    ("roupa", "Compras"),
    ("salario", "Salário"),
    ("salário", "Salário"),
    ("shein", "Compras"),
    ("shopee", "Compras"),
    ("shopping", "Compras"),
    ("show", "Lazer"),
    ("spotify", "Lazer"),
    ("supermercado", "Alimentação"),
    ("taxi", "Transporte"),
    ("telefone", "Contas"),
    ("tim", "Contas"),
    ("uber", "Transporte"),
    ("vivo", "Contas"),
    ("água", "Contas"),
    ("ônibus", "Transporte"),
]


def upgrade() -> None:
    op.execute("DELETE FROM category_rules")
    for keyword, category in PT_RULES:
        op.execute("INSERT INTO category_rules (keyword, category) VALUES ('%s', '%s')" % (keyword.replace(chr(39), chr(39)*2), category.replace(chr(39), chr(39)*2)))


def downgrade() -> None:
    op.execute("DELETE FROM category_rules")
