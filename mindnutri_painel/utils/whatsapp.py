import requests
import base64
import os
import tempfile
from django.conf import settings as config

HEADERS = {
    "apikey": config.EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}
BASE = f"{config.EVOLUTION_API_URL}/message"
INST = config.EVOLUTION_INSTANCE


def _post(endpoint: str, payload: dict) -> dict:
    url = f"{BASE}/{endpoint}/{INST}"
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        safe_endpoint = str(endpoint).encode('utf-8', 'ignore').decode('utf-8')
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        print(f"[Evolution] Erro em {safe_endpoint}: {safe_msg}")
        return {}


def enviar_texto(telefone: str, texto: str) -> dict:
    """Envia mensagem de texto simples."""
    return _post("sendText", {
        "number": telefone,
        "textMessage": {"text": texto},
    })


def enviar_arquivo(telefone: str, caminho: str, caption: str = "") -> dict:
    """Envia arquivo (PDF ou XLSX) como documento."""
    ext = os.path.splitext(caminho)[1].lower()
    mime_map = {
        ".pdf":  "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
    }
    mimetype = mime_map.get(ext, "application/octet-stream")
    nome_arquivo = os.path.basename(caminho)

    with open(caminho, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    return _post("sendMedia", {
        "number": telefone,
        "mediaMessage": {
            "mediatype": "document",
            "mimetype": mimetype,
            "media": b64,
            "fileName": nome_arquivo,
            "caption": caption,
        }
    })


def enviar_imagem(telefone: str, caminho: str, caption: str = "") -> dict:
    """Envia imagem."""
    with open(caminho, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return _post("sendMedia", {
        "number": telefone,
        "mediaMessage": {
            "mediatype": "image",
            "mimetype": "image/jpeg",
            "media": b64,
            "caption": caption,
        }
    })


def baixar_midia(media_url: str, media_key: str = None) -> bytes | None:
    """Baixa mídia (áudio, imagem, documento) da Evolution API."""
    try:
        # Evolution API endpoint para download de mídia
        url = f"{config.EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{INST}"
        r = requests.post(url, json={"message": {"key": {"id": media_key}}},
                          headers=HEADERS, timeout=30)
        if r.status_code == 200:
            data = r.json()
            b64 = data.get("base64", "")
            if b64:
                return base64.b64decode(b64)
    except Exception as e:
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        print(f"[Evolution] Erro ao baixar m\u00eddia: {safe_msg}")
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

        # Áudio / PTT
        if "audioMessage" in msg or "pttMessage" in msg:
            midia_id = key.get("id", "")
            return {"telefone": telefone, "tipo": "audio",
                    "texto": None, "midia_id": midia_id}

        # Imagem
        if "imageMessage" in msg:
            midia_id = key.get("id", "")
            caption  = msg["imageMessage"].get("caption", "")
            return {"telefone": telefone, "tipo": "imagem",
                    "texto": caption, "midia_id": midia_id}

        # Documento (PDF, XLSX)
        if "documentMessage" in msg:
            midia_id  = key.get("id", "")
            mime      = msg["documentMessage"].get("mimetype", "")
            caption   = msg["documentMessage"].get("caption", "")
            return {"telefone": telefone, "tipo": "documento",
                    "texto": caption, "midia_id": midia_id, "mime": mime}

        return None
    except Exception as e:
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        print(f"[Evolution] Erro ao extrair webhook: {safe_msg}")
        return None
