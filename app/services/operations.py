"""Executa operações interpretadas pelo parser (criar, remover, transferir)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.models import Expense, User
from app.services.parser import ParsedOperation
from app.utils.logging import get_logger

logger = get_logger(__name__)

WALLET_LABELS = {
    "conta": "Conta",
    "dinheiro": "Dinheiro",
    "investimento": "Investimentos",
}
WALLETS = frozenset(WALLET_LABELS)
KIND_LABELS = {
    "expense": "Gasto",
    "income": "Entrada",
    "investment": "Investimento",
    "investment_out": "Resgate",
    "transfer_in": "Transferência",
    "transfer_out": "Transferência",
}


@dataclass(slots=True)
class OperationResult:
    status: str
    operation: ParsedOperation
    entries: list[Expense] = field(default_factory=list)
    balances: dict[str, Decimal] | None = None

    @property
    def entry(self) -> Expense | None:
        return self.entries[0] if self.entries else None


def _wallet_label(wallet: str) -> str:
    return WALLET_LABELS.get(wallet, wallet.title())


def _merchant(op: ParsedOperation, default: str) -> str:
    return op.merchant.title() if op.merchant else default


async def execute(
    session: AsyncSession, user: User, op: ParsedOperation
) -> OperationResult:
    """Aplica a operação e devolve dados suficientes para a resposta do bot."""
    if op.action == "delete":
        return await _delete(session, user, op)
    if op.action == "transfer":
        return await _transfer(session, user, op)
    return await _create(session, user, op)


async def undo_last(session: AsyncSession, user: User) -> OperationResult:
    """Desfaz o lançamento mais recente (inclui transferências em par)."""
    op = ParsedOperation(action="delete", latest_only=True, source="manual")
    return await _delete(session, user, op)


async def _create(session: AsyncSession, user: User, op: ParsedOperation) -> OperationResult:
    amount = op.amount or Decimal("0")
    entry = await repo.create_expense(
        session,
        user_id=user.id,
        merchant=op.merchant or "Lançamento",
        amount=amount,
        category=op.category or "Outros",
        notes=op.notes or None,
        expense_date=op.expense_date,
        kind=op.kind,
        wallet=op.wallet if op.wallet in repo.WALLETS else "conta",
    )
    return OperationResult("created", op, entries=[entry])


async def _delete(session: AsyncSession, user: User, op: ParsedOperation) -> OperationResult:
    has_filter = any(
        value is not None
        for value in (op.amount, op.target_kind, op.merchant or None)
    ) or op.date_explicit

    if not op.latest_only and not has_filter:
        return OperationResult("needs_detail", op)

    rows = await repo.find_expenses_for_management(
        session,
        user.id,
        kind=op.target_kind,
        amount=op.amount,
        merchant=op.merchant or None,
        expense_date=op.expense_date if op.date_explicit else None,
        limit=10 if op.latest_only else 5,
    )
    if not rows:
        return OperationResult("not_found", op)

    target = rows[0]
    if target.transfer_id is not None:
        deleted = await repo.delete_transfer(
            session, user_id=user.id, transfer_id=target.transfer_id
        )
    else:
        deleted = await repo.delete_expenses_by_ids(
            session, user_id=user.id, ids=[target.id]
        )

    balances = await repo.general_balances(session, user.id)
    return OperationResult("deleted", op, entries=deleted, balances=balances)


async def _transfer(session: AsyncSession, user: User, op: ParsedOperation) -> OperationResult:
    source = op.wallet
    dest = op.wallet_to
    amount = op.amount

    if not amount or amount <= 0 or not source or not dest:
        return OperationResult("needs_detail", op)
    if source not in WALLETS or dest not in WALLETS or source == dest:
        return OperationResult("invalid", op)

    if source == "investimento":
        # Resgate: reduz o investido e credita a carteira de destino.
        entry = await repo.create_expense(
            session,
            user_id=user.id,
            merchant=_merchant(op, "Resgate de investimento"),
            amount=amount,
            category="Investimento",
            notes=op.notes or "Resgate de investimento",
            expense_date=op.expense_date,
            kind="investment_out",
            wallet=dest,
        )
        balances = await repo.general_balances(session, user.id)
        return OperationResult("redeemed", op, entries=[entry], balances=balances)

    transfer_id = uuid.uuid4()

    if dest == "investimento":
        # Aporte vindo de uma carteira: registra o investimento e debita a origem.
        entries = await repo.create_expenses(
            session,
            user_id=user.id,
            entries=[
                {
                    "merchant": _merchant(op, "Aporte"),
                    "amount": amount,
                    "category": "Investimento",
                    "notes": op.notes or None,
                    "expense_date": op.expense_date,
                    "kind": "investment",
                    "wallet": source,
                    "transfer_id": transfer_id,
                },
                {
                    "merchant": f"Transferência {_wallet_label(source)} → Investimentos",
                    "amount": amount,
                    "category": "Transferência",
                    "notes": "transferência interna",
                    "expense_date": op.expense_date,
                    "kind": "transfer_out",
                    "wallet": source,
                    "transfer_id": transfer_id,
                },
            ],
        )
        balances = await repo.general_balances(session, user.id)
        return OperationResult("invested", op, entries=entries, balances=balances)

    # conta ↔ dinheiro
    entries = await repo.create_expenses(
        session,
        user_id=user.id,
        entries=[
            {
                "merchant": f"Transferência {_wallet_label(source)} → {_wallet_label(dest)}",
                "amount": amount,
                "category": "Transferência",
                "notes": op.notes or "transferência interna",
                "expense_date": op.expense_date,
                "kind": "transfer_out",
                "wallet": source,
                "transfer_id": transfer_id,
            },
            {
                "merchant": f"Transferência {_wallet_label(source)} → {_wallet_label(dest)}",
                "amount": amount,
                "category": "Transferência",
                "notes": op.notes or "transferência interna",
                "expense_date": op.expense_date,
                "kind": "transfer_in",
                "wallet": dest,
                "transfer_id": transfer_id,
            },
        ],
    )
    balances = await repo.general_balances(session, user.id)
    return OperationResult("transferred", op, entries=entries, balances=balances)
