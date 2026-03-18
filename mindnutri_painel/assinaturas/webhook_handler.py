"""
Handler centralizado de webhooks do Asaas.
Mapeia todos os eventos relevantes para ações no sistema.
"""
from servico_assinaturas import (
    ativar_assinante,
    renovar_assinante,
    bloquear_por_inadimplencia,
    cancelar_assinante,
)
from utils import banco


def processar(evento: str, payload: dict):
    """Ponto de entrada do webhook. Roteia para o handler correto."""
    print(f"[Webhook Asaas] Evento recebido: {evento}")

    handlers = {
        "PAYMENT_CONFIRMED":            _on_payment_confirmed,
        "PAYMENT_RECEIVED":             _on_payment_confirmed,
        "PAYMENT_OVERDUE":              _on_payment_overdue,
        "PAYMENT_REFUNDED":             _on_payment_refunded,
        "PAYMENT_CHARGEBACK_REQUESTED": _on_payment_chargeback,
        "PAYMENT_DELETED":              _on_payment_deleted,
        "SUBSCRIPTION_INACTIVATED":     _on_subscription_inactivated,
        "SUBSCRIPTION_DELETED":         _on_subscription_inactivated,
    }

    handler = handlers.get(evento)
    if not handler:
        print(f"[Webhook Asaas] Evento ignorado: {evento}")
        return

    payment_data     = payload.get("payment", {})
    subscription_data = payload.get("subscription", {})
    customer_id = (
        payment_data.get("customer") or
        subscription_data.get("customer") or
        payload.get("customer")
    )

    if not customer_id:
        print(f"[Webhook Asaas] customer_id não encontrado")
        return

    telefone = _telefone_por_customer(customer_id)
    if not telefone:
        print(f"[Webhook Asaas] Assinante não encontrado: {customer_id}")
        return

    try:
        handler(telefone, payment_data or subscription_data)
    except Exception as e:
        print(f"[Webhook Asaas] Erro no handler {evento}: {e}")
        banco.criar_notificacao(
            "erro_sistema", "critico",
            f"Erro ao processar webhook {evento}",
            f"customer_id={customer_id}, erro={str(e)}",
            telefone,
        )


# ── HANDLERS ──────────────────────────────────────────────────────

def _on_payment_confirmed(telefone: str, data: dict):
    assinante = banco.get_assinante(telefone)
    if not assinante:
        return
    if assinante.get("status") in ("pendente", "cancelado", "bloqueado", "inadimplente"):
        ativar_assinante(telefone, data)
    else:
        renovar_assinante(telefone)


def _on_payment_overdue(telefone: str, data: dict):
    bloquear_por_inadimplencia(telefone, data)


def _on_payment_refunded(telefone: str, data: dict):
    banco.atualizar_assinante(telefone, status="bloqueado")
    banco.criar_notificacao(
        "inadimplencia", "aviso",
        "Pagamento estornado",
        f"Assinante {telefone} — pagamento estornado. Acesso suspenso.",
        telefone,
    )
    from utils.whatsapp import enviar_texto
    enviar_texto(telefone,
        "⚠️ Identificamos um estorno no seu pagamento.\n\n"
        "Seu acesso foi suspenso. Entre em contato com o suporte Mindhub. 💙"
    )


def _on_payment_chargeback(telefone: str, data: dict):
    banco.atualizar_assinante(telefone, status="bloqueado")
    banco.criar_notificacao(
        "inadimplencia", "critico",
        "Chargeback solicitado",
        f"Assinante {telefone} solicitou chargeback. Verificação necessária.",
        telefone,
    )


def _on_payment_deleted(telefone: str, data: dict):
    banco.criar_notificacao(
        "cancelamento", "info",
        "Cobrança deletada",
        f"Cobrança do assinante {telefone} foi deletada no Asaas.",
        telefone,
    )


def _on_subscription_inactivated(telefone: str, data: dict):
    cancelar_assinante(telefone)


# ── HELPER ────────────────────────────────────────────────────────

def _telefone_por_customer(customer_id: str):
    from utils.banco import conn
    with conn() as c:
        row = c.execute(
            "SELECT telefone FROM assinantes WHERE asaas_customer_id = ?",
            (customer_id,)
        ).fetchone()
    return row["telefone"] if row else None
