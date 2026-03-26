"""
Views Django do agente Mindnutri.
Recebe webhooks da Evolution API e do Asaas.
"""
import sys
import json
import logging
import threading
import io

# ── FIX CRITICO: Forca stdout/stderr para UTF-8 no Windows ─────
# Sem isto, qualquer print() com emoji/acentos crasha threads silenciosamente
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from utils import banco, whatsapp
from utils.asaas import processar_webhook_asaas
from agente_app.nucleo import processar_mensagem

logger = logging.getLogger(__name__)


def _processar_em_background(telefone: str, tipo: str, texto: str | None,
                              midia_id: str | None, midia_bytes: bytes | None) -> None:
    """Processa a mensagem em thread separada para não bloquear o webhook."""
    try:
        logger.info("[Agente] Iniciando processamento para %s (tipo: %s)", telefone, tipo)
        processar_mensagem(
            telefone=telefone,
            tipo=tipo,
            texto=texto,
            midia_id=midia_id,
            midia_bytes=midia_bytes,
        )
        logger.info("[Agente] Processamento concluído para %s", telefone)
    except Exception as e:
        safe_msg = repr(e).encode('utf-8', 'ignore').decode('utf-8')
        logger.error("[Agente] Erro ao processar mensagem de %s: %s", telefone, safe_msg, exc_info=True)


@csrf_exempt
@require_POST
def webhook_whatsapp(request):
    """Recebe eventos da Evolution API."""
    try:
        payload = json.loads(request.body)
        import pathlib
        with open("webhook_payloads.txt", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n\n---\n\n")
    except Exception:
        return JsonResponse({"ok": False, "erro": "JSON inv\u00e1lido"}, status=400)

    from utils.whatsapp import extrair_webhook
    msg = extrair_webhook(payload)

    if not msg:
        logger.debug("[Webhook] Mensagem ignorada (não é mensagens.upsert ou é do bot)")
        return JsonResponse({"ok": True, "ignorado": True})

    telefone = msg["telefone"]
    tipo     = msg["tipo"]
    logger.info("[Webhook] Recebido de %s - Tipo: %s", telefone, tipo)
    texto    = msg.get("texto")
    midia_id = msg.get("midia_id")
    mensagem_completa = msg.get("mensagem_completa")
    midia_bytes = None

    # Baixar mídia se necessário
    if midia_id and tipo in ("audio", "imagem", "documento"):
        from utils.whatsapp import baixar_midia
        logger.info("[Webhook] Baixando midia: id=%s tem_msg_completa=%s", midia_id, mensagem_completa is not None)
        midia_bytes = baixar_midia(
            media_key=midia_id,
            mensagem_completa=mensagem_completa,
        )
        logger.info("[Webhook] Resultado download: %s", f"OK {len(midia_bytes)} bytes" if midia_bytes else "FALHOU")

    # Processa em background (responde ao webhook imediatamente)
    t = threading.Thread(
        target=_processar_em_background,
        args=(telefone, tipo, texto, midia_id, midia_bytes),
        daemon=True
    )
    t.start()

    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def webhook_asaas(request):
    """Recebe eventos de pagamento do Asaas."""
    try:
        payload = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False}, status=400)

    evento = payload.get("event", "")
    payment_data = payload.get("payment", {})

    processar_webhook_asaas(evento, payment_data)

    return JsonResponse({"ok": True})
