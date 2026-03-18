import requests
from django.conf import settings as config
from utils import banco

HEADERS = {
    "access_token": config.ASAAS_API_KEY,
    "Content-Type": "application/json",
}


def _get(endpoint: str) -> dict:
    r = requests.get(f"{config.ASAAS_BASE_URL}/{endpoint}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(endpoint: str, payload: dict) -> dict:
    r = requests.post(f"{config.ASAAS_BASE_URL}/{endpoint}",
                      json=payload, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def criar_ou_buscar_cliente(telefone: str, nome: str = None) -> str:
    """Retorna o customer_id do Asaas, criando o cliente se necessário."""
    assinante = banco.get_assinante(telefone)

    if assinante and assinante.get("asaas_customer_id"):
        return assinante["asaas_customer_id"]

    nome_cliente = nome or assinante.get("nome") or f"Cliente {telefone[-4:]}"
    # Telefone no formato esperado pelo Asaas
    fone_limpo = telefone.replace("+", "").replace("-", "").replace(" ", "")

    data = _post("customers", {
        "name":         nome_cliente,
        "mobilePhone":  fone_limpo,
        "notificationDisabled": False,
    })

    customer_id = data["id"]
    banco.atualizar_assinante(telefone, asaas_customer_id=customer_id)
    return customer_id


def criar_cobranca_assinatura(telefone: str) -> str:
    """
    Cria uma assinatura recorrente mensal no Asaas.
    Retorna o link de pagamento.
    """
    from datetime import date
    customer_id = criar_ou_buscar_cliente(telefone)

    data = _post("subscriptions", {
        "customer":     customer_id,
        "billingType":  "UNDEFINED",   # Pix ou cartão — cliente escolhe
        "value":        config.PLANO_VALOR,
        "nextDueDate":  date.today().isoformat(),
        "cycle":        "MONTHLY",
        "description":  "Mindhub Mindnutri — Assinatura Mensal",
    })

    subscription_id = data["id"]
    banco.atualizar_assinante(telefone, asaas_subscription_id=subscription_id)

    # Busca o link de pagamento da primeira cobrança
    pagamentos = _get(f"subscriptions/{subscription_id}/payments")
    if pagamentos.get("data"):
        primeiro = pagamentos["data"][0]
        link = primeiro.get("invoiceUrl") or primeiro.get("bankSlipUrl", "")
        return link

    return data.get("invoiceUrl", "")


def criar_cobranca_avulsa(telefone: str, valor: float, descricao: str) -> str:
    """Cria uma cobrança avulsa (renovação antecipada, etc.)."""
    from datetime import date
    customer_id = criar_ou_buscar_cliente(telefone)

    data = _post("payments", {
        "customer":    customer_id,
        "billingType": "UNDEFINED",
        "value":       valor,
        "dueDate":     date.today().isoformat(),
        "description": descricao,
    })

    return data.get("invoiceUrl") or data.get("bankSlipUrl", "")


def processar_webhook_asaas(evento: str, payment_data: dict):
    """
    Processa webhooks do Asaas:
    PAYMENT_CONFIRMED → ativa assinante
    PAYMENT_OVERDUE   → marca inadimplente
    SUBSCRIPTION_INACTIVATED → cancela
    """
    customer_id = payment_data.get("customer", "")

    # Busca o assinante pelo customer_id
    assinante = _buscar_por_customer_id(customer_id)
    if not assinante:
        print(f"[Asaas] Webhook ignorado — customer não encontrado: {customer_id}")
        return

    telefone = assinante["telefone"]

    if evento == "PAYMENT_CONFIRMED":
        from datetime import date, timedelta
        banco.atualizar_assinante(telefone,
            status="ativo",
            data_inicio=date.today().isoformat(),
            proxima_cobranca=(date.today() + timedelta(days=30)).isoformat(),
            fichas_geradas_mes=0,
        )
        banco.criar_notificacao(
            "novo_assinante", "info",
            "Pagamento confirmado",
            f"{assinante.get('nome', telefone)} — pagamento confirmado. Acesso ativado.",
            telefone
        )
        # Boas-vindas ao novo assinante
        _boas_vindas_pos_pagamento(telefone, assinante)

    elif evento == "PAYMENT_OVERDUE":
        banco.atualizar_assinante(telefone, status="inadimplente")
        banco.criar_notificacao(
            "inadimplencia", "critico",
            "Pagamento em atraso",
            f"{assinante.get('nome', telefone)} — pagamento em atraso. Acesso bloqueado.",
            telefone
        )
        from utils.whatsapp import enviar_texto
        enviar_texto(telefone,
            "⚠️ Seu pagamento está em atraso e seu acesso foi suspenso.\n\n"
            "Para reativar, acesse o link abaixo ou entre em contato com nosso suporte.")

    elif evento in ("SUBSCRIPTION_INACTIVATED", "PAYMENT_DELETED"):
        banco.atualizar_assinante(telefone, status="cancelado")
        banco.criar_notificacao(
            "cancelamento", "aviso",
            "Assinatura cancelada",
            f"{assinante.get('nome', telefone)} — assinatura cancelada.",
            telefone
        )


def _buscar_por_customer_id(customer_id: str) -> dict | None:
    """Busca assinante no banco pelo customer_id do Asaas."""
    import sqlite3
    from utils.banco import DB_PATH, conn
    with conn() as c:
        row = c.execute(
            "SELECT * FROM assinantes WHERE asaas_customer_id = ?", (customer_id,)
        ).fetchone()
    return dict(row) if row else None


def _boas_vindas_pos_pagamento(telefone: str, assinante: dict):
    """Inicia o onboarding após pagamento confirmado."""
    from utils.whatsapp import enviar_texto
    from utils.banco import set_estado

    enviar_texto(telefone,
        "🎉 Parabéns! Sua assinatura Mindnutri foi ativada!\n\n"
        "Vou fazer algumas perguntas rápidas para personalizar sua experiência.\n\n"
        "Qual é o seu nome completo?")
    set_estado(telefone, "onboarding_nome", {})
