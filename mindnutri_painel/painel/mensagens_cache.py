# -*- coding: utf-8 -*-
"""
Cache em memória para mensagens do bot.
Evita bater no banco a cada mensagem de WhatsApp recebida.
"""
import threading
import time

_cache: dict[str, str] | None = None
_cache_ts: float = 0
_lock: threading.Lock = threading.Lock()
CACHE_TTL: int = 300  # 5 minutos


def get_mensagens() -> dict[str, str]:
    """Retorna dict {chave: texto}, com cache de 5 minutos."""
    global _cache, _cache_ts
    with _lock:
        now = time.time()
        if _cache is not None and (now - _cache_ts) < CACHE_TTL:
            return _cache
        from painel.models import MensagemBot
        _cache = MensagemBot.carregar_todas()
        _cache_ts = now
        return _cache


def invalidar_cache() -> None:
    """Invalida cache — chamado quando o admin salva mensagens pelo painel."""
    global _cache
    with _lock:
        _cache = None


def msg(chave: str, **kwargs: str | int | float) -> str:
    """
    Retorna a mensagem formatada.
    Exemplo: msg("menu_principal", nome="João", fichas_rest=28)
    """
    mensagens = get_mensagens()
    template = mensagens.get(chave)
    if template is None:
        # Chave não encontrada — retorna placeholder para debug
        return f"[MSG:{chave}]"
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        # Variável faltando no template editado pelo admin — retorna sem formatar
        return template
