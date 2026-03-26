import logging
import requests
import base64
import os
from django.conf import settings as config

logger = logging.getLogger(__name__)

HEADERS = {
    "apikey": config.EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}
BASE = f"{config.EVOLUTION_API_URL}/message"
INST = config.EVOLUTION_INSTANCE

_MIME_TYPES: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _post(endpoint: str, payload: dict) -> dict:
    url = f"{BASE}/{endpoint}/{INST}"
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        safe_endpoint = str(endpoint).encode('utf-8', 'ignore').decode('utf-8')
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        logger.error("[Evolution] Erro em %s: %s", safe_endpoint, safe_msg)
        return {}


def enviar_texto(telefone: str, texto: str) -> dict:
    """Envia mensagem de texto simples."""
    return _post("sendText", {
        "number": telefone,
        "text": texto,
    })


def enviar_arquivo(telefone: str, caminho: str, caption: str = "") -> dict:
    """Envia arquivo (PDF ou XLSX) como documento."""
    ext = os.path.splitext(caminho)[1].lower()
    mimetype = _MIME_TYPES.get(ext, "application/octet-stream")
    nome_arquivo = os.path.basename(caminho)

    with open(caminho, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    return _post("sendMedia", {
        "number": telefone,
        "mediatype": "document",
        "mimetype": mimetype,
        "media": b64,
        "fileName": nome_arquivo,
        "caption": caption,
    })


def enviar_imagem(telefone: str, caminho: str, caption: str = "") -> dict:
    """Envia imagem."""
    ext = os.path.splitext(caminho)[1].lower()
    mimetype = _MIME_TYPES.get(ext, "image/jpeg")
    nome_arquivo = os.path.basename(caminho)

    with open(caminho, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    return _post("sendMedia", {
        "number": telefone,
        "mediatype": "image",
        "mimetype": mimetype,
        "media": b64,
        "fileName": nome_arquivo,
        "caption": caption,
    })


def baixar_midia(media_url: str = None, media_key: str = None,
                 mensagem_completa: dict = None) -> bytes | None:
    """
    Baixa mídia (áudio, imagem, documento) da Evolution API.
    Extrai key da mensagem_completa se disponível, senão usa media_key.
    """
    try:
        url = f"{config.EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{INST}"

        # Monta a key para o download
        if mensagem_completa and "key" in mensagem_completa:
            msg_key = mensagem_completa["key"]
        else:
            msg_key = {"id": media_key}

        payload = {"message": {"key": msg_key}}

        logger.info("[Evolution] Baixando midia: id=%s", msg_key.get('id', '?'))
        r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        logger.info("[Evolution] Resposta: status=%s", r.status_code)

        # Evolution API retorna 200 ou 201 para sucesso
        if r.status_code in (200, 201):
            data = r.json()
            b64 = data.get("base64", "")
            if b64:
                decoded = base64.b64decode(b64)
                logger.info("[Evolution] Midia OK: %d bytes", len(decoded))
                return decoded
            else:
                logger.warning("[Evolution] Resposta sem base64. Chaves: %s", list(data.keys()))
        else:
            logger.error("[Evolution] Erro HTTP %s: %s", r.status_code, r.text[:300])
    except Exception as e:
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        logger.error("[Evolution] Erro ao baixar midia: %s", safe_msg)
    return None


def extrair_webhook(payload: dict) -> dict | None:
    """
    Normaliza o payload do webhook da Evolution API.
    Retorna dict com: telefone, tipo, texto, midia_url, midia_tipo, midia_id
    Retorna None se não for mensagem de usuário.
    """
    try:
        event = payload.get("event", "")
        if event != "messages.upsert":
            return None

        data = payload.get("data", {})
        key  = data.get("key", {})

        # Ignora mensagens enviadas pelo próprio bot
        if key.get("fromMe", False):
            return None

        remote = key.get("remoteJid", "")

        # Linked Device (@lid): o remoteJid nao e um numero de telefone valido.
        # O campo top-level "sender" contem o numero real do usuario.
        if remote.endswith("@lid"):
            sender = payload.get("sender", "")
            telefone = sender.split("@")[0]
        else:
            telefone = remote.split("@")[0]

        msg = data.get("message", {})

        # Texto simples
        if "conversation" in msg:
            return {"telefone": telefone, "tipo": "texto",
                    "texto": msg["conversation"].strip(), "midia_id": None}

        # Texto estendido
        if "extendedTextMessage" in msg:
            return {"telefone": telefone, "tipo": "texto",
                    "texto": msg["extendedTextMessage"]["text"].strip(),
                    "midia_id": None}

        # Dados completos para download de mídia (key + message)
        _msg_completa = {"key": key, "message": msg}

        # Áudio / PTT
        if "audioMessage" in msg or "pttMessage" in msg:
            midia_id = key.get("id", "")
            return {"telefone": telefone, "tipo": "audio",
                    "texto": None, "midia_id": midia_id,
                    "mensagem_completa": _msg_completa}

        # Imagem
        if "imageMessage" in msg:
            midia_id = key.get("id", "")
            caption  = msg["imageMessage"].get("caption", "")
            return {"telefone": telefone, "tipo": "imagem",
                    "texto": caption, "midia_id": midia_id,
                    "mensagem_completa": _msg_completa}

        # Documento (PDF, XLSX)
        if "documentMessage" in msg:
            midia_id  = key.get("id", "")
            mime      = msg["documentMessage"].get("mimetype", "")
            caption   = msg["documentMessage"].get("caption", "")
            return {"telefone": telefone, "tipo": "documento",
                    "texto": caption, "midia_id": midia_id, "mime": mime,
                    "mensagem_completa": _msg_completa}

        return None
    except Exception as e:
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        logger.error("[Evolution] Erro ao extrair webhook: %s", safe_msg)
        return None
