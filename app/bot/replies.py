"""Modelos de resposta do bot em português (PT-BR)."""

from __future__ import annotations

from app.utils.money import format_brl

WELCOME = (
    "Olá, {name}! 👋 Eu sou seu assistente financeiro.\n\n"
    "É só me mandar o que gastou ou recebeu, como você fala:\n"
    "  • gastei 47 no mercado\n"
    "  • recebi 3200 de salário\n"
    "  • investi 500 no tesouro direto\n"
    "  • resgata 300 do tesouro pra conta\n"
    "  • move 200 da conta pro dinheiro\n"
    "  • remove o último lançamento\n"
    "  • 🎙️ mande um áudio (ex: paguei 40 na netflix)\n"
    "  • 🧾 mande foto do comprovante\n\n"
    "Comandos:\n"
    "/today – gastos de hoje\n"
    "/month – resumo do mês\n"
    "/saldo – saldos gerais (conta + dinheiro)\n"
    "/desfazer – apaga o último lançamento\n"
    "/remover – apaga um lançamento (ex: /remover 500 dos investimentos)\n"
    "/export – relatório em PDF\n"
    "/dashboard – abrir o painel web\n"
    "/help – ver esta mensagem\n\n"
    "💡 Pra lançar em dinheiro vivo, inclua na mensagem: `gastei 20 em dinheiro`"
)

HELP = WELCOME

UNPARSEABLE = (
    "Não entendi 😅 Tente algo como `gastei 45 no ifood`, `recebi 3200 de salário`, "
    "`resgata 300 do tesouro pra conta` ou `remove o último lançamento`."
)

LOGGED_EXPENSE = "💸 Gasto registrado: {amount} · {merchant} · {category}"
LOGGED_INCOME = "💰 Entrada registrada: {amount} · {merchant} · {category}"
LOGGED_INVESTMENT = "📈 Investimento registrado: {amount} · {merchant} · {category}"

NO_TODAY = "Nada registrado hoje ainda. Me mande um gasto ou entrada pra começar!"
NO_MONTH = "Nada registrado este mês ainda."

DASHBOARD_LINK = (
    "Aqui está seu link do painel (válido por 15 minutos):\n{url}\n\n"
    "Abra em qualquer navegador; vamos salvar um cookie pra você não precisar entrar de novo."
)

KIND_LABELS = {
    "expense": "Gasto",
    "income": "Entrada",
    "investment": "Investimento",
    "investment_out": "Resgate",
    "transfer_in": "Transferência",
    "transfer_out": "Transferência",
}

WALLET_LABELS = {
    "conta": "Conta",
    "dinheiro": "Dinheiro",
    "investimento": "Investimentos",
}


def _wallet(wallet: str) -> str:
    return WALLET_LABELS.get(wallet, wallet.title() if wallet else "—")


def format_operation_result(result) -> str:
    """Formata o resultado de uma operação para o Telegram.

    Recebe um ``app.services.operations.OperationResult`` sem importá-lo
    (mantém o módulo de respostas livre de dependências de banco).
    """
    op = result.operation

    if result.status == "created":
        entry = result.entry
        template = {
            "income": LOGGED_INCOME,
            "investment": LOGGED_INVESTMENT,
        }.get(entry.kind, LOGGED_EXPENSE)
        wallet_tag = " · 💵 dinheiro" if entry.wallet == "dinheiro" else ""
        return template.format(
            amount=format_brl(entry.amount),
            merchant=entry.merchant,
            category=entry.category,
        ) + wallet_tag

    if result.status == "deleted":
        entry = result.entry
        if entry is None:
            return "🗑️ Lançamento removido."
        amount = format_brl(entry.amount)
        if len(result.entries) > 1:
            head = f"🗑️ Transferência desfeita: {amount} · {entry.merchant}"
        else:
            label = KIND_LABELS.get(entry.kind, "Lançamento")
            head = f"🗑️ Removido: {amount} · {entry.merchant} · {label}"
        if result.balances is not None:
            head += f"\n📈 Investido agora: {format_brl(result.balances.get('investido', 0))}"
        return head

    if result.status == "transferred":
        head = (
            f"🔁 Transferência: {format_brl(op.amount)} · "
            f"{_wallet(op.wallet)} → {_wallet(op.wallet_to)}"
        )
        if result.balances is not None:
            head += (
                f"\n🏦 Conta: {format_brl(result.balances.get('conta', 0))}"
                f"\n💵 Dinheiro: {format_brl(result.balances.get('dinheiro', 0))}"
            )
        return head

    if result.status == "redeemed":
        head = (
            f"📤 Resgate: {format_brl(op.amount)} · "
            f"Investimentos → {_wallet(op.wallet_to)}"
        )
        if result.balances is not None:
            head += (
                f"\n📈 Investido agora: {format_brl(result.balances.get('investido', 0))}"
                f"\n🏦 {_wallet(op.wallet_to)}: "
                f"{format_brl(result.balances.get(op.wallet_to, 0))}"
            )
        return head

    if result.status == "invested":
        head = (
            f"📈 Aporte: {format_brl(op.amount)} · "
            f"{_wallet(op.wallet)} → Investimentos"
        )
        if result.balances is not None:
            head += (
                f"\n📈 Investido agora: {format_brl(result.balances.get('investido', 0))}"
                f"\n🏦 {_wallet(op.wallet)}: "
                f"{format_brl(result.balances.get(op.wallet, 0))}"
            )
        return head

    if result.status == "not_found":
        return (
            "Não encontrei nenhum lançamento com esses dados 🤔\n"
            "Confira os lançamentos em /month ou no painel e tente de novo."
        )

    if result.status == "needs_detail":
        if op.action == "delete":
            return (
                "Preciso saber o que remover 🤔\n"
                "Diga o valor, a descrição, o tipo ou apenas `último`.\n"
                "Ex: `remove 500 dos investimentos` ou `apaga o último lançamento`."
            )
        return (
            "Preciso do valor e do caminho da transferência 🤔\n"
            "Ex: `resgata 500 do tesouro pra conta` ou "
            "`move 200 da conta pro dinheiro`."
        )

    if result.status == "invalid":
        return (
            "Não consegui fazer essa transferência 😅\n"
            "Origem e destino precisam ser diferentes (conta, dinheiro ou investimentos).\n"
            "Ex: `move 200 da conta pro dinheiro`."
        )

    return UNPARSEABLE
