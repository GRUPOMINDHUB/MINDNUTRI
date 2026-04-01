import json
import logging
import os
import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

import openai
import requests
from django.conf import settings as config

from agente_app.prompt import SYSTEM_PROMPT
from agente_app.gerador import xlsx_gerador, pdf_gerador
from painel.mensagens_cache import msg as _msg
from utils import banco, whatsapp, midia, storage

_gpt = openai.OpenAI(api_key=config.OPENAI_API_KEY)

EXEMPLOS_DIR: Path = Path(__file__).parent.parent / "exemplos"


class _FalhasComTTL:
    """Contador de falhas com expiração automática (evita memory leak)."""
    def __init__(self, ttl: int = 3600):
        self._data: dict[str, tuple[int, float]] = {}
        self._ttl = ttl

    def get(self, key: str, default: int = 0) -> int:
        import time
        entry = self._data.get(key)
        if entry and time.monotonic() - entry[1] < self._ttl:
            return entry[0]
        return default

    def set(self, key: str, value: int) -> None:
        import time
        self._data[key] = (value, time.monotonic())

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


_falhas = _FalhasComTTL(ttl=3600)


def _chamar_openai_com_retry(mensagens, tools, modelo, max_tentativas=3):
    """Chama OpenAI com retry e backoff exponencial para erros transientes."""
    import time as _time
    for tentativa in range(max_tentativas):
        try:
            return _gpt.chat.completions.create(
                model=modelo,
                messages=mensagens,
                tools=tools,
                max_tokens=2000,
                temperature=0.4,
                timeout=60,
            )
        except openai.RateLimitError:
            espera = 2 ** tentativa
            logger.warning("[OpenAI] Rate limit, aguardando %ds (tentativa %d/%d)",
                           espera, tentativa + 1, max_tentativas)
            _time.sleep(espera)
        except openai.APITimeoutError:
            logger.warning("[OpenAI] Timeout (tentativa %d/%d)", tentativa + 1, max_tentativas)
            if tentativa == max_tentativas - 1:
                raise
        except openai.APIConnectionError:
            logger.warning("[OpenAI] Conexão falhou (tentativa %d/%d)", tentativa + 1, max_tentativas)
            _time.sleep(1)
    from utils.alertas_grupo import alertar_erro
    alertar_erro("Erro OpenAI", "Máximo de tentativas OpenAI atingido (rate limit / timeout / conexão)")
    raise openai.APIError("Máximo de tentativas OpenAI atingido")


# ── HELPERS DE DETECÇÃO ───────────────────────────────────────────────────────

_FRASES_ZERO = (
    "comecar do zero", "começar do zero", "recomecar", "recomeçar",
    "reiniciar", "do zero", "start over", "reset", "apagar tudo",
    "quero comecar", "quero começar",
)

def _quer_comecar_do_zero(texto: str) -> bool:
    t = (texto or "").lower().strip()
    return any(f in t for f in _FRASES_ZERO)


_SAUDACOES = (
    "oi", "olá", "ola", "eae", "eai", "e ai", "e aí",
    "bom dia", "boa tarde", "boa noite", "hello", "hi",
    "fala", "salve", "opa", "hey",
)

def _eh_saudacao(texto: str) -> bool:
    t = (texto or "").lower().strip()
    return t in _SAUDACOES or any(t.startswith(s + " ") or t.startswith(s + "!") or t.startswith(s + ",") for s in _SAUDACOES)


# ── DETECÇÃO DE INGREDIENTES MANIPULADOS (no código, não no LLM) ─────────────

_PALAVRAS_MANIPULADO = [
    "desfiado", "desfiada", "moido", "moida", "moído", "moída",
    "cozido", "cozida", "assado", "assada",
    "caramelizado", "caramelizada", "temperado", "temperada",
    "frito", "frita", "refogado", "refogada",
    "confitado", "confitada", "crocante",
    "gratinado", "gratinada", "empanado", "empanada",
    "pure", "purê", "ragu", "ragú", "ragú",
    "tropeiro", "risoto", "molho",
    "creme", "ganache", "brigadeiro", "farofa",
    "caldo", "blend", "chimichurri", "pesto",
    "bechamel", "béchamel", "vinagrete", "guacamole",
    "homus", "hummus", "pate", "patê",
    "massa fresca", "nhoque", "gnocchi",
]

# Palavras que indicam produto industrializado (NÃO manipulado mesmo com "molho"/"creme")
_EXCECOES_INDUSTRIALIZADO = [
    "molho de tomate", "extrato de tomate", "creme de leite",
    "leite condensado", "molho ingles", "molho inglês",
    "molho shoyu", "molho de soja", "molho barbecue",
    "cream cheese", "requeijao", "requeijão",
    "caldo knorr", "caldo maggi", "caldo em cubo", "caldo em po",
]


def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculo."""
    nfkd = unicodedata.normalize('NFKD', texto.lower())
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _detectar_manipulados(texto_usuario: str) -> list[str]:
    """
    Analisa texto do usuário e retorna lista de ingredientes que parecem manipulados.
    Ex: "300g de frango desfiado, 200g de arroz, 100g de purê de batata"
    → ["frango desfiado", "purê de batata"]
    """
    texto_lower = texto_usuario.lower().strip()
    texto_norm = _normalizar(texto_usuario)

    # Primeiro checa se é uma lista de ingredientes (tem números/unidades)
    tem_ingredientes = bool(re.search(r'\d+\s*(g|kg|ml|l|xicara|colher|unidade)', texto_norm))
    if not tem_ingredientes:
        return []

    # Checa exceções industrializadas primeiro
    for exc in _EXCECOES_INDUSTRIALIZADO:
        exc_norm = _normalizar(exc)
        if exc_norm in texto_norm:
            # Remove do texto normalizado pra não pegar "molho" de "molho de tomate"
            texto_norm = texto_norm.replace(exc_norm, "")
            texto_lower = texto_lower.replace(exc.lower(), "")

    # Agora procura palavras de manipulação
    manipulados = []
    for palavra in _PALAVRAS_MANIPULADO:
        palavra_norm = _normalizar(palavra)
        if palavra_norm in texto_norm:
            # Tenta extrair o nome do ingrediente completo ao redor da palavra
            # Procura padrão: "Xg de [ingrediente com palavra]" ou "[ingrediente com palavra]"
            patterns = [
                # "300g de frango desfiado" → captura "frango desfiado"
                rf'\d+\s*(?:g|kg|ml|l)\s+(?:de\s+)?([^,\n]*?{re.escape(palavra)}[^,\n]*)',
                # "frango desfiado 300g" → captura "frango desfiado"
                rf'([^,\n]*?{re.escape(palavra)}[^,\n]*?)\s*\d+\s*(?:g|kg|ml|l)',
                # Qualquer menção
                rf'([^,\n]*?{re.escape(palavra)}[^,\n]*)',
            ]
            for pat in patterns:
                match = re.search(pat, texto_lower, re.IGNORECASE)
                if match:
                    nome = match.group(1).strip().strip('-').strip()
                    # Remove números e unidades do nome
                    nome = re.sub(r'\d+\s*(?:g|kg|ml|l)\s*(?:de\s+)?', '', nome).strip()
                    if nome and nome not in manipulados and len(nome) > 2:
                        manipulados.append(nome)
                    break

    return manipulados


def _iniciar_boas_vindas(telefone: str) -> None:
    # Preserva cupom se já foi aplicado
    estado_atual = banco.get_estado(telefone)
    cupom = _dados_cupom(estado_atual)
    banco.set_estado(telefone, "aguardando_nicho_demo", cupom)
    whatsapp.enviar_texto(telefone, _msg("boas_vindas_inicial"))


def _processar_midia(telefone: str, tipo: str, texto: str | None,
                     midia_bytes: bytes | None, estado_atual: str) -> tuple[str | None, str]:
    """
    Converte mídia (áudio, imagem, documento) em texto processável.
    Retorna (texto_convertido, tipo_convertido). texto_convertido=None indica erro já tratado.
    """
    _ESTADOS_FOTO = ("coletando_foto_preparo", "aguardando_foto_operacional")

    if estado_atual in _ESTADOS_FOTO and tipo == "imagem":
        if not midia_bytes:
            logger.error("[Midia] Imagem recebida mas midia_bytes vazio!")
            whatsapp.enviar_texto(telefone, _msg("foto_nao_salva"))
            return None, tipo
        foto_path = _salvar_foto_prato_operacional(telefone, midia_bytes)
        if not foto_path:
            whatsapp.enviar_texto(telefone, _msg("foto_nao_salva"))
            return None, tipo
        return f"[FOTO_PRATO]{foto_path}", "texto"

    if tipo == "audio" and midia_bytes:
        try:
            texto_transcrito = midia.transcrever_audio(midia_bytes)
        except Exception as e:
            logger.error("[Midia] Falha ao transcrever audio de %s: %s", telefone, e)
            from utils.alertas_grupo import alertar_erro
            alertar_erro("Erro Transcrição Áudio", str(e), telefone=telefone, estado=estado_atual)
            whatsapp.enviar_texto(telefone, _msg("audio_nao_transcrito"))
            return None, tipo
        if not texto_transcrito:
            whatsapp.enviar_texto(telefone, _msg("audio_nao_transcrito"))
            return None, tipo
        return texto_transcrito, tipo

    if tipo == "imagem" and midia_bytes:
        try:
            ingredientes = midia.extrair_ingredientes_de_imagem(midia_bytes)
        except Exception as e:
            logger.error("[Midia] Falha ao extrair ingredientes de imagem de %s: %s", telefone, e)
            from utils.alertas_grupo import alertar_erro
            alertar_erro("Erro Processamento Imagem", str(e), telefone=telefone, estado=estado_atual)
            whatsapp.enviar_texto(
                telefone,
                "Recebi sua imagem, mas não consegui processá-la. "
                "Pode tentar enviar novamente ou descrever por texto?"
            )
            return None, tipo
        return f"[IMAGEM ENVIADA]\nIngredientes identificados na imagem:\n{ingredientes}", tipo

    if tipo == "imagem" and not midia_bytes:
        logger.error("[Midia] Imagem recebida sem bytes para %s", telefone)
        whatsapp.enviar_texto(telefone, _msg("erro_processar_imagem"))
        return None, tipo

    if tipo == "documento" and midia_bytes:
        return "[DOCUMENTO ENVIADO] O cliente enviou um documento para análise.", tipo

    return texto, tipo


def processar_mensagem(telefone: str, tipo: str, texto: str | None = None,
                       midia_id: str | None = None, midia_bytes: bytes | None = None) -> None:
    """Ponto de entrada único para todas as mensagens recebidas."""
    logger.info("[Recebido] telefone=%s tipo=%s texto=%s", telefone, tipo, texto)

    # Feedback imediato: indica que o bot está processando
    whatsapp.enviar_presenca(telefone, "composing")

    estado = banco.get_estado(telefone)
    estado_atual = estado.get("estado", "")

    # ── Expirar estados inativos (>2h) para evitar limbo ────────────
    if estado_atual not in ("inicio", "aguardando_pagamento", ""):
        minutos_inativo = banco.get_tempo_inativo_minutos(telefone)
        if minutos_inativo > 120:
            logger.info("[Estado] Expirando estado antigo para %s: %s (%d min inativo)",
                        telefone, estado_atual, minutos_inativo)
            banco.resetar_estado(telefone)
            estado = {"estado": "inicio", "dados": {}}
            estado_atual = "inicio"

    # ── Processar mídia ──────────────────────────────────────────────
    if tipo != "texto" or (tipo == "imagem" and estado_atual in ("coletando_foto_preparo", "aguardando_foto_operacional")):
        texto, tipo = _processar_midia(telefone, tipo, texto, midia_bytes, estado_atual)
        if texto is None:
            return

    if not texto:
        whatsapp.enviar_texto(telefone, _msg("mensagem_nao_entendida"))
        return

    texto_lower = texto.lower().strip()
    est = estado["estado"]

    # ── Confirmação de reset em andamento ────────────────────────────
    if est == "confirmando_reset":
        if _eh_resposta_sim(texto):
            banco.limpar_historico(telefone)
            # Se é assinante ativo, vai direto pro início de nova ficha
            # (não repete onboarding)
            _assinante_reset = banco.get_assinante(telefone)
            if _assinante_reset and _assinante_reset.get("status") == "ativo":
                banco.set_estado(telefone, "criando_ficha", {})
                msg_nova = "Ficha anterior cancelada! 🍽\n\nQual o nome do novo prato que vamos calcular?"
                whatsapp.enviar_texto(telefone, msg_nova)
                banco.salvar_mensagem(telefone, "assistant", msg_nova)
            else:
                banco.set_estado(telefone, "inicio", {})
                _iniciar_boas_vindas(telefone)
        else:
            dados = estado.get("dados", {})
            banco.set_estado(telefone, dados.get("estado_anterior", "inicio"), dados.get("dados_anteriores", {}))
            whatsapp.enviar_texto(telefone, _msg("continuar_de_onde_parou"))
        return

    # ── Detectar "quero começar do zero" a qualquer momento ──────────
    if _quer_comecar_do_zero(texto) and est not in ("inicio", "confirmando_reset", ""):
        banco.set_estado(telefone, "confirmando_reset", {
            "estado_anterior": est,
            "dados_anteriores": estado.get("dados", {}),
        })
        whatsapp.enviar_texto(telefone, _msg("confirmar_reset"))
        return

    # ── Verificar se já é assinante ──────────────────────────────────
    assinante = banco.get_assinante(telefone)

    if assinante:
        if assinante["status"] == "pendente":
            # Ainda não pagou — continuar no fluxo pré-assinatura
            pass
        elif assinante["status"] in ("bloqueado", "inadimplente"):
            whatsapp.enviar_texto(telefone, _msg("acesso_suspenso"))
            return
        elif assinante["status"] == "cancelado":
            whatsapp.enviar_texto(telefone, _msg("assinatura_cancelada"))
            return
        else:
            _fluxo_assinante_ativo(telefone, texto, texto_lower, estado, assinante)
            return

    # ── Sem assinante: verificar abandono (≥ 60 min) ─────────────────
    if est not in ("inicio", "aguardando_decisao_retorno", ""):
        minutos = banco.get_tempo_inativo_minutos(telefone)
        if minutos >= 60:
            banco.set_estado(telefone, "aguardando_decisao_retorno", {
                "estado_anterior": est,
                "dados_anteriores": estado.get("dados", {}),
            })
            whatsapp.enviar_texto(telefone, _msg("retorno_apos_abandono"))
            return

    if est == "aguardando_decisao_retorno":
        dados = estado.get("dados", {})
        if any(w in texto_lower for w in ("continuar", "continua", "parou", "seguir")):
            banco.set_estado(telefone, dados.get("estado_anterior", "inicio"), dados.get("dados_anteriores", {}))
            whatsapp.enviar_texto(telefone, _msg("retorno_continuando"))
            return
        if any(w in texto_lower for w in ("zero", "comecar", "começar", "novo", "reiniciar")):
            banco.limpar_historico(telefone)
            banco.set_estado(telefone, "inicio", {})
            _iniciar_boas_vindas(telefone)
            return
        whatsapp.enviar_texto(telefone, _msg("retorno_instrucao"))
        return

    # ── Fluxo pré-assinatura ──────────────────────────────────────────
    _fluxo_pre_assinatura(telefone, texto, texto_lower, estado)


# ── FLUXO ASSINANTE ATIVO ─────────────────────────────────────────────────────

def _fluxo_assinante_ativo(telefone: str, texto: str, texto_lower: str,
                            estado: dict, assinante: dict) -> None:
    est = estado["estado"]

    # Comandos de menu
    if texto_lower in ("cancelar", "recomeçar", "reiniciar", "menu", "/menu"):
        banco.resetar_estado(telefone)
        _enviar_menu_principal(telefone, assinante)
        return

    # Fichas disponíveis
    fichas_rest = assinante["fichas_limite_mes"] - assinante["fichas_geradas_mes"]
    if 0 < fichas_rest <= 3:
        dados_est = estado.get("dados", {})
        if not dados_est.get("aviso_limite_enviado"):
            whatsapp.enviar_texto(telefone, _msg("aviso_fichas_poucas", fichas_rest=fichas_rest))
            dados_est["aviso_limite_enviado"] = True
            banco.set_estado(telefone, est, dados_est)

    if fichas_rest <= 0:
        whatsapp.enviar_texto(telefone, _msg("limite_fichas_atingido"))
        banco.set_estado(telefone, "aguardando_renovacao", {})
        return

    if est == "aguardando_renovacao":
        if "sim" in texto_lower:
            _pedir_metodo_pagamento(telefone, "escolha_pagamento_renovacao",
                "Como você prefere fazer a renovação?")
        else:
            banco.resetar_estado(telefone)
            _enviar_menu_principal(telefone, assinante)
        return

    if est == "escolha_pagamento_renovacao":
        metodo = _interpretar_metodo_pagamento(texto)
        if not metodo:
            _pedir_metodo_pagamento(telefone, "escolha_pagamento_renovacao",
                "Não entendi o método de pagamento.")
            return
        _enviar_link_renovacao(telefone, assinante, metodo)
        return

    # Reset no meio de uma ficha: pede confirmação
    ESTADOS_FICHA = (
        "aguardando_confirmacao_geracao", "aguardando_confirmacao_resumo",
        "oferecendo_pdf", "aguardando_decisao_ficha_operacional",
        "coletando_foto_preparo", "aguardando_foto_operacional",
        "aguardando_modo_preparo_operacional",
    )
    if est.startswith("criando_ficha") or est in ESTADOS_FICHA:
        if texto_lower in ("cancelar", "nova ficha", "novo prato", "recomeçar ficha"):
            banco.set_estado(telefone, "confirmando_reset_ficha", {
                "estado_anterior": est,
                "dados_anteriores": estado.get("dados", {}),
            })
            whatsapp.enviar_texto(telefone, _msg("confirmar_cancelar_ficha"))
            return

    if est == "confirmando_reset_ficha":
        if _eh_resposta_sim(texto):
            banco.resetar_estado(telefone)
            _enviar_menu_principal(telefone, assinante)
        else:
            dados = estado.get("dados", {})
            banco.set_estado(telefone, dados.get("estado_anterior", "inicio"), dados.get("dados_anteriores", {}))
            whatsapp.enviar_texto(telefone, _msg("continuando_ficha_atual"))
        return

    if est.startswith("criando_ficha"):
        _conversar_com_ia(telefone, texto, assinante)
        return

    if est == "aguardando_confirmacao_resumo":
        _fluxo_confirmacao_resumo(telefone, texto, estado, assinante)
        return

    if est == "aguardando_confirmacao_geracao":
        _fluxo_confirmacao_geracao(telefone, texto, estado, assinante)
        return

    if est in ("oferecendo_pdf", "aguardando_decisao_ficha_operacional"):
        _fluxo_decisao_ficha_operacional(telefone, texto, estado, assinante)
        return

    if est in ("coletando_foto_preparo", "aguardando_foto_operacional", "aguardando_modo_preparo_operacional"):
        _fluxo_coletando_foto_preparo(telefone, texto, estado, assinante)
        return

    # Saudação ou estado vazio/inicio → menu principal (não delega pro LLM)
    if est in ("inicio", "") or _eh_saudacao(texto_lower):
        banco.set_estado(telefone, "criando_ficha", {})
        _enviar_menu_principal(telefone, assinante)
        return

    _conversar_com_ia(telefone, texto, assinante)

# ── FLUXO PRÉ-ASSINATURA ─────────────────────────────────────────────────────


def _dados_cupom(estado: dict) -> dict:
    """Extrai dados de cupom do estado atual, para preservar entre transições."""
    dados = estado.get("dados", {})
    cupom = {}
    if dados.get("cupom_codigo"):
        cupom["cupom_codigo"] = dados["cupom_codigo"]
    if dados.get("cupom_valor"):
        cupom["cupom_valor"] = dados["cupom_valor"]
    return cupom


def _verificar_cupom(telefone: str, texto: str, estado: dict) -> bool:
    """Verifica se o texto contém um cupom válido. Se sim, salva no estado e avisa o user.
    Se já estiver aguardando pagamento, regenera o link com o valor do cupom."""
    from painel.models import Cupom
    texto_limpo = texto.strip().upper()
    cupom = Cupom.validar(texto_limpo)
    if cupom:
        dados = estado.get("dados", {})
        dados["cupom_codigo"] = cupom.codigo
        dados["cupom_valor"] = float(cupom.valor_primeiro_pagamento)
        banco.set_estado(telefone, estado["estado"], dados)
        whatsapp.enviar_texto(telefone, _msg("cupom_aplicado",
            codigo=cupom.codigo,
            valor=f"{cupom.valor_primeiro_pagamento:.2f}",
            valor_normal=f"{config.PLANO_VALOR:.2f}"))
        logger.info("[Cupom] %s aplicado para %s — R$ %s", cupom.codigo, telefone, cupom.valor_primeiro_pagamento)

        # Se já está aguardando pagamento, regenera o link com o desconto
        if estado["estado"] == "aguardando_pagamento":
            metodo = dados.get("metodo_pagamento", "cartao")
            logger.info("[Cupom] Regenerando link de pagamento com desconto para %s", telefone)
            _iniciar_assinatura(telefone, metodo, dados)

        return True
    return False


def _fluxo_pre_assinatura(telefone: str, texto: str, texto_lower: str, estado: dict) -> None:
    """
    Fluxo completo para quem ainda não assinou:
    boas-vindas → demo por nicho → oferta → coleta dados → pagamento
    """
    est = estado["estado"]

    # Detectar cupom em qualquer estado do onboarding
    if _verificar_cupom(telefone, texto, estado):
        # Se é o primeiro contato, ainda inicia boas-vindas após salvar cupom
        if est in ("inicio", ""):
            _iniciar_boas_vindas(telefone)
        return

    # Primeiro contato ou estado inicial
    if est in ("inicio", ""):
        _iniciar_boas_vindas(telefone)
        return

    # Aguardando escolha de nicho para o exemplo
    if est == "aguardando_nicho_demo":
        _enviar_exemplo_por_nicho(telefone, texto)
        cupom = _dados_cupom(estado)
        banco.set_estado(telefone, "aguardando_interesse", cupom)
        whatsapp.enviar_texto(telefone, _msg("interesse_pos_demo"))
        return

    # Aguardando resposta de interesse após demo
    if est == "aguardando_interesse":
        cupom = _dados_cupom(estado)
        _POSITIVOS = ("sim", "quero", "gostei", "gosti", "gostey", "interessei",
                       "claro", "bora", "vamos", "show", "top", "saber", "mais",
                       "conta", "legal", "massa", "demais", "adorei", "amei",
                       "curti", "curtir", "bacana", "otimo", "ótimo", "dahora",
                       "assinar", "pagar", "contratar", "quero sim")
        _NEGATIVOS = ("nao", "não", "depois", "agora nao", "agora não",
                       "sem interesse", "nao quero", "não quero", "talvez")
        if any(w in texto_lower for w in _POSITIVOS):
            banco.set_estado(telefone, "aguardando_decisao_assinar", cupom)
            whatsapp.enviar_texto(telefone, _msg("oferta_pos_demo", valor=f"{config.PLANO_VALOR:.2f}"))
        elif any(w in texto_lower for w in _NEGATIVOS):
            whatsapp.enviar_texto(telefone, _msg("nao_tem_interesse"))
            banco.set_estado(telefone, "inicio", {})
        else:
            # Não entendeu — assume positivo e mostra oferta (melhor converter do que perder)
            banco.set_estado(telefone, "aguardando_decisao_assinar", cupom)
            whatsapp.enviar_texto(telefone, _msg("oferta_pos_demo", valor=f"{config.PLANO_VALOR:.2f}"))
        return

    # Aguardando decisão de assinar
    if est == "aguardando_decisao_assinar":
        cupom = _dados_cupom(estado)
        if any(w in texto_lower for w in ("assinar", "sim", "quero", "pagar", "contratar")):
            banco.set_estado(telefone, "coletando_dados", cupom)
            _conversar_coleta_dados(telefone, texto, estado)
        else:
            whatsapp.enviar_texto(telefone, _msg("nao_quer_assinar"))
        return

    # Coletando dados via LLM (Nome e Instagram)
    if est == "coletando_dados":
        _conversar_coleta_dados(telefone, texto, estado)
        return

    # Escolha do método de pagamento
    if est == "escolha_pagamento_assinatura":
        metodo = _interpretar_metodo_pagamento(texto)
        if not metodo:
            _pedir_metodo_pagamento(telefone, "escolha_pagamento_assinatura",
                "Não entendi o método. Pode repetir?", dados=estado.get("dados", {}))
            return
        _iniciar_assinatura(telefone, metodo, estado.get("dados", {}))
        return

    # Aguardando confirmação de pagamento
    if est == "aguardando_pagamento":
        metodo_trocado = _interpretar_metodo_pagamento(texto)
        if metodo_trocado:
            whatsapp.enviar_texto(telefone, _msg("troca_metodo_pagamento", metodo=metodo_trocado.upper()))
            _iniciar_assinatura(telefone, metodo_trocado, estado.get("dados", {}))
            return
        if any(c in texto_lower for c in ("mudar", "trocar", "alterar", "outro")):
            _pedir_metodo_pagamento(telefone, "escolha_pagamento_assinatura",
                "Qual método você prefere agora?", dados=estado.get("dados", {}))
            return
        # Reenviar link se pedido
        if any(c in texto_lower for c in ("link", "manda", "enviar", "reenviar", "pagar", "cade", "cadê")):
            metodo_atual = estado.get("dados", {}).get("metodo_pagamento", "cartao")
            _iniciar_assinatura(telefone, metodo_atual, estado.get("dados", {}))
            return
        whatsapp.enviar_texto(telefone, _msg("aguardando_pagamento"))
        return

    # Fallback: reinicia
    _iniciar_boas_vindas(telefone)


def _conversar_coleta_dados(telefone: str, texto: str, estado: dict) -> None:
    """
    Usa LLM para coletar Nome e Instagram de forma conversacional.
    Quando todos os dados estiverem confirmados, avança para pagamento.
    """
    whatsapp.enviar_presenca(telefone, "composing")

    prompt_coleta = _msg("prompt_coleta")

    historico = banco.get_historico(telefone, limite=10)
    banco.salvar_mensagem(telefone, "user", texto)

    mensagens = [{"role": "system", "content": prompt_coleta}] + historico + [{"role": "user", "content": texto}]

    tools = [{
        "type": "function",
        "function": {
            "name": "concluir_coleta_dados",
            "description": "Conclui o cadastro após coletar nome e instagram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome":      {"type": "string"},
                    "instagram": {"type": "string"},
                },
                "required": ["nome", "instagram"],
            },
        },
    }]

    try:
        modelo = getattr(config, "OPENAI_MODEL", "gpt-4.1")
        resposta = _chamar_openai_com_retry(mensagens, tools, modelo)
        message = resposta.choices[0].message

        if message.content and message.content.strip():
            banco.salvar_mensagem(telefone, "assistant", message.content.strip())
            whatsapp.enviar_texto(telefone, message.content.strip())

        if message.tool_calls:
            for tc in message.tool_calls:
                if tc.function.name != "concluir_coleta_dados":
                    continue
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    whatsapp.enviar_texto(telefone, _msg("dados_coleta_erro"))
                    return

                nome      = (args.get("nome") or "").strip()
                instagram = (args.get("instagram") or "").strip()

                if not (nome and instagram):
                    whatsapp.enviar_texto(telefone, _msg("dados_coleta_quase_la"))
                    return

                if instagram.lower() in ("nao", "não", "n", "nenhum", "nao tenho", "não tenho"):
                    instagram = "NAO"
                elif not instagram.startswith("@"):
                    instagram = "@" + instagram.lstrip("@")

                # Salva dados no estado para usar em _iniciar_assinatura
                # Preserva cupom se já foi aplicado durante a coleta
                # Recarrega estado fresh do banco para pegar cupom salvo em mensagem anterior
                estado_atual = banco.get_estado(telefone)
                dados_cadastro = estado_atual.get("dados", {})
                dados_cadastro.update({"nome": nome, "instagram": instagram})
                logger.info("[Coleta] Dados finais: %s", dados_cadastro)
                banco.set_estado(telefone, "escolha_pagamento_assinatura", dados_cadastro)
                banco.salvar_mensagem(telefone, "system", "[Dados coletados]")

                whatsapp.enviar_texto(telefone, _msg("dados_coletados_pagamento", nome=nome))
                return

        if not message.content and not message.tool_calls:
            whatsapp.enviar_texto(telefone, _msg("dados_coleta_vazio"))

    except Exception as e:
        logger.error("[Coleta dados] Erro: %s", e)
        from utils.alertas_grupo import alertar_erro
        alertar_erro("Erro Coleta Dados", str(e), telefone=telefone, estado="coletando_dados")
        whatsapp.enviar_texto(telefone, _msg("dados_coleta_instabilidade"))
def _enviar_exemplo_por_nicho(telefone: str, texto: str) -> None:
    """Envia os arquivos de exemplo para o nicho escolhido."""
    texto_lower = texto.lower()

    if "1" in texto or "hamburguer" in texto_lower or "hambúrguer" in texto_lower or "burger" in texto_lower:
        nicho = "hamburguer"
    elif "2" in texto or "pizza" in texto_lower:
        nicho = "pizza"
    elif "3" in texto or "sobremesa" in texto_lower or "brownie" in texto_lower or "doce" in texto_lower:
        nicho = "sobremesa"
    else:
        nicho = "hamburguer"

    nicho_label = nicho.capitalize()

    whatsapp.enviar_texto(telefone, _msg("exemplo_nicho_intro", nicho_label=nicho_label))

    xlsx_path = EXEMPLOS_DIR / f"exemplo_{nicho}.xlsx"
    pdf_path  = EXEMPLOS_DIR / f"exemplo_{nicho}.pdf"

    enviou_algo = False

    if xlsx_path.exists():
        whatsapp.enviar_arquivo(telefone, str(xlsx_path),
            caption=f"Ficha Técnica — {nicho_label} (XLSX)")
        enviou_algo = True
    else:
        logger.error("Arquivo de exemplo não encontrado: %s", xlsx_path)

    if pdf_path.exists():
        whatsapp.enviar_arquivo(telefone, str(pdf_path),
            caption=f"Ficha Operacional — {nicho_label} (PDF)")
        enviou_algo = True
    else:
        logger.error("Arquivo de exemplo não encontrado: %s", pdf_path)

    if not enviou_algo:
        whatsapp.enviar_texto(telefone, _msg("exemplo_nicho_erro"))


def _interpretar_metodo_pagamento(texto: str) -> str | None:
    texto_lower = _normalizar_texto_pagamento(texto)
    if texto_lower in ("1", "cartao", "cartão", "credito", "crédito", "cartao de credito", "cartão de crédito"):
        return "cartao"
    if texto_lower in ("2", "pix"):
        return "pix"
    if "pix" in texto_lower:
        return "pix"
    if any(chave in texto_lower for chave in ("cartao", "cartão", "credito", "crédito")):
        return "cartao"
    return None


def _normalizar_texto_pagamento(texto: str) -> str:
    """Normaliza texto para aumentar robustez na deteccao do metodo de pagamento."""
    if texto is None:
        return ""

    sem_acentos = unicodedata.normalize("NFKD", str(texto))
    sem_acentos = "".join(ch for ch in sem_acentos if not unicodedata.combining(ch))
    return sem_acentos.lower().strip()


def _pedir_metodo_pagamento(telefone: str, estado_destino: str, abertura: str, dados: dict = None) -> None:
    banco.set_estado(telefone, estado_destino, dados or {})
    whatsapp.enviar_texto(telefone, _msg("pedir_metodo_pagamento", abertura=abertura))


def _iniciar_assinatura(telefone: str, metodo: str, dados_cadastro: dict = None) -> None:
    """Cria o Assinante no banco (se ainda não existir), gera o link de cobrança única e envia ao cliente."""
    logger.info("[Pagamento] Gerando cobranca unica para %s via %s", telefone, metodo)

    # Cria o Assinante APENAS agora (na emissão do link de pagamento)
    dados = dados_cadastro or {}
    from painel.models import Assinante
    assinante_obj, criado = Assinante.objects.get_or_create(
        telefone=telefone,
        defaults={
            "nome":      dados.get("nome", ""),
            "instagram": dados.get("instagram", ""),
            "status":    "pendente",
        }
    )
    # Sempre atualiza nome/instagram (corrige caso get_or_create tenha
    # encontrado assinante existente sem esses dados)
    nome_novo = dados.get("nome", "")
    insta_novo = dados.get("instagram", "")
    if nome_novo and not assinante_obj.nome:
        assinante_obj.nome = nome_novo
    if insta_novo and not assinante_obj.instagram:
        assinante_obj.instagram = insta_novo
    if not criado and (nome_novo or insta_novo):
        assinante_obj.save()
        logger.info("[Pagamento] Assinante %s atualizado: nome=%s instagram=%s", telefone, assinante_obj.nome, assinante_obj.instagram)

    # Verificar se há cupom aplicado
    cupom_codigo = dados.get("cupom_codigo")
    cupom_valor = dados.get("cupom_valor")
    valor_primeiro = float(cupom_valor) if cupom_valor else config.PLANO_VALOR

    if cupom_codigo:
        logger.info("[Cupom] Usando cupom %s — primeiro pagamento R$ %.2f", cupom_codigo, valor_primeiro)

    # Asaas exige mínimo R$ 5 para qualquer cobrança
    if valor_primeiro < 5.0:
        logger.warning("[Pagamento] Valor R$ %.2f abaixo do mínimo Asaas (R$ 5). Ajustando para R$ 5,00.", valor_primeiro)
        valor_primeiro = 5.0

    try:
        if metodo == "cartao":
            from utils.asaas import criar_link_cartao
            pagamento = criar_link_cartao(telefone, valor=valor_primeiro)
            link = pagamento.get("url")
        else:
            from utils.asaas import criar_cobranca_pix
            pagamento = criar_cobranca_pix(
                telefone,
                valor_primeiro,
                f"Mindhub Mindnutri - Plano Mensal via Pix{' (cupom ' + cupom_codigo + ')' if cupom_codigo else ''}",
            )
            link = pagamento.get("invoice_url")
            codigo_pix = pagamento.get("pix_copy_paste", "")

        if not link:
            raise ValueError("Link de pagamento retornado vazio pelo Asaas")

        dados_estado = {"metodo_pagamento": metodo}
        if metodo == "cartao":
            plid = pagamento.get("payment_link_id", "")
            dados_estado["payment_link_id"] = plid
            # Persistir no modelo Assinante (não apenas no estado)
            # para que o webhook encontre mesmo se o estado expirar
            if plid:
                banco.atualizar_assinante(telefone, payment_link_id=plid)
            whatsapp.enviar_texto(telefone, _msg("link_cartao", link=link))
        else:
            dados_estado["payment_id"] = pagamento.get("payment_id", "")
            bloco_pix = f"Código Pix copia e cola:\n{codigo_pix}\n\n" if codigo_pix else ""
            whatsapp.enviar_texto(telefone, _msg("link_pix", link=link, bloco_codigo_pix=bloco_pix))

        # Registrar uso do cupom
        if cupom_codigo:
            from painel.models import Cupom
            cupom_obj = Cupom.validar(cupom_codigo)
            if cupom_obj:
                cupom_obj.usar()
            dados_estado["cupom_codigo"] = cupom_codigo
            dados_estado["cupom_valor"] = cupom_valor

        banco.set_estado(telefone, "aguardando_pagamento", dados_estado)

    except Exception as e:
        logger.error("ERRO ASAAS: %s", e)
        if isinstance(e, requests.exceptions.HTTPError) and hasattr(e, 'response') and e.response is not None:
            logger.error("ASAAS RESPONSE: %s", e.response.text)

        erro_body = e.response.text if isinstance(e, requests.exceptions.HTTPError) and hasattr(e, 'response') and e.response is not None else ""

        from utils.alertas_grupo import alertar_erro
        alertar_erro("Erro Pagamento Asaas", f"Método: {metodo} | {str(e)[:300]}", telefone=telefone, estado="aguardando_pagamento")

        if metodo == "pix" and "Pix" in erro_body:
            whatsapp.enviar_texto(telefone, _msg("pix_nao_habilitado"))
            banco.set_estado(telefone, "escolha_pagamento_assinatura", dados_cadastro or {})
            return

        whatsapp.enviar_texto(telefone, _msg("erro_asaas_generico", gestor_whatsapp=config.GESTOR_WHATSAPP))

        if config.GESTOR_WHATSAPP:
            whatsapp.enviar_texto(config.GESTOR_WHATSAPP, _msg("alerta_gestor_asaas", telefone=telefone, erro=str(e)[:200]))
# â”€â”€ MENU PRINCIPAL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _enviar_menu_principal(telefone: str, assinante: dict) -> None:
    nome = assinante.get("nome") or "cliente"
    fichas_rest = assinante["fichas_limite_mes"] - assinante["fichas_geradas_mes"]
    texto_menu = _msg("menu_principal", nome=nome, fichas_rest=fichas_rest)
    whatsapp.enviar_texto(telefone, texto_menu)
    # Salvar no histórico para o LLM saber que já pediu o nome do prato
    banco.salvar_mensagem(telefone, "assistant", texto_menu)



def _fluxo_confirmacao_resumo(telefone: str, texto: str, estado: dict, assinante: dict) -> None:
    """
    Aguarda 'GERAR' após resumo calculado pelo código.
    Se confirmar → pergunta se quer ficha operacional (PDF).
    Se pedir correção → volta pra IA com contexto.
    """
    texto_lower = (texto or "").strip().lower()
    dados_fluxo = estado.get("dados", {})

    if any(p in texto_lower for p in ("gerar", "gera", "pode gerar", "sim", "ok", "confirma", "👍")):
        # Avança para perguntar sobre PDF operacional
        banco.set_estado(telefone, "aguardando_decisao_ficha_operacional", dados_fluxo)
        whatsapp.enviar_texto(telefone, _msg("pergunta_ficha_operacional"))
        logger.info("[Fluxo] Cliente %s confirmou resumo — perguntando sobre PDF", telefone)
        return

    if any(p in texto_lower for p in ("cancelar", "desistir", "nao", "não")):
        banco.resetar_estado(telefone)
        whatsapp.enviar_texto(telefone, _msg("cancelei_geracao"))
        return

    # Cliente pediu correção — volta pra IA com os dados atuais
    banco.set_estado(telefone, "criando_ficha", dados_fluxo)
    banco.salvar_mensagem(telefone, "assistant", "[Sistema: cliente pediu correção no resumo. Ajuste conforme solicitado e chame gerar_ficha_tecnica novamente quando pronto.]")
    _conversar_com_ia(telefone, texto, assinante)


def _fluxo_confirmacao_geracao(telefone: str, texto: str, estado: dict, assinante: dict) -> None:
    """Aguarda confirmação do cliente para gerar o arquivo."""
    if any(p in texto.lower() for p in ["sim", "gera", "pode", "ok", "yes", "confirma", "👍"]):
        dados = estado.get("dados", {})
        tipo  = dados.get("tipo_geracao", "tecnica")
        _gerar_e_enviar_arquivo(telefone, dados, tipo, assinante)
        banco.resetar_estado(telefone)
    else:
        banco.resetar_estado(telefone)
        whatsapp.enviar_texto(telefone, _msg("cancelei_geracao"))


def _eh_resposta_sim(texto: str) -> bool:
    texto_limpo = (texto or "").lower().strip()
    return any(p in texto_limpo for p in ("sim", "s", "quero", "gera", "ok", "pode", "yes"))


def _eh_resposta_nao(texto: str) -> bool:
    texto_limpo = (texto or "").lower().strip()
    return any(p in texto_limpo for p in ("nao", "não", "n", "agora nao", "agora não", "dispenso"))


def _normalizar_lista_modo_preparo(texto: str) -> list[str]:
    """
    Normaliza texto de modo de preparo em lista de passos.
    Aceita: linhas separadas, numeração, ponto-e-vírgula, ou texto corrido com frases.
    Cada passo lógico completo vira um item.
    """
    # Se é uma lista (da IA), já vem ok
    if isinstance(texto, list):
        return [str(p).strip() for p in texto if str(p).strip()]

    bruto = (texto or "").strip()
    if not bruto:
        return []

    # Separar por quebras de linha
    linhas = [l.strip(" -•\t") for l in bruto.splitlines() if l.strip()]

    # Se veio tudo numa linha só, tentar separar por ponto-e-vírgula ou por sentenças
    if len(linhas) == 1:
        # Tentar ponto-e-vírgula primeiro
        partes_pv = [p.strip() for p in re.split(r";\s*", linhas[0]) if p.strip()]
        if len(partes_pv) > 1:
            linhas = partes_pv
        else:
            # Separar por frases (ponto final seguido de maiúscula ou número)
            partes = re.split(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ\d])", linhas[0])
            if len(partes) > 1:
                linhas = [p.strip() for p in partes if p.strip()]

    if not linhas:
        return []

    passos = []
    for linha in linhas:
        # Ignorar linhas que são apenas números soltos (ex: "2", "3", "4")
        if re.fullmatch(r"\d+\.?\s*", linha):
            continue
        # Remover numeração inicial (1. 2) 3- etc.)
        passo = re.sub(r"^\d+[\)\.\-:\s]+", "", linha).strip()
        if passo:
            # Capitalizar primeira letra
            passo = passo[0].upper() + passo[1:] if len(passo) > 1 else passo.upper()
            passos.append(passo)
    return passos


def _salvar_foto_prato_operacional(telefone: str, midia_bytes: bytes) -> str | None:
    try:
        nome_foto = f"foto_prato_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        caminho = storage.salvar_arquivo(telefone, nome_foto, dados=midia_bytes)
        logger.debug("[Fluxo PDF] Foto salva em: %s", caminho)
        return caminho
    except Exception as e:
        logger.error("[Fluxo PDF] Falha ao salvar foto do prato: %s", e)
        return None


def _formatar_qtd_operacional(valor: float | str, unidade: str) -> str:
    try:
        num = float(valor)
    except (ValueError, TypeError):
        return f"{str(valor or '').strip()} {(unidade or '').strip()}".strip()

    unidade_limpa = (unidade or "").strip().lower()

    # Converter kg → g quando abaixo de 1kg
    if unidade_limpa == "kg" and num < 1:
        num = round(num * 1000)
        unidade_limpa = "g"
    # Converter L → ml quando abaixo de 1L
    elif unidade_limpa in ("l", "litro", "litros") and num < 1:
        num = round(num * 1000)
        unidade_limpa = "ml"

    if isinstance(num, float) and num.is_integer():
        txt = str(int(num))
    else:
        txt = f"{num:.3f}".rstrip("0").rstrip(".") if isinstance(num, float) else str(num)

    return f"{txt}{unidade_limpa}".strip()


def _montar_ingredientes_operacionais(dados: dict) -> list[dict]:
    ingredientes_op = dados.get("ingredientes_op") or []
    if ingredientes_op:
        return ingredientes_op

    ingredientes = dados.get("ingredientes") or []
    resultado = []
    for ing in ingredientes:
        resultado.append(
            {
                "qtd": _formatar_qtd_operacional(ing.get("peso_liquido", ""), ing.get("unidade", "")),
                "nome": str(ing.get("nome", "")).strip(),
            }
        )
    return resultado


def _montar_dados_operacionais(dados_tecnica: dict, foto_path: str = "", modo_preparo: list[str] | None = None) -> dict:
    dados_pdf = dict(dados_tecnica or {})
    dados_pdf["ingredientes_op"] = _montar_ingredientes_operacionais(dados_tecnica or {})
    dados_pdf["modo_preparo"] = modo_preparo or dados_pdf.get("modo_preparo") or []
    dados_pdf["foto_path"] = foto_path or ""
    return dados_pdf


def _montar_resumo_calculado(dados_tecnica: dict) -> str:
    """
    Monta o resumo da ficha com TODOS os cálculos feitos em Python.
    O LLM NUNCA faz contas — este código é a fonte da verdade.
    """
    nome_prato = dados_tecnica.get("nome_prato", "Preparação")
    ingredientes = dados_tecnica.get("ingredientes", [])

    linhas = [f"Resumo da Ficha: {nome_prato}", ""]

    custo_total = 0.0
    for idx, ing in enumerate(ingredientes, 1):
        nome = ing.get("nome", "?")
        pl = float(ing.get("peso_liquido", 0) or 0)
        fc = float(ing.get("fc", 1.0) or 1.0)
        ic = float(ing.get("ic", 1.0) or 1.0)
        cu = float(ing.get("custo_unit", 0) or 0)
        pb = float(ing.get("peso_bruto", 0) or 0)
        unidade = (ing.get("unidade", "kg") or "kg").strip()

        # Calcular peso_bruto se não veio
        if not pb and pl:
            pb = pl * fc

        custo_ing = round(cu * pb, 2)
        custo_total += custo_ing

        # Atualizar o dicionário para garantir consistência na geração
        ing["peso_bruto"] = round(pb, 4)

        # Formatar linha do resumo
        if "(subficha)" in nome.lower() or ing.get("subficha"):
            linhas.append(f"{idx}. {nome} (subficha): {pb:.3f}{unidade} x R$ {cu:.2f}/{unidade} = R$ {custo_ing:.2f}")
        elif fc > 1.01:
            linhas.append(f"{idx}. {nome}: {pl:.3f}{unidade} x FC {fc:.2f} = {pb:.3f}{unidade} x R$ {cu:.2f}/{unidade} = R$ {custo_ing:.2f}")
        elif ic > 1.01:
            peso_cozido = pl * ic
            linhas.append(f"{idx}. {nome}: {pl:.3f}{unidade} cru (rende {peso_cozido:.3f}{unidade} cozido) x R$ {cu:.2f}/{unidade} = R$ {custo_ing:.2f}")
        else:
            linhas.append(f"{idx}. {nome}: {pb:.3f}{unidade} x R$ {cu:.2f}/{unidade} = R$ {custo_ing:.2f}")

    custo_total = round(custo_total, 2)

    # Porções
    rendimento_porcoes = dados_tecnica.get("rendimento_porcoes")
    peso_porcao = float(dados_tecnica.get("peso_porcao_kg", 0) or 0)

    linhas.append("")
    linhas.append(f"Custo Total: R$ {custo_total:.2f}")

    if rendimento_porcoes and float(rendimento_porcoes) > 0:
        n_porcoes = float(rendimento_porcoes)
        custo_porcao = round(custo_total / n_porcoes, 2)
        linhas.append(f"Porcoes: {n_porcoes:.0f} | Custo por Porcao: R$ {custo_porcao:.2f}")
    elif peso_porcao > 0:
        # Calcular rendimento a partir da soma dos ingredientes
        rend_total = sum(
            float(i.get("peso_liquido", 0) or 0) * float(i.get("ic", 1.0) or 1.0)
            for i in ingredientes
        )
        if rend_total > 0:
            n_porcoes = rend_total / peso_porcao
            custo_porcao = round(custo_total / n_porcoes, 2)
            linhas.append(f"Porcoes: {n_porcoes:.0f} | Custo por Porcao: R$ {custo_porcao:.2f}")

    linhas.append("")
    linhas.append('Tudo certo? Digite "GERAR" para receber seu PDF e Excel.')
    linhas.append('⚠️ Atenção: Ao digitar "GERAR" você gastará 1 ficha do seu saldo e a ação não poderá ser desfeita.')
    linhas.append('Se algo estiver errado, me diga o que corrigir antes de gerar.')

    return "\n".join(linhas)


def _iniciar_fluxo_pos_coleta_tecnica(telefone: str, dados_tecnica: dict) -> None:
    """
    Dados coletados pela IA. Monta resumo calculado por código (não pelo LLM)
    e aguarda confirmação do cliente.
    """
    # Gera o resumo com cálculos feitos em Python
    resumo = _montar_resumo_calculado(dados_tecnica)

    dados_fluxo = {
        "tecnica_dados": dados_tecnica,
        "modo_preparo": dados_tecnica.get("modo_preparo", []),
        "foto_path": "",
    }
    banco.set_estado(telefone, "aguardando_confirmacao_resumo", dados_fluxo)
    whatsapp.enviar_texto(telefone, resumo)
    logger.info("[Fluxo] Resumo calculado enviado para %s — aguardando GERAR", telefone)


def _finalizar_fluxo_geracao_integrada(telefone: str, fluxo: dict, assinante: dict) -> None:
    """
    Gera os arquivos finais:
    - gerar_operacional=True  → combo (XLSX + PDF juntos)
    - gerar_operacional=False → só XLSX
    """
    dados_tecnica = dict(fluxo.get("tecnica_dados") or {})
    gerar_operacional = bool(fluxo.get("gerar_operacional"))

    if gerar_operacional:
        # Combo: gera XLSX + PDF juntos
        dados_combo = _montar_dados_operacionais(
            dados_tecnica,
            foto_path=fluxo.get("foto_path", ""),
            modo_preparo=fluxo.get("modo_preparo") or dados_tecnica.get("modo_preparo", []),
        )
        logger.info("[Fluxo] Gerando combo XLSX+PDF para %s", telefone)
        _gerar_e_enviar_arquivo(telefone, dados_combo, "combo", assinante)
    else:
        # Só Excel
        logger.info("[Fluxo] Gerando somente XLSX para %s", telefone)
        _gerar_e_enviar_arquivo(telefone, dados_tecnica, "tecnica", assinante)

    banco.resetar_estado(telefone)


def _avancar_coleta_operacional(telefone: str, fluxo: dict, assinante: dict) -> None:
    foto_path = (fluxo.get("foto_path") or "").strip()
    modo_preparo = fluxo.get("modo_preparo") or fluxo.get("tecnica_dados", {}).get("modo_preparo", [])

    if not foto_path:
        banco.set_estado(telefone, "aguardando_foto_operacional", fluxo)
        whatsapp.enviar_texto(telefone, _msg("aguardando_foto"))
        logger.debug("[Fluxo PDF] Aguardando foto do prato de %s", telefone)
        return

    if not modo_preparo:
        banco.set_estado(telefone, "aguardando_modo_preparo_operacional", fluxo)
        whatsapp.enviar_texto(telefone, _msg("aguardando_modo_preparo"))
        logger.debug("[Fluxo PDF] Aguardando modo de preparo de %s", telefone)
        return

    # Garantir que modo_preparo esteja no nível correto do fluxo
    fluxo["modo_preparo"] = modo_preparo
    _finalizar_fluxo_geracao_integrada(telefone, fluxo, assinante)


def _fluxo_decisao_ficha_operacional(telefone: str, texto: str, estado: dict, assinante: dict) -> None:
    fluxo = estado.get("dados", {})

    if _eh_resposta_sim(texto):
        fluxo["gerar_operacional"] = True
        fluxo["modo_preparo"] = fluxo.get("modo_preparo") or fluxo.get("tecnica_dados", {}).get("modo_preparo", [])
        banco.set_estado(telefone, "aguardando_decisao_ficha_operacional", fluxo)
        logger.info("[Fluxo PDF] Cliente %s optou por gerar PDF operacional.", telefone)
        _avancar_coleta_operacional(telefone, fluxo, assinante)
        return

    if _eh_resposta_nao(texto):
        fluxo["gerar_operacional"] = False
        whatsapp.enviar_texto(telefone, _msg("somente_tecnica"))
        logger.info("[Fluxo PDF] Cliente %s optou por gerar somente tecnica.", telefone)
        _finalizar_fluxo_geracao_integrada(telefone, fluxo, assinante)
        return

    whatsapp.enviar_texto(telefone, _msg("confirmar_sim_nao_pdf"))


def _fluxo_coletando_foto_preparo(telefone: str, texto: str, estado: dict, assinante: dict) -> None:
    """
    Compatibilidade de estado:
    - aceita foto ou texto na mesma etapa;
    - redireciona para os fluxos legados de foto/modo de preparo.
    """
    estado_atual = estado.get("estado", "")
    texto_limpo = (texto or "").strip()
    texto_lower = texto_limpo.lower()

    if estado_atual == "aguardando_modo_preparo_operacional":
        _fluxo_coleta_modo_preparo_operacional(telefone, texto, estado, assinante)
        return

    if texto_limpo.startswith("[FOTO_PRATO]") or any(
        p in texto_lower for p in ("sem foto", "pular foto", "nao tenho foto", "não tenho foto")
    ):
        _fluxo_coleta_foto_operacional(telefone, texto, estado, assinante)
        return

    if _normalizar_lista_modo_preparo(texto):
        _fluxo_coleta_modo_preparo_operacional(telefone, texto, estado, assinante)
        return

    _fluxo_coleta_foto_operacional(telefone, texto, estado, assinante)


def _fluxo_coleta_foto_operacional(telefone: str, texto: str, estado: dict, assinante: dict) -> None:
    fluxo = estado.get("dados", {})
    texto_limpo = (texto or "").strip()

    if texto_limpo.startswith("[FOTO_PRATO]"):
        fluxo["foto_path"] = texto_limpo.replace("[FOTO_PRATO]", "", 1).strip()
        banco.set_estado(telefone, "aguardando_foto_operacional", fluxo)
        whatsapp.enviar_texto(telefone, _msg("foto_recebida"))
        _avancar_coleta_operacional(telefone, fluxo, assinante)
        return

    if any(p in texto_limpo.lower() for p in ("sem foto", "pular foto", "nao tenho foto", "não tenho foto")):
        fluxo["foto_path"] = ""
        whatsapp.enviar_texto(telefone, _msg("sem_foto_seguir"))
        # Se já tem modo_preparo (vindo da ficha técnica), gera direto
        modo_preparo = fluxo.get("modo_preparo") or fluxo.get("tecnica_dados", {}).get("modo_preparo", [])
        if modo_preparo:
            fluxo["modo_preparo"] = modo_preparo
            _finalizar_fluxo_geracao_integrada(telefone, fluxo, assinante)
        else:
            banco.set_estado(telefone, "aguardando_modo_preparo_operacional", fluxo)
            whatsapp.enviar_texto(telefone, _msg("aguardando_modo_preparo"))
        return

    whatsapp.enviar_texto(telefone, _msg("foto_ainda_necessaria"))


def _reescrever_modo_preparo(passos_brutos: list[str], nome_prato: str = "") -> list[str]:
    """Usa o LLM para reescrever o modo de preparo de forma profissional e clara."""
    texto_bruto = "\n".join(passos_brutos)
    try:
        from painel.models import ConfiguracaoIA
        _cfg = ConfiguracaoIA.get_config()
        modelo = _cfg.modelo_ia or "gpt-4.1"

        resp = _gpt.chat.completions.create(
            model=modelo,
            max_tokens=1000,
            temperature=0.3,
            timeout=30,
            messages=[
                {"role": "system", "content": (
                    "Voce e um editor de fichas tecnicas de cozinha profissional. "
                    "Reescreva o modo de preparo abaixo em passos claros, objetivos e profissionais. "
                    "Regras:\n"
                    "- Cada passo deve ser UMA acao clara e completa\n"
                    "- Remova numeracoes, o sistema numera automaticamente\n"
                    "- Use linguagem profissional de cozinha (ex: 'Incorpore', 'Reserve', 'Leve ao forno')\n"
                    "- Mantenha tempos e temperaturas exatos como informados\n"
                    "- Nao invente passos nem altere a receita\n"
                    "- Retorne APENAS os passos, um por linha, sem numeros nem marcadores\n"
                    "- Maximo 10 passos (agrupe se necessario)"
                )},
                {"role": "user", "content": f"Prato: {nome_prato}\n\nModo de preparo bruto:\n{texto_bruto}"}
            ]
        )
        texto_limpo = resp.choices[0].message.content or ""
        passos_reescritos = _normalizar_lista_modo_preparo(texto_limpo)
        if passos_reescritos:
            logger.info("[Preparo] Modo de preparo reescrito: %d passos brutos → %d passos limpos",
                        len(passos_brutos), len(passos_reescritos))
            return passos_reescritos
    except Exception as e:
        logger.warning("[Preparo] Falha ao reescrever modo de preparo: %s — usando bruto", e)

    return passos_brutos


def _fluxo_coleta_modo_preparo_operacional(telefone: str, texto: str, estado: dict, assinante: dict) -> None:
    fluxo = estado.get("dados", {})
    passos = _normalizar_lista_modo_preparo(texto)

    if not passos:
        whatsapp.enviar_texto(telefone, _msg("modo_preparo_nao_identificado"))
        return

    # Reescreve o modo de preparo de forma profissional via LLM
    nome_prato = fluxo.get("tecnica_dados", {}).get("nome_prato", "")
    passos = _reescrever_modo_preparo(passos, nome_prato)

    fluxo["modo_preparo"] = passos
    banco.set_estado(telefone, "aguardando_modo_preparo_operacional", fluxo)
    logger.debug("[Fluxo PDF] Modo de preparo recebido (%s passos) para %s", len(passos), telefone)
    _finalizar_fluxo_geracao_integrada(telefone, fluxo, assinante)


# â”€â”€ CONVERSA COM IA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _conversar_com_ia(telefone: str, texto: str, assinante: dict) -> None:
    """
    Envia mensagem para a IA com todo o contexto e retorna resposta.
    Detecta quando a IA quer gerar um arquivo.
    """
    # Indica "digitando..." enquanto a IA processa
    whatsapp.enviar_presenca(telefone, "composing")

    # Salva mensagem do usuÃ¡rio
    banco.salvar_mensagem(telefone, "user", texto)

    # Monta histÃ³rico
    historico = banco.get_historico(telefone, limite=20)

    # Contexto do assinante
    ingredientes_cadastrados = banco.get_ingredientes(telefone)
    nomes_ing = [i["nome"] for i in ingredientes_cadastrados[:30]]
    fichas_rest = assinante["fichas_limite_mes"] - assinante["fichas_geradas_mes"]

    # Carregar base de perdas para injetar no contexto da IA
    from painel.models import PerdaIngrediente
    try:
        perdas_list = PerdaIngrediente.carregar_todas()
        perdas_com_valor = [p for p in perdas_list if p["perda_percentual"] != 0]
        perdas_texto = "\n".join(
            f"- {p['nome']}: {'perde ' + str(p['perda_percentual']) + '%' if p['perda_percentual'] > 0 else 'ganha ' + str(abs(p['perda_percentual'])) + '% (absorve agua)'} ({p['tipo_perda']})"
            for p in perdas_com_valor
        )
    except Exception as e:
        logger.warning("[IA] Falha ao carregar base de perdas: %s", e)
        perdas_texto = ""

    # Carregar subfichas já calculadas do estado
    estado_atual = banco.get_estado(telefone)
    dados_estado = estado_atual.get("dados", {})
    subfichas_calculadas = dados_estado.get("subfichas_calculadas", {})
    if subfichas_calculadas:
        subfichas_texto = "\n".join(
            f"- {nome}: R$ {info['custo_por_kg']:.2f}/kg (rendimento {info['rendimento_kg']:.2f}kg, custo total R$ {info['custo_total']:.2f})"
            for nome, info in subfichas_calculadas.items()
        )
    else:
        subfichas_texto = ""

    nome_prato_atual = dados_estado.get("nome_prato", "")

    # Monta contexto enxuto — perdas só quando necessário
    partes_contexto = [f"""CONTEXTO DO CLIENTE:
- Nome: {assinante.get('nome', 'nao informado')}
- Estabelecimento: {assinante.get('estabelecimento', 'nao informado')}
- Nicho: {assinante.get('nicho', 'nao informado')}
- Cidade: {assinante.get('cidade', 'nao informado')}
- Fichas restantes este mes: {fichas_rest}

- Ingredientes ja usados em fichas anteriores (SEM preco salvo — SEMPRE peca o preco de novo): {', '.join(nomes_ing) if nomes_ing else 'nenhum ainda'}"""]

    if nome_prato_atual:
        partes_contexto.append(f"- Prato atual: {nome_prato_atual}")

    if subfichas_texto:
        partes_contexto.append(f"""
SUBFICHAS JA CALCULADAS (use estes custos por kg na ficha principal — NAO recalcule, NAO pergunte de novo):
{subfichas_texto}
IMPORTANTE: Estes ingredientes JA TEM custo definido. Use o custo_unit acima direto na ficha. FC=1.0, sem perda.""")

    # Só injeta perdas se já tem nome do prato (está coletando ingredientes ou além)
    if nome_prato_atual and perdas_texto:
        partes_contexto.append(f"""
BASE DE PERDAS PADRAO (use como referencia ao perguntar sobre perdas):
{perdas_texto}""")

    contexto_extra = "\n".join(partes_contexto)

    from painel.models import ConfiguracaoIA
    _cfg = ConfiguracaoIA.get_config()
    _sys_prompt = _cfg.get_system_prompt() or SYSTEM_PROMPT
    system_com_contexto = _sys_prompt + "\n\n" + contexto_extra

    # Prepara mensagens para OpenAI (System prompt embutido no histÃ³rico)
    mensagens_openai = [{"role": "system", "content": system_com_contexto}] + historico

    # ── DETECÇÃO AUTOMÁTICA DE MANIPULADOS (código Python, não LLM) ──
    # Analisa a mensagem atual do usuário. Se contém ingredientes manipulados,
    # injeta instrução EXPLÍCITA pro LLM perguntar "faz em casa ou compra pronto?"
    manipulados_detectados = _detectar_manipulados(texto)
    if manipulados_detectados:
        lista_manip = ", ".join(manipulados_detectados)
        instrucao_manipulados = (
            f"[INSTRUCAO DO SISTEMA — PRIORIDADE MAXIMA]\n"
            f"O sistema detectou que os seguintes ingredientes sao MANIPULADOS/PRE-PREPARADOS: {lista_manip}\n"
            f"Voce DEVE perguntar para CADA um deles: \"Esse [nome] voce faz ai na casa ou compra pronto?\"\n"
            f"NAO peca preco desses ingredientes ANTES de saber se o cliente faz em casa ou compra pronto.\n"
            f"Se faz em casa → inicie SUBFICHA (Bloco 2.5).\n"
            f"Se compra pronto → ai sim peca o preco.\n"
            f"Para os DEMAIS ingredientes que NAO estao nesta lista, peca o preco normalmente."
        )
        # Insere como mensagem de sistema logo antes da última mensagem do usuário
        mensagens_openai.insert(-1, {"role": "system", "content": instrucao_manipulados})
        logger.info("[Manipulados] Detectados para %s: %s", telefone, lista_manip)

    try:
        # Detecta se deve gerar arquivo via ferramenta (formato OpenAI)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "gerar_ficha_tecnica",
                    "description": "Gera ficha tecnica. Passe todos os ingredientes com custo_unit, peso_liquido, FC e IC.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nome_prato":        {"type": "string"},
                            "classificacao":     {"type": "string"},
                            "codigo":            {"type": "string"},
                            "peso_porcao_kg":    {"type": "number"},
                            "rendimento_porcoes": {"type": "number"},
                            "ingredientes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "nome":         {"type": "string"},
                                        "unidade":      {"type": "string"},
                                        "peso_bruto":   {"type": "number"},
                                        "peso_liquido": {"type": "number"},
                                        "fc":           {"type": "number"},
                                        "ic":           {"type": "number"},
                                        "custo_unit":   {"type": "number"},
                                    },
                                    "required": ["nome", "unidade", "peso_liquido", "fc", "ic", "custo_unit"]
                                }
                            },
                            "modo_preparo": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["nome_prato", "classificacao", "ingredientes"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "definir_prato",
                    "description": "Salva o nome do prato. Chame ao receber o nome.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nome_prato": {"type": "string", "description": "Nome do prato informado pelo cliente"},
                        },
                        "required": ["nome_prato"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calcular_subficha",
                    "description": "Calcula custo/kg de um pre-preparo. Passe ingredientes (nome, peso_kg, custo_unit) e rendimento_kg.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nome_subficha": {"type": "string", "description": "Nome do pre-preparo (ex: Massa de Empada)"},
                            "ingredientes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "nome":       {"type": "string"},
                                        "peso_kg":    {"type": "number", "description": "Quantidade usada em KG"},
                                        "custo_unit": {"type": "number", "description": "Preco por KG (R$/kg)"},
                                    },
                                    "required": ["nome", "peso_kg", "custo_unit"]
                                }
                            },
                            "rendimento_kg": {"type": "number", "description": "Quanto a receita rende em KG"},
                        },
                        "required": ["nome_subficha", "ingredientes", "rendimento_kg"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "salvar_ingredientes",
                    "description": "Salva ingredientes na base do cliente (apenas nome, unidade, FC e IC — SEM custo).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ingredientes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "nome":    {"type": "string"},
                                        "unidade": {"type": "string"},
                                        "fc":      {"type": "number"},
                                        "ic":      {"type": "number"},
                                    },
                                    "required": ["nome", "unidade"]
                                }
                            }
                        },
                        "required": ["ingredientes"]
                    }
                }
            }
        ]

        # ConfiguraÃ§Ã£o do modelo caso nÃ£o tenha sido migrada
        modelo_escolhido = _cfg.modelo_ia or getattr(config, 'OPENAI_MODEL', 'gpt-4.1')

        resposta = _chamar_openai_com_retry(mensagens_openai, tools, modelo_escolhido)

        message = resposta.choices[0].message

        # Processa resposta textual e tools (se houver)
        texto_resposta = message.content or ""
        tool_calls = message.tool_calls

        # Limpa JSON de tool calls que o modelo às vezes despeja no content
        if tool_calls and texto_resposta:
            texto_resposta = re.sub(
                r'\{[\s\n]*"tool_uses"[\s\S]*?\}\s*$', '', texto_resposta
            ).strip()
            texto_resposta = re.sub(
                r'\{[\s\n]*"recipient_name"[\s\S]*?\}\s*$', '', texto_resposta
            ).strip()

        # Reseta contador de falhas
        _falhas.delete(telefone)

        # Processa tool use
        if tool_calls:
            # Salvar no histÃ³rico que a aÃ§Ã£o foi tomada para a IA nÃ£o repetir infinitamente
            msg_salvar = texto_resposta if texto_resposta else "[Tool executada]"
            banco.salvar_mensagem(telefone, "assistant", msg_salvar)
            texto_enviado = False

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                
                # A OpenAI retorna os argumentos em formato string JSON
                try:
                    tool_input = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    logger.error("Erro ao decodificar argumentos da função %s", tool_name)
                    continue

                if tool_name == "definir_prato":
                    nome_prato = tool_input.get("nome_prato", "")
                    estado_at = banco.get_estado(telefone)
                    dados_at = estado_at.get("dados", {})
                    dados_at["nome_prato"] = nome_prato
                    banco.set_estado(telefone, estado_at["estado"], dados_at)
                    logger.info("[Agente] Nome do prato salvo: %s", nome_prato)
                    # Envia o texto do LLM ou fallback pedindo ingredientes
                    if texto_resposta and not texto_enviado:
                        whatsapp.enviar_texto(telefone, texto_resposta)
                        banco.salvar_mensagem(telefone, "assistant", texto_resposta)
                        texto_enviado = True
                    elif not texto_enviado:
                        msg_fallback = (
                            f"Otimo! Vamos montar a ficha do {nome_prato} 🍽\n\n"
                            "Me mande os ingredientes com as quantidades usadas no prato e quantas porcoes rende.\n\n"
                            "Exemplo: 300g de frango, 100g de arroz, 200ml de leite - rende 1 porcao"
                        )
                        whatsapp.enviar_texto(telefone, msg_fallback)
                        banco.salvar_mensagem(telefone, "assistant", msg_fallback)
                        texto_enviado = True
                    continue

                elif tool_name == "gerar_ficha_tecnica":
                    tool_input["estabelecimento"] = assinante.get("estabelecimento", "")
                    _iniciar_fluxo_pos_coleta_tecnica(telefone, tool_input)
                    continue

                elif tool_name == "gerar_ficha_operacional":
                    # GUARD: IA nao deve chamar esta tool diretamente.
                    # Redireciona para o fluxo correto via gerar_ficha_tecnica.
                    logger.warning("[Agente] IA chamou gerar_ficha_operacional diretamente — ignorando. O fluxo correto é via gerar_ficha_tecnica → estado aguardando_decisao_ficha_operacional.")
                    continue

                elif tool_name == "calcular_subficha":
                    resultado = _calcular_subficha_python(tool_input)
                    _salvar_subficha_no_estado(telefone, tool_input, resultado)
                    # Envia resultado ao usuário
                    whatsapp.enviar_texto(telefone, resultado["mensagem"])
                    banco.salvar_mensagem(telefone, "assistant", resultado["mensagem"])
                    # Sempre envia confirmação pós-subficha (não depende do LLM)
                    nome_sub = tool_input.get("nome_subficha", "pre-preparo")
                    estado_pos = banco.get_estado(telefone)
                    dados_pos = estado_pos.get("dados", {})
                    subfichas_pendentes = []
                    nome_prato_ctx = dados_pos.get("nome_prato", "prato principal")
                    # Verifica se há mais subfichas pendentes no histórico
                    # (o LLM pode ter mencionado outros pré-preparos)
                    todas_subfichas = dados_pos.get("subfichas_calculadas", {})
                    msg_confirmacao = f"Seu {nome_sub} ficou a R$ {resultado['custo_por_kg']:.2f}/kg. Esta certo ou quer ajustar algo?\n\nSe estiver ok, podemos continuar com o {nome_prato_ctx}!"
                    whatsapp.enviar_texto(telefone, msg_confirmacao)
                    banco.salvar_mensagem(telefone, "assistant", msg_confirmacao)
                    texto_enviado = True
                    continue

                elif tool_name == "salvar_ingredientes":
                    for ing in tool_input.get("ingredientes", []):
                        banco.salvar_ingrediente(
                            telefone,
                            ing["nome"],
                            ing.get("unidade", "kg"),
                            ing.get("fc", 1.0),
                            ing.get("ic", 1.0),
                        )
                    if texto_resposta and not texto_enviado:
                        whatsapp.enviar_texto(telefone, texto_resposta)
                        texto_enviado = True
                    if not texto_resposta:
                        banco.salvar_mensagem(telefone, "assistant", "[Ingredientes salvos na base do cliente]")

            return

        # Resposta de texto normal (sem tools)
        if texto_resposta:
            # Detecta se o modelo despejou JSON de tool call no texto (fallback)
            tool_json_match = re.search(
                r'\{\s*"tool_uses"\s*:\s*\[[\s\S]*?\]\s*\}', texto_resposta
            )
            if tool_json_match:
                try:
                    tool_data = json.loads(tool_json_match.group())
                    texto_limpo = texto_resposta[:tool_json_match.start()].strip()
                    for tool_use in tool_data.get("tool_uses", []):
                        func_name = tool_use.get("recipient_name", "").replace("functions.", "")
                        params = tool_use.get("parameters", {})
                        if func_name == "calcular_subficha":
                            resultado = _calcular_subficha_python(params)
                            _salvar_subficha_no_estado(telefone, params, resultado)
                            whatsapp.enviar_texto(telefone, resultado["mensagem"])
                            banco.salvar_mensagem(telefone, "assistant", resultado["mensagem"])
                            # Confirmação pós-subficha
                            nome_sub = params.get("nome_subficha", "pre-preparo")
                            estado_fb = banco.get_estado(telefone)
                            nome_prato_fb = estado_fb.get("dados", {}).get("nome_prato", "prato principal")
                            msg_conf = f"Seu {nome_sub} ficou a R$ {resultado['custo_por_kg']:.2f}/kg. Esta certo ou quer ajustar algo?\n\nSe estiver ok, podemos continuar com o {nome_prato_fb}!"
                            whatsapp.enviar_texto(telefone, msg_conf)
                            banco.salvar_mensagem(telefone, "assistant", msg_conf)
                            logger.warning("[Agente] Tool call extraída do texto (fallback): %s", func_name)
                        elif func_name == "gerar_ficha_tecnica":
                            params["estabelecimento"] = assinante.get("estabelecimento", "")
                            if texto_limpo:
                                banco.salvar_mensagem(telefone, "assistant", texto_limpo)
                            _iniciar_fluxo_pos_coleta_tecnica(telefone, params)
                            logger.warning("[Agente] Tool call extraída do texto (fallback): %s", func_name)
                        else:
                            logger.warning("[Agente] Tool desconhecida no texto: %s", func_name)
                            banco.salvar_mensagem(telefone, "assistant", texto_resposta)
                            whatsapp.enviar_texto(telefone, texto_resposta)
                except (json.JSONDecodeError, KeyError) as parse_err:
                    logger.error("[Agente] Falha ao parsear tool JSON do texto: %s", parse_err)
                    banco.salvar_mensagem(telefone, "assistant", texto_resposta)
                    whatsapp.enviar_texto(telefone, texto_resposta)
            else:
                banco.salvar_mensagem(telefone, "assistant", texto_resposta)
                whatsapp.enviar_texto(telefone, texto_resposta)
        else:
            # Safety net: LLM retornou resposta completamente vazia
            logger.warning("[Agente] LLM retornou resposta vazia (sem texto e sem tools) para %s", telefone)
            msg_vazia = "Desculpa, pode repetir? Nao entendi bem o que voce precisa."
            whatsapp.enviar_texto(telefone, msg_vazia)
            banco.salvar_mensagem(telefone, "assistant", msg_vazia)

    except Exception as e:
        safe_msg = repr(e).encode('utf-8', 'ignore').decode('utf-8')
        logger.error("[OpenAI] Erro: %s", safe_msg)
        from utils.alertas_grupo import alertar_erro
        alertar_erro("Erro OpenAI", safe_msg, telefone=telefone, estado="criando_ficha")
        _registrar_falha(telefone, assinante)


# â”€â”€ GERAÃ‡ÃƒO E ENVIO DE ARQUIVOS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _gerar_e_enviar_arquivo(telefone: str, dados: dict, tipo: str, assinante: dict) -> None:
    """Gera e envia arquivo(s). Se tipo='combo', gera XLSX+PDF com um unico consumo de credito."""
    nome_prato = dados.get("nome_prato", "preparo")
    nome_prato_limpo = str(nome_prato).strip()

    try:
        if tipo == "combo":
            whatsapp.enviar_texto(telefone, _msg("gerando_combo", nome_prato=nome_prato_limpo))
        else:
            whatsapp.enviar_texto(telefone, _msg("gerando_ficha", nome_prato=nome_prato_limpo))

        cobrar_credito = _deve_consumir_credito_por_prato(telefone, nome_prato_limpo)
        logger.debug("[Credito] prato=%s cobrar_credito=%s tipo=%s", nome_prato_limpo, cobrar_credito, tipo)

        if tipo == "combo":
            caminho_tecnica = _gerar_enviar_registrar_arquivo(
                telefone=telefone,
                dados=dados,
                tipo_arquivo="tecnica",
                nome_prato=nome_prato_limpo,
            )
            dados_operacional = _montar_dados_operacionais(
                dados,
                foto_path=dados.get("foto_path", ""),
                modo_preparo=dados.get("modo_preparo", []),
            )
            caminho_operacional = _gerar_enviar_registrar_arquivo(
                telefone=telefone,
                dados=dados_operacional,
                tipo_arquivo="operacional",
                nome_prato=nome_prato_limpo,
            )
            logger.info("[Gerador] Combo concluido: tecnica=%s operacional=%s", caminho_tecnica, caminho_operacional)
        else:
            dados_exec = dados
            if tipo == "operacional":
                dados_exec = _montar_dados_operacionais(
                    dados,
                    foto_path=dados.get("foto_path", ""),
                    modo_preparo=dados.get("modo_preparo", []),
                )
            caminho_final = _gerar_enviar_registrar_arquivo(
                telefone=telefone,
                dados=dados_exec,
                tipo_arquivo=tipo,
                nome_prato=nome_prato_limpo,
            )
            logger.info("[Gerador] Arquivo %s concluido: %s", tipo, caminho_final)

        if cobrar_credito:
            banco.incrementar_ficha(telefone)
            logger.info("[Credito] +1 credito aplicado para %s (%s)", telefone, nome_prato_limpo)
        else:
            logger.debug("[Credito] Nenhum credito adicional para %s (%s)", telefone, nome_prato_limpo)

        _salvar_ingredientes_da_ficha(telefone, dados)

        assinante_atualizado = banco.get_assinante(telefone)
        fichas_rest = assinante_atualizado["fichas_limite_mes"] - assinante_atualizado["fichas_geradas_mes"]
        whatsapp.enviar_texto(telefone, _msg("ficha_gerada_sucesso", fichas_rest=fichas_rest))

    except Exception as e:
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        logger.error("[Gerador] Erro ao gerar arquivo: %s", safe_msg)
        from utils.alertas_grupo import alertar_erro
        alertar_erro("Erro Geração Ficha", f"{tipo} | {nome_prato_limpo} | {safe_msg}", telefone=telefone)
        whatsapp.enviar_texto(telefone, _msg("erro_gerar_ficha"))
        banco.criar_notificacao(
            "erro_sistema",
            "critico",
            "Erro na geracao de arquivo",
            f"Erro ao gerar {tipo} para {nome_prato_limpo} - {telefone}: {e}",
            telefone,
        )


def _deve_consumir_credito_por_prato(telefone: str, nome_prato: str) -> bool:
    """TODA geração consome 1 credito — prato novo, repetido ou recalculado."""
    return True


def _gerar_enviar_registrar_arquivo(telefone: str, dados: dict, tipo_arquivo: str, nome_prato: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        nome_arquivo = storage.gerar_nome_arquivo(telefone, nome_prato, tipo_arquivo)
        caminho_tmp = os.path.join(tmpdir, nome_arquivo)

        if tipo_arquivo == "tecnica":
            xlsx_gerador.gerar_ficha_xlsx(dados, caminho_tmp)
            caption = f"📊 Ficha Tecnica - {nome_prato}"
        else:
            foto_path = dados.get("foto_path", "")
            pdf_gerador.gerar_ficha_pdf(dados, caminho_tmp, foto_path=foto_path)
            caption = f"📄 Ficha Operacional - {nome_prato}"

        caminho_final = storage.salvar_arquivo(telefone, nome_arquivo, caminho_origem=caminho_tmp)
        whatsapp.enviar_arquivo(telefone, caminho_final, caption=caption)
        _registrar_ficha_gerada(telefone, dados, tipo_arquivo, nome_prato, caminho_final)
        logger.info("[Gerador] %s enviado para %s: %s", tipo_arquivo, telefone, caminho_final)
        return caminho_final


def _registrar_ficha_gerada(telefone: str, dados: dict, tipo: str, nome_prato: str, caminho_final: str) -> None:
    custo_total = _calcular_custo_total(dados)
    peso_porcao = dados.get("peso_porcao_kg", 0.1)
    ingredientes = dados.get("ingredientes", [])
    rendimento = sum(i.get("peso_liquido", 0) * i.get("ic", 1) for i in ingredientes)
    num_porcoes = rendimento / peso_porcao if peso_porcao > 0 else 0

    banco.salvar_ficha(
        telefone,
        {
            "nome_prato": nome_prato,
            "tipo": tipo,
            "codigo": dados.get("codigo", ""),
            "custo_total": custo_total,
            "custo_porcao": custo_total / num_porcoes if num_porcoes > 0 else 0,
            "num_porcoes": round(num_porcoes, 1),
            "arquivo_path": caminho_final,
        },
    )
    logger.info("[Banco] Ficha registrada tipo=%s prato=%s", tipo, nome_prato)


def _salvar_ingredientes_da_ficha(telefone: str, dados: dict) -> None:
    """Salva ingredientes da ficha SEM custo — preco muda e deve ser pedido a cada ficha."""
    ingredientes = dados.get("ingredientes", [])
    for ing in ingredientes:
        banco.salvar_ingrediente(
            telefone,
            ing.get("nome", ""),
            ing.get("unidade", "kg"),
            ing.get("fc", 1.0),
            ing.get("ic", 1.0),
        )
    if ingredientes:
        logger.info("[Banco] Ingredientes atualizados: %s item(ns)", len(ingredientes))


def _salvar_subficha_no_estado(telefone: str, tool_input: dict, resultado: dict) -> None:
    """Salva resultado da subficha no estado para o LLM lembrar nas próximas mensagens."""
    estado = banco.get_estado(telefone)
    dados = estado.get("dados", {})
    subfichas = dados.get("subfichas_calculadas", {})

    nome = tool_input.get("nome_subficha", "?")
    subfichas[nome] = {
        "custo_por_kg": resultado["custo_por_kg"],
        "rendimento_kg": resultado["rendimento_kg"],
        "custo_total": resultado["custo_total"],
    }

    dados["subfichas_calculadas"] = subfichas
    banco.set_estado(telefone, estado["estado"], dados)
    logger.info("[Subficha] Salva no estado: %s = R$ %.2f/kg", nome, resultado["custo_por_kg"])


def _calcular_subficha_python(dados: dict) -> dict:
    """
    Calcula custo por kg de um pré-preparo (subficha).
    Toda a aritmética é feita em Python — o LLM NUNCA faz contas.
    """
    nome = dados.get("nome_subficha", "Pré-preparo")
    ingredientes = dados.get("ingredientes", [])
    rendimento_kg = float(dados.get("rendimento_kg", 1) or 1)

    linhas = [f"Subficha: {nome}", ""]
    custo_total = 0.0

    for idx, ing in enumerate(ingredientes, 1):
        nome_ing = ing.get("nome", "?")
        peso = float(ing.get("peso_kg", 0) or 0)
        cu = float(ing.get("custo_unit", 0) or 0)
        custo_ing = round(cu * peso, 2)
        custo_total += custo_ing
        linhas.append(f"{idx}. {nome_ing}: {peso:.3f}kg x R$ {cu:.2f}/kg = R$ {custo_ing:.2f}")

    custo_total = round(custo_total, 2)
    custo_por_kg = round(custo_total / rendimento_kg, 2) if rendimento_kg > 0 else 0

    linhas.append("")
    linhas.append(f"Custo total da receita: R$ {custo_total:.2f}")
    linhas.append(f"Rendimento: {rendimento_kg:.2f}kg")
    linhas.append(f"Custo por kg: R$ {custo_por_kg:.2f}")

    return {
        "custo_total": custo_total,
        "custo_por_kg": custo_por_kg,
        "rendimento_kg": rendimento_kg,
        "mensagem": "\n".join(linhas),
    }


def _calcular_custo_total(dados: dict) -> float:
    """Custo total = soma de (custo_unit × peso_bruto) de cada ingrediente.
    peso_bruto = peso_liquido × FC (o que efetivamente se compra)."""
    total = 0.0
    for ing in dados.get("ingredientes", []):
        pb = ing.get("peso_bruto", 0)
        pl = ing.get("peso_liquido", 0)
        fc = ing.get("fc", 1.0) or 1.0
        # Se peso_bruto não veio, calcula a partir de peso_liquido × FC
        if not pb and pl:
            pb = pl * fc
        total += ing.get("custo_unit", 0) * pb
    return round(total, 2)


# â”€â”€ FALHAS E ALERTAS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _registrar_falha(telefone: str, assinante: dict) -> None:
    qtd = _falhas.get(telefone, 0) + 1
    _falhas.set(telefone, qtd)

    if qtd == 1:
        whatsapp.enviar_texto(telefone, _msg("falha_entender_1"))
    elif qtd == 2:
        whatsapp.enviar_texto(telefone, _msg("falha_entender_2"))
    elif qtd >= 3:
        _falhas.delete(telefone)
        whatsapp.enviar_texto(telefone, _msg("falha_entender_3"))
        # Alerta para o gestor
        nome = assinante.get("nome", telefone)
        banco.criar_notificacao(
            "sem_entender", "aviso",
            "Agente nÃ£o entendeu cliente",
            f"{nome} ({telefone}) enviou 3 mensagens que o agente nÃ£o conseguiu interpretar.",
            telefone
        )
        if config.GESTOR_WHATSAPP:
            whatsapp.enviar_texto(config.GESTOR_WHATSAPP, _msg("alerta_gestor_nao_entendeu", nome=nome, telefone=telefone))


def _enviar_link_renovacao(telefone: str, assinante: dict, metodo: str) -> None:
    try:
        if metodo == "cartao":
            from utils.asaas import criar_link_cartao_avulso

            pagamento = criar_link_cartao_avulso(
                telefone,
                config.PLANO_VALOR,
                "Mindhub Mindnutri - Renovacao antecipada",
            )
            link = pagamento.get("url", "")
            plid = pagamento.get("payment_link_id", "")
            # Persistir no modelo Assinante para o webhook encontrar
            if plid:
                banco.atualizar_assinante(telefone, payment_link_id=plid)
            banco.set_estado(
                telefone,
                "aguardando_pagamento",
                {"payment_link_id": plid, "metodo_pagamento": metodo},
            )
        else:
            from utils.asaas import criar_cobranca_pix

            pagamento = criar_cobranca_pix(
                telefone,
                config.PLANO_VALOR,
                "Mindhub Mindnutri - Renovacao via Pix",
            )
            link = pagamento.get("invoice_url", "")
            banco.set_estado(
                telefone,
                "aguardando_pagamento",
                {"payment_id": pagamento.get("payment_id", ""), "metodo_pagamento": metodo},
            )

        whatsapp.enviar_texto(telefone, _msg("link_renovacao", metodo=metodo, link=link))
    except Exception as e:
        logger.error("[Renovacao] Erro ao gerar link de renovacao para %s: %s", telefone, e)
        from utils.alertas_grupo import alertar_erro
        alertar_erro("Erro Renovação", str(e), telefone=telefone, estado="aguardando_renovacao")
        whatsapp.enviar_texto(telefone, _msg("erro_renovacao"))

