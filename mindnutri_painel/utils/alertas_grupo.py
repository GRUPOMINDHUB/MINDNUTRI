"""
Alertas automáticos para o grupo WhatsApp "SUPORTE - MINDNUTRI".

Envia erros técnicos e alertas de negócio usando o mesmo bot da Evolution API.
O "Ignore Groups" da Evolution API apenas ignora mensagens RECEBIDAS —
o bot continua podendo ENVIAR para grupos via API.

Throttle: máximo 1 alerta a cada 30 segundos (fila para excedentes).
"""
import logging
import threading
import time
from collections import deque
from datetime import datetime

import requests
from django.conf import settings as config

logger = logging.getLogger(__name__)

# ── CONFIGURAÇÃO ─────────────────────────────────────────────────
GRUPO_JID = getattr(config, "WHATSAPP_GRUPO_ALERTAS", "")
_THROTTLE_SEGUNDOS = 30

# ── ESTADO INTERNO ───────────────────────────────────────────────
_ultimo_envio: float = 0.0
_lock = threading.Lock()
_fila: deque[str] = deque(maxlen=50)  # evita crescer infinitamente
_worker_ativo = False


def _enviar_para_grupo(texto: str) -> dict:
    """Envia mensagem de texto para o grupo via Evolution API."""
    if not GRUPO_JID:
        logger.warning("[AlertaGrupo] WHATSAPP_GRUPO_ALERTAS não configurado — alerta descartado")
        return {}

    url = f"{config.EVOLUTION_API_URL}/message/sendText/{config.EVOLUTION_INSTANCE}"
    headers = {
        "apikey": config.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "number": GRUPO_JID,
        "text": texto,
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        logger.info("[AlertaGrupo] Mensagem enviada para o grupo com sucesso")
        return r.json()
    except Exception as e:
        logger.error("[AlertaGrupo] Falha ao enviar para grupo: %s", e)
        return {}


def _processar_fila() -> None:
    """Worker que processa a fila de alertas respeitando o throttle."""
    global _worker_ativo, _ultimo_envio

    while True:
        with _lock:
            if not _fila:
                _worker_ativo = False
                return
            texto = _fila.popleft()

        # Respeitar throttle
        agora = time.monotonic()
        espera = _THROTTLE_SEGUNDOS - (agora - _ultimo_envio)
        if espera > 0:
            time.sleep(espera)

        _enviar_para_grupo(texto)
        _ultimo_envio = time.monotonic()


def _enfileirar(texto: str) -> None:
    """Adiciona alerta na fila e inicia worker se necessário."""
    global _worker_ativo

    with _lock:
        _fila.append(texto)
        if _worker_ativo:
            return
        _worker_ativo = True

    thread = threading.Thread(target=_processar_fila, daemon=True,
                              name="alertas-grupo-worker")
    thread.start()


def _agora_formatado() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


# ── API PÚBLICA ──────────────────────────────────────────────────

def _buscar_nome_assinante(telefone: str) -> str:
    """Busca o nome do assinante no banco de dados pelo telefone."""
    if not telefone:
        return ""
    try:
        from painel.models import Assinante
        assinante = Assinante.objects.filter(telefone=telefone).first()
        if assinante and assinante.nome:
            return assinante.nome
    except Exception:
        pass  # Não deve quebrar o alerta se o banco falhar
    return ""


def alertar_erro(tipo: str, descricao: str, telefone: str = "",
                 estado: str = "") -> None:
    """
    Envia alerta de erro técnico para o grupo.

    Args:
        tipo: Tipo do erro (ex: "Erro OpenAI", "Erro Transcrição Áudio")
        descricao: Descrição do erro (mensagem da exception)
        telefone: Telefone do usuário afetado (opcional)
        estado: Estado atual do fluxo do usuário (opcional)
    """
    # Busca nome do assinante automaticamente
    nome = _buscar_nome_assinante(telefone) if telefone else ""

    partes = [
        "🚨 *Erro no MindNutri*",
        "",
    ]

    if nome:
        partes.append(f"👤 Usuário: {nome}")
    if telefone:
        partes.append(f"📱 Telefone: {telefone}")
    partes.append(f"📋 Tipo: {tipo}")
    if estado:
        partes.append(f"🔄 Estado: {estado}")

    partes += [
        "",
        "📝 *Descrição:*",
        str(descricao)[:500],  # limita tamanho
        "",
        f"🕐 {_agora_formatado()}",
    ]

    texto = "\n".join(partes)
    logger.info("[AlertaGrupo] Enfileirando alerta de erro: %s", tipo)
    _enfileirar(texto)


def alertar_negocio(tipo: str, titulo: str, descricao: str,
                    telefone: str = "", nome: str = "") -> None:
    """
    Envia alerta de negócio para o grupo.

    Args:
        tipo: Categoria (ex: "Inadimplência", "Não Renovação", "Fichas Sub-utilizadas")
        titulo: Título resumido do alerta
        descricao: Descrição detalhada
        telefone: Telefone do assinante
        nome: Nome do assinante
    """
    # Emoji baseado no tipo
    emojis = {
        "inadimplência": "💰",
        "inadimplencia": "💰",
        "não renovação": "🔄",
        "nao renovacao": "🔄",
        "cancelamento": "❌",
        "fichas sub-utilizadas": "📊",
        "fichas subutilizadas": "📊",
        "novo assinante": "🎉",
    }
    emoji = emojis.get(tipo.lower(), "⚠️")

    partes = [
        f"{emoji} *Alerta: {titulo}*",
        "",
    ]

    if nome:
        partes.append(f"👤 Nome: {nome}")
    if telefone:
        partes.append(f"📱 Telefone: {telefone}")

    partes += [
        "",
        "📝 *Descrição:*",
        str(descricao)[:500],
        "",
        f"🕐 {_agora_formatado()}",
    ]

    texto = "\n".join(partes)
    logger.info("[AlertaGrupo] Enfileirando alerta de negócio: %s", tipo)
    _enfileirar(texto)
