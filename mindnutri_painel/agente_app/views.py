"""
Views Django do agente Mindnutri.
Recebe webhooks da Evolution API e do Asaas.
"""
import json
import threading
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from utils import banco, whatsapp
from utils.asaas import processar_webhook_asaas
from agente_app.nucleo import processar_mensagem


def _processar_em_background(telefone, tipo, texto, midia_id, midia_bytes):
    """Processa a mensagem em thread separada para não bloquear o webhook."""
    try:
        processar_mensagem(
            telefone=telefone,
            tipo=tipo,
            texto=texto,
            midia_id=midia_id,
            midia_bytes=midia_bytes,
        )
    except Exception as e:
        safe_msg = repr(e).encode('utf-8', 'ignore').decode('utf-8')
        print(f"[Agente] Erro ao processar mensagem de {telefone}: {safe_msg}")
        import traceback
        traceback.print_exc()


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
        return JsonResponse({"ok": True, "ignorado": True})

    telefone = msg["telefone"]
    tipo     = msg["tipo"]
    texto    = msg.get("texto")
    midia_id = msg.get("midia_id")
    midia_bytes = None

    # Baixar mídia se necessário
    if midia_id and tipo in ("audio", "imagem", "documento"):
        from utils.whatsapp import baixar_midia
        midia_bytes = baixar_midia(None, midia_id)

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


@csrf_exempt
def onboarding_continuar(request):
    """
    Processa respostas do onboarding pós-pagamento.
    O onboarding é feito via WhatsApp — essa view é apenas para referência.
    """
    return JsonResponse({"ok": True})
