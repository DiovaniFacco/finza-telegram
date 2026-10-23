"""Testes das regras determinísticas do parser (sem banco/IA)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.ai import _coerce
from app.services.parser import detect_operation_intent, rule_parse_operation


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("removi 500 dos investimentos", "investment"),
        ("remove o valor de 500 dos investimentos", "investment"),
        ("apaga o gasto de 45 no ifood", "expense"),
        ("tira o investimento de 500", "investment"),
        ("exclui o resgate de 200", "investment_out"),
    ],
)
def test_delete_intent(message: str, kind: str) -> None:
    op = rule_parse_operation(message)
    assert op is not None
    assert op.action == "delete"
    assert op.target_kind == kind


def test_delete_strips_operation_words_from_merchant() -> None:
    op = rule_parse_operation("remove o valor de 500 dos investimentos")
    assert op is not None
    assert op.amount == Decimal("500.00")
    assert op.merchant == ""


def test_delete_latest_only() -> None:
    op = rule_parse_operation("desfaz o último lançamento")
    assert op is not None
    assert op.action == "delete"
    assert op.latest_only is True


def test_delete_without_filters_asks_for_detail() -> None:
    op = rule_parse_operation("remove tudo")
    assert op is not None
    assert op.action == "delete"
    assert op.amount is None
    assert op.merchant == ""
    assert op.target_kind is None


@pytest.mark.parametrize(
    ("message", "source", "dest", "amount"),
    [
        ("resgata 300 do tesouro pra conta", "investimento", "conta", "300.00"),
        ("tira 200 dos investimentos e move pra conta", "investimento", "conta", "200.00"),
        ("resgatei 250", "investimento", "conta", "250.00"),
        ("movi 300 da conta pro dinheiro", "conta", "dinheiro", "300.00"),
        ("passei 50 da carteira pro banco", "dinheiro", "conta", "50.00"),
        ("transferir 100 da conta para o investimento", "conta", "investimento", "100.00"),
        ("tira o investimento de 500 e move pra conta", "investimento", "conta", "500.00"),
    ],
)
def test_transfer_intent(
    message: str, source: str, dest: str, amount: str
) -> None:
    op = rule_parse_operation(message)
    assert op is not None
    assert op.action == "transfer"
    assert op.wallet == source
    assert op.wallet_to == dest
    assert op.amount == Decimal(amount)


@pytest.mark.parametrize(
    "message",
    [
        "gastei 45 no ifood",
        "recebi 3200 de salário",
        "investi 500 no tesouro direto",
        "coloquei 500 no cdb",
        "paguei 100 de conta de luz",
        "recebi 80 de dividendos",
    ],
)
def test_normal_entries_are_not_operations(message: str) -> None:
    assert detect_operation_intent(message) is None
    assert rule_parse_operation(message) is None


def test_missing_amount_transfer_falls_through_to_ai() -> None:
    op = rule_parse_operation("resgata aquele investimento")
    assert op is not None
    assert op.action == "transfer"
    assert op.amount is None


def test_ai_coerce_operation_payload() -> None:
    result = _coerce(
        '{"action": "transfer", "amount": 120, "merchant": "Tesouro", '
        '"from_wallet": "investments", "to_wallet": "bank", "kind": "expense"}'
    )
    assert result is not None
    assert result.action == "transfer"
    assert result.from_wallet == "investimento"
    assert result.to_wallet == "conta"


def test_ai_coerce_delete_payload() -> None:
    result = _coerce(
        '{"action": "delete", "amount": 50, "target_kind": "investment", '
        '"merchant": "CDB"}'
    )
    assert result is not None
    assert result.action == "delete"
    assert result.target_kind == "investment"


def test_general_balances_accounts_for_transfers_and_redemptions(monkeypatch) -> None:
    import asyncio
    import uuid

    from app.db import repository as repo

    totals = {
        ("conta", "income"): Decimal("500"),
        ("conta", "expense"): Decimal("100"),
        ("conta", "transfer_out"): Decimal("200"),
        ("conta", "investment"): Decimal("300"),
        ("conta", "investment_out"): Decimal("100"),
        ("dinheiro", "transfer_in"): Decimal("200"),
    }

    async def fake_initials(session, user_id):
        return {"conta": Decimal("1000"), "dinheiro": Decimal("0")}

    async def fake_total(session, user_id, wallet, kind):
        return totals.get((wallet, kind), Decimal("0"))

    monkeypatch.setattr(repo, "get_initial_balances", fake_initials)
    monkeypatch.setattr(repo, "wallet_kind_total", fake_total)

    balances = asyncio.run(repo.general_balances(None, uuid.uuid4()))

    assert balances["conta"] == Decimal("1300")
    assert balances["dinheiro"] == Decimal("200")
    assert balances["investido"] == Decimal("200")


def test_removing_an_investment_does_not_create_a_new_one() -> None:
    """Regressão: 'removi 500 dos investimentos' virava um novo aporte."""
    import asyncio

    from app.services.parser import parse_message

    class DummySession:
        """ensure_fresh falha silenciosamente sem banco; as regras seguem valendo."""

    op = asyncio.run(parse_message("removi 500 dos investimentos", DummySession()))

    assert op is not None
    assert op.action == "delete"
    assert op.target_kind == "investment"
    assert op.amount == Decimal("500.00")


def test_redeeming_investment_is_a_transfer() -> None:
    import asyncio

    from app.services.parser import parse_message

    class DummySession:
        pass

    op = asyncio.run(parse_message("resgata 300 do tesouro pra conta", DummySession()))

    assert op is not None
    assert op.action == "transfer"
    assert op.wallet == "investimento"
    assert op.wallet_to == "conta"
    assert op.amount == Decimal("300.00")


def test_regular_entries_keep_working() -> None:
    import asyncio

    from app.services.parser import parse_message

    class DummySession:
        pass

    op = asyncio.run(parse_message("investi 500 no tesouro", DummySession()))

    assert op is not None
    assert op.action == "create"
    assert op.kind == "investment"
    assert op.amount == Decimal("500.00")


