from painel.mensagens_cache import msg as _msg
import json
import logging
import re
import requests

from django.conf import settings as config
from django.db import transaction

from utils import banco

logger = logging.getLogger(__name__)

HEADERS = {
    "access_token": config.ASAAS_API_KEY,
    "Content-Type": "application/json",
}


def _get(endpoint: str) -> dict:
    url = f"{config.ASAAS_BASE_URL}/{endpoint}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code >= 400:
        logger.error("[Asaas] GET %s HTTP %s: %s", endpoint, r.status_code, r.text)
    r.raise_for_status()
    return r.json()


def _post(endpoint: str, payload: dict) -> dict:
    url = f"{config.ASAAS_BASE_URL}/{endpoint}"
    r = requests.post(url, json=payload, headers=HEADERS, timeout=15)
    if r.status_code >= 400:
        logger.error("[Asaas] POST %s HTTP %s: %s", endpoint, r.status_code, r.text)
    r.raise_for_status()
    return r.json()


def _update(endpoint: str, payload: dict) -> dict:
    url = f"{config.ASAAS_BASE_URL}/{endpoint}"
    r = requests.put(url, json=payload, headers=HEADERS, timeout=15)
    if r.status_code >= 400:
        logger.error("[Asaas] PUT %s HTTP %s: %s", endpoint, r.status_code, r.text)
    r.raise_for_status()
    return r.json()


def _formatar_telefone(telefone: str) -> str:
    """Garante telefone no formato numerico com prefixo 55."""
    fone = re.sub(r"\D", "", telefone)
    if not fone.startswith("55"):
        fone = "55" + fone

    logger.debug("[Asaas] Telefone formatado: %s -> %s", telefone, fone)
    return fone


def criar_ou_buscar_cliente(telefone: str, nome: str = None) -> str:
    """Retorna o customer_id do Asaas, criando o cliente se necessario."""
    assinante = banco.get_assinante(telefone) or {}
    customer_id = assinante.get("asaas_customer_id")
    cpf_cliente = assinante.get("cpf") or ""

    if not cpf_cliente:
        logger.warning("[Asaas] Assinante %s sem CPF — usando telefone como identificador", telefone)

    if customer_id:
        try:
            customer_data = _get(f"customers/{customer_id}")
            if cpf_cliente and not customer_data.get("cpfCnpj"):
                logger.info("[Asaas] Customer %s sem CPF. Atualizando...", customer_id)
                _update(f"customers/{customer_id}", {"cpfCnpj": cpf_cliente})
            logger.info("[Asaas] Customer ID existente e valido: %s", customer_id)
            return customer_id
        except Exception:
            logger.warning("[Asaas] Customer ID obsoleto: %s. Criando novo...", customer_id)

    nome_cliente = nome or assinante.get("nome") or f"Assinante {telefone[-4:]}"
    fone_limpo = _formatar_telefone(telefone)

    payload_cliente = {
        "name": nome_cliente,
        "mobilePhone": fone_limpo,
        "notificationDisabled": False,
    }
    if cpf_cliente:
        payload_cliente["cpfCnpj"] = cpf_cliente

    try:
        data = _post("customers", payload_cliente)
        customer_id = data["id"]
        banco.atualizar_assinante(telefone, asaas_customer_id=customer_id)
        logger.info("[Asaas] Cliente criado com sucesso: %s", customer_id)
        return customer_id

    except requests.exceptions.HTTPError as e:
        resp_text = e.response.text if hasattr(e, "response") and e.response is not None else str(e)
        logger.error("[Asaas] Erro ao criar cliente: %s", resp_text)

        if cpf_cliente and e.response is not None and e.response.status_code == 400:
            try:
                customers = _get(f"customers?cpfCnpj={cpf_cliente}")
                if customers.get("data"):
                    customer_id = customers["data"][0]["id"]
                    banco.atualizar_assinante(telefone, asaas_customer_id=customer_id)
                    logger.info("[Asaas] Cliente encontrado por CPF: %s", customer_id)
                    return customer_id
            except Exception as inner_e:
                logger.error("[Asaas] Falha na busca alternativa: %s", inner_e)

        raise e


def criar_cobranca_assinatura(telefone: str) -> str:
    """Mantido por compatibilidade: gera cobrança única em cartão."""
    data = criar_link_cartao(telefone)
    return data.get("url", "")


def criar_link_cartao(telefone: str, valor: float = None) -> dict:
    """
    Gera um payment link de cobrança ÚNICA em cartão (sem recorrência).
    Quando o plano expirar ou as fichas acabarem, um novo link é gerado.
    """
    assinante = banco.get_assinante(telefone) or {}
    customer_id = criar_ou_buscar_cliente(telefone)
    nome = assinante.get("nome") or f"Assinante {telefone[-4:]}"
    valor_final = valor or config.PLANO_VALOR

    logger.info("[Asaas] Criando payment link cartao (avulso) para %s (customer=%s, valor=%s)", telefone, customer_id, valor_final)

    payload = {
        "billingType": "CREDIT_CARD",
        "chargeType": "DETACHED",
        "name": f"Mindnutri Plano Mensal {telefone[-4:]}",
        "description": f"Mindhub Mindnutri - Plano Mensal (R$ {valor_final:.2f})",
        "value": valor_final,
        "notificationEnabled": False,
        "externalReference": telefone,
    }

    data = _post("paymentLinks", payload)

    logger.info("[Asaas] Payment link avulso criado: %s -> %s", data.get('id'), data.get('url'))
    return {
        "payment_link_id": data.get("id", ""),
        "url": data.get("url", ""),
        "customer_id": customer_id,
        "nome": nome,
    }


def criar_link_cartao_avulso(telefone: str, valor: float, descricao: str) -> dict:
    """Gera um payment link avulso em cartao, sem boleto."""
    customer_id = criar_ou_buscar_cliente(telefone)
    logger.info("[Asaas] Criando payment link avulso em cartao para %s (customer=%s)", telefone, customer_id)

    data = _post(
        "paymentLinks",
        {
            "billingType": "CREDIT_CARD",
            "chargeType": "DETACHED",
            "name": f"Mindnutri Pagamento {telefone[-4:]}",
            "description": descricao,
            "value": valor,
            "notificationEnabled": False,
            "externalReference": telefone,
        },
    )

    logger.info("[Asaas] Payment link avulso criado: %s -> %s", data.get('id'), data.get('url'))
    return {
        "payment_link_id": data.get("id", ""),
        "url": data.get("url", ""),
        "customer_id": customer_id,
    }


def criar_cobranca_pix(telefone: str, valor: float, descricao: str) -> dict:
    """
    Cria uma cobranca avulsa via Pix.
    O Asaas exige conta aprovada para liberar este meio de pagamento.
    """
    from datetime import date, timedelta

    customer_id = criar_ou_buscar_cliente(telefone)
    data = _post(
        "payments",
        {
            "customer": customer_id,
            "billingType": "PIX",
            "value": valor,
            "dueDate": (date.today() + timedelta(days=1)).isoformat(),
            "description": descricao,
        },
    )

    payment_id = data["id"]
    qr_data = {}
    try:
        qr_data = _get(f"payments/{payment_id}/pixQrCode")
    except Exception as exc:
        logger.warning("[Asaas] Pix criado sem QR complementar: %s", exc)

    return {
        "payment_id": payment_id,
        "customer_id": customer_id,
        "invoice_url": data.get("invoiceUrl", ""),
        "pix_copy_paste": qr_data.get("payload", ""),
        "pix_base64": qr_data.get("encodedImage", ""),
    }


def criar_cobranca_avulsa(telefone: str, valor: float, descricao: str) -> str:
    """Mantido por compatibilidade: gera link avulso em cartao."""
    data = criar_link_cartao_avulso(telefone, valor, descricao)
    return data.get("url", "")


def processar_webhook_asaas(evento: str, payment_data: dict) -> None:
    """
    Processa webhooks do Asaas com idempotência ATÔMICA.
    Registra ANTES de processar — se já existe, ignora.
    """
    from painel.models import WebhookProcessado

    payment_id = payment_data.get("id", "")
    evento_id = f"{evento}:{payment_id}" if payment_id else ""

    if not evento_id:
        logger.warning("[Asaas] Webhook sem payment_id ignorado: %s", evento)
        return

    # Idempotência atômica: get_or_create usa INSERT ON CONFLICT (unique)
    _, created = WebhookProcessado.objects.get_or_create(
        evento_id=evento_id,
        defaults={"evento_tipo": evento},
    )
    if not created:
        logger.info("[Asaas] Webhook duplicado ignorado: %s", evento_id)
        return

    customer_id = payment_data.get("customer", "")
    payment_link_id = payment_data.get("paymentLink", "")

    assinante = _buscar_por_customer_id(customer_id)
    if not assinante and payment_link_id:
        assinante = _buscar_por_payment_link_id(payment_link_id)
    if not assinante:
        logger.warning("[Asaas] Webhook ignorado - customer nao encontrado: %s / paymentLink: %s", customer_id, payment_link_id)
        return

    telefone = assinante["telefone"]

    with transaction.atomic():
        if customer_id and assinante.get("asaas_customer_id") != customer_id:
            banco.atualizar_assinante(telefone, asaas_customer_id=customer_id)

        if evento in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
            _processar_pagamento_confirmado(telefone, assinante)

        elif evento == "PAYMENT_OVERDUE":
            banco.atualizar_assinante(telefone, status="inadimplente")
            banco.criar_notificacao(
                "inadimplencia",
                "critico",
                "Pagamento em atraso",
                f"{assinante.get('nome', telefone)} - pagamento em atraso.",
                telefone,
            )
            from utils.whatsapp import enviar_texto
            enviar_texto(telefone, _msg("webhook_pagamento_atraso"))

        elif evento in ("SUBSCRIPTION_INACTIVATED", "PAYMENT_DELETED"):
            banco.atualizar_assinante(telefone, status="cancelado")
            banco.criar_notificacao(
                "cancelamento",
                "aviso",
                "Assinatura cancelada",
                f"{assinante.get('nome', telefone)} - assinatura cancelada.",
                telefone,
            )


def _processar_pagamento_confirmado(telefone: str, assinante: dict) -> None:
    """Ativa assinante após pagamento confirmado."""
    from datetime import date, timedelta

    era_primeiro = assinante.get("status") in ("pendente", "bloqueado", "inadimplente")
    banco.atualizar_assinante(
        telefone,
        status="ativo",
        data_inicio=assinante.get("data_inicio") or date.today().isoformat(),
        proxima_cobranca=(date.today() + timedelta(days=30)).isoformat(),
        fichas_geradas_mes=0,
    )

    if era_primeiro:
        banco.criar_notificacao(
            "novo_assinante", "info", "Pagamento confirmado",
            f"{assinante.get('nome', telefone)} - pagamento confirmado. Acesso ativado.",
            telefone,
        )
        _boas_vindas_pos_pagamento(telefone)
    else:
        banco.criar_notificacao(
            "novo_assinante", "info", "Assinatura renovada",
            f"{assinante.get('nome', telefone)} - pagamento recebido. Ciclo renovado.",
            telefone,
        )
        from utils.whatsapp import enviar_texto
        enviar_texto(telefone, _msg("webhook_pagamento_renovado"))


def _buscar_por_customer_id(customer_id: str) -> dict | None:
    """Busca assinante no banco pelo customer_id do Asaas."""
    if not customer_id:
        return None

    from painel.models import Assinante

    try:
        a = Assinante.objects.get(asaas_id=customer_id)
        return banco.get_assinante(a.telefone)
    except Assinante.DoesNotExist:
        return None


def _buscar_por_payment_link_id(payment_link_id: str) -> dict | None:
    """Busca assinante pelo payment_link_id indexado no modelo."""
    if not payment_link_id:
        return None

    from painel.models import Assinante

    try:
        a = Assinante.objects.get(payment_link_id=payment_link_id)
        return banco.get_assinante(a.telefone)
    except Assinante.DoesNotExist:
        pass

    # Fallback: busca no estado da conversa (legado)
    from painel.models import EstadoConversa
    for estado in EstadoConversa.objects.all():
        try:
            dados = json.loads(estado.dados_temp or "{}")
        except json.JSONDecodeError:
            continue
        if dados.get("payment_link_id") == payment_link_id:
            return banco.get_assinante(estado.telefone)

    return None


def _boas_vindas_pos_pagamento(telefone: str) -> None:
    """Boas-vindas ao novo assinante após confirmar o pagamento."""
    from utils.whatsapp import enviar_texto
    from utils.banco import resetar_estado

    assinante = banco.get_assinante(telefone) or {}
    nome = assinante.get("nome") or "cliente"
    fichas_rest = assinante.get("fichas_limite_mes", getattr(config, "PLANO_FICHAS_LIMITE", 30))

    resetar_estado(telefone)
    enviar_texto(telefone, _msg("webhook_boas_vindas", nome=nome, fichas_rest=fichas_rest))
