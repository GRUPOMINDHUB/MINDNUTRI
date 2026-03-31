"""
Views Django do agente Mindnutri.
Recebe webhooks da Evolution API e do Asaas.
"""
import hmac
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from utils.asaas import processar_webhook_asaas
from utils.whatsapp import extrair_webhook
from agente_app.nucleo import processar_mensagem

logger = logging.getLogger(__name__)

# ── CONCORRÊNCIA: pool limitado + lock por telefone ──────────────
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mindnutri")
_user_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_user_lock(telefone: str) -> threading.Lock:
    with _locks_lock:
        if telefone not in _user_locks:
            _user_locks[telefone] = threading.Lock()
        return _user_locks[telefone]


def _processar_em_background(telefone: str, tipo: str, texto: str | None,
                              midia_id: str | None, midia_bytes: bytes | None) -> None:
    """Processa a mensagem em thread separada, serializada por telefone."""
    lock = _get_user_lock(telefone)
    if not lock.acquire(timeout=120):
        logger.warning("[Agente] Timeout aguardando lock para %s — descartando mensagem", telefone)
        return
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
        from utils.alertas_grupo import alertar_erro
        alertar_erro("Erro Genérico", safe_msg, telefone=telefone)
    finally:
        lock.release()


@csrf_exempt
@require_POST
def webhook_whatsapp(request):
    """Recebe eventos da Evolution API."""
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "erro": "JSON inválido"}, status=400)

    msg = extrair_webhook(payload)

    if not msg:
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

    # Processa em background via thread pool (serializado por telefone)
    _executor.submit(_processar_em_background, telefone, tipo, texto, midia_id, midia_bytes)

    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def webhook_asaas(request):
    """Recebe eventos de pagamento do Asaas com verificação de token."""
    # Verificação de autenticidade via access_token (configurado na URL do webhook no Asaas)
    token_esperado = getattr(settings, "ASAAS_WEBHOOK_TOKEN", "")
    if token_esperado:
        token_recebido = request.GET.get("access_token", "")
        if not hmac.compare_digest(token_recebido, token_esperado):
            logger.warning("[Asaas] Webhook rejeitado: token inválido de %s",
                           request.META.get("REMOTE_ADDR", "?"))
            return JsonResponse({"ok": False}, status=401)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False}, status=400)

    evento = payload.get("event", "")
    payment_data = payload.get("payment", {})

    processar_webhook_asaas(evento, payment_data)

    return JsonResponse({"ok": True})
