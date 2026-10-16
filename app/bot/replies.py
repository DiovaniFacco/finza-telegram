"""Modelos de resposta do bot em português (PT-BR)."""

from __future__ import annotations

WELCOME = (
    "Olá, {name}! 👋 Eu sou seu assistente financeiro.\n\n"
    "É só me mandar o que gastou ou recebeu, como você fala:\n"
    "  • gastei 47 no mercado\n"
    "  • recebi 3200 de salário\n"
    "  • investi 500 no tesouro direto\n"
    "  • 🎙️ mande um áudio (ex: paguei 40 na netflix)\n"
    "  • 🧾 mande foto do comprovante\n\n"
    "Comandos:\n"
    "/today – gastos de hoje\n"
    "/month – resumo do mês\n"
    "/saldo – saldos gerais (conta + dinheiro)\n"
    "/export – relatório em PDF\n"
    "/dashboard – abrir o painel web\n"
    "/help – ver esta mensagem\n\n"
    "💡 Pra lançar em dinheiro vivo, inclua na mensagem: `gastei 20 em dinheiro`"
)

HELP = WELCOME

UNPARSEABLE = (
    "Não entendi 😅 Tente algo como `gastei 45 no ifood` ou `recebi 3200 de salário`."
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
