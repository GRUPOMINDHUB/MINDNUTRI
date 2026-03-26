import json
import re
import os
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
import logging

# ConfiguraÃ§Ã£o de log em arquivo
logging.basicConfig(
    filename='agente_debug.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

import openai
import requests

from django.conf import settings as config
from agente_app.prompt import SYSTEM_PROMPT
from painel.mensagens_cache import msg as _msg
from utils import banco, whatsapp, midia, storage
from agente_app.gerador import xlsx_gerador, pdf_gerador

_gpt = openai.OpenAI(api_key=config.OPENAI_API_KEY)

# Pasta de assets (logo, exemplos) â€” relativa Ã  raiz do projeto Django (mindnutri_painel/)
ASSETS_DIR   = Path(__file__).parent.parent / "assets"
EXEMPLOS_DIR = Path(__file__).parent.parent / "exemplos"

# Contador de falhas de entendimento por telefone.
# Note: not thread-safe; acceptable for single-process --noreload deployments.
# For multi-process/threaded setups, move to a persistent store (e.g. banco).
_falhas: dict[str, int] = {}



# ── HELPERS DE DETECÇÃO ───────────────────────────────────────────────────────

_FRASES_ZERO = (
    "comecar do zero", "começar do zero", "recomecar", "recomeçar",
    "reiniciar", "do zero", "start over", "reset", "apagar tudo",
    "quero comecar", "quero começar",
)

def _quer_comecar_do_zero(texto: str) -> bool:
    t = (texto or "").lower().strip()
    return any(f in t for f in _FRASES_ZERO)


def _iniciar_boas_vindas(telefone: str) -> None:
    banco.set_estado(telefone, "aguardando_nicho_demo", {})
    whatsapp.enviar_texto(telefone, _msg("boas_vindas_inicial"))


def processar_mensagem(telefone: str, tipo: str, texto: str = None,
                       midia_id: str = None, midia_bytes: bytes = None) -> None:
    """Ponto de entrada único para todas as mensagens recebidas."""
    logger.info(f"[Recebido] telefone={telefone} tipo={tipo} texto={texto}")

    estado = banco.get_estado(telefone)

    # ── Processar mídia ──────────────────────────────────────────────
    estado_atual_midia = estado.get("estado", "")
    logger.debug(f"[Midia] estado={estado_atual_midia} tipo={tipo} tem_midia_bytes={midia_bytes is not None}")
    if estado_atual_midia in ("coletando_foto_preparo", "aguardando_foto_operacional") and tipo == "imagem" and midia_bytes:
        logger.debug(f"[Midia] Salvando foto do prato ({len(midia_bytes)} bytes)")
        foto_path = _salvar_foto_prato_operacional(telefone, midia_bytes)
        if foto_path:
            texto = f"[FOTO_PRATO]{foto_path}"
            tipo = "texto"
            logger.debug(f"[Midia] Foto salva com sucesso: {foto_path}")
        else:
            whatsapp.enviar_texto(telefone, _msg("foto_nao_salva"))
            return
    elif estado_atual_midia in ("coletando_foto_preparo", "aguardando_foto_operacional") and tipo == "imagem" and not midia_bytes:
        logger.error("[Midia] Imagem recebida mas midia_bytes está vazio!")
        whatsapp.enviar_texto(telefone, _msg("foto_nao_salva"))
        return
    elif tipo == "audio" and midia_bytes:
        try:
            texto_transcrito = midia.transcrever_audio(midia_bytes)
        except Exception as e:
            logger.error(f"[Midia] Falha ao transcrever audio de {telefone}: {e}")
            whatsapp.enviar_texto(telefone, _msg("audio_nao_transcrito"))
            return
        if not texto_transcrito:
            whatsapp.enviar_texto(telefone, _msg("audio_nao_transcrito"))
            return
        texto = texto_transcrito
    elif tipo == "imagem" and midia_bytes:
        try:
            ingredientes_extraidos = midia.extrair_ingredientes_de_imagem(midia_bytes)
        except Exception as e:
            logger.error(f"[Midia] Falha ao extrair ingredientes de imagem de {telefone}: {e}")
            whatsapp.enviar_texto(telefone,
                "Recebi sua imagem, mas não consegui processá-la. "
                "Pode tentar enviar novamente ou descrever por texto?")
            return
        texto = f"[IMAGEM ENVIADA]\nIngredientes identificados na imagem:\n{ingredientes_extraidos}"
    elif tipo == "imagem" and not midia_bytes:
        logger.error("[Midia] Imagem recebida fora do fluxo de foto, midia_bytes vazio!")
        whatsapp.enviar_texto(telefone,
            "Recebi sua imagem, mas não consegui processá-la. "
            "Pode tentar enviar novamente ou descrever por texto?")
        return
    elif tipo == "documento" and midia_bytes:
        texto = "[DOCUMENTO ENVIADO] O cliente enviou um documento para análise."

    if not texto:
        whatsapp.enviar_texto(telefone, _msg("mensagem_nao_entendida"))
        return

    texto_lower = texto.lower().strip()
    est = estado["estado"]

    logger.debug(f"telefone={telefone} estado={est}")

    # ── Confirmação de reset em andamento ────────────────────────────
    if est == "confirmando_reset":
        if _eh_resposta_sim(texto):
            banco.limpar_historico(telefone)
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
        "aguardando_confirmacao_geracao", "oferecendo_pdf",
        "aguardando_decisao_ficha_operacional", "coletando_foto_preparo",
        "aguardando_foto_operacional", "aguardando_modo_preparo_operacional",
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

    if est == "aguardando_confirmacao_geracao":
        _fluxo_confirmacao_geracao(telefone, texto, estado, assinante)
        return

    if est in ("oferecendo_pdf", "aguardando_decisao_ficha_operacional"):
        _fluxo_decisao_ficha_operacional(telefone, texto, estado, assinante)
        return

    if est in ("coletando_foto_preparo", "aguardando_foto_operacional", "aguardando_modo_preparo_operacional"):
        _fluxo_coletando_foto_preparo(telefone, texto, estado, assinante)
        return

    _conversar_com_ia(telefone, texto, assinante)

# ── FLUXO PRÉ-ASSINATURA ─────────────────────────────────────────────────────

def _verificar_cupom(telefone: str, texto: str, estado: dict) -> bool:
    """Verifica se o texto contém um cupom válido. Se sim, salva no estado e avisa o user."""
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
        logger.info(f"[Cupom] {cupom.codigo} aplicado para {telefone} — R$ {cupom.valor_primeiro_pagamento}")
        return True
    return False


def _fluxo_pre_assinatura(telefone: str, texto: str, texto_lower: str, estado: dict) -> None:
    """
    Fluxo completo para quem ainda não assinou:
    boas-vindas → demo por nicho → oferta → coleta dados → pagamento
    """
    est = estado["estado"]

    # Detectar cupom em qualquer estado do onboarding (exceto inicio)
    if est not in ("inicio", "") and _verificar_cupom(telefone, texto, estado):
        return

    # Primeiro contato ou estado inicial
    if est in ("inicio", ""):
        _iniciar_boas_vindas(telefone)
        return

    # Aguardando escolha de nicho para o exemplo
    if est == "aguardando_nicho_demo":
        _enviar_exemplo_por_nicho(telefone, texto)
        banco.set_estado(telefone, "aguardando_interesse", {})
        whatsapp.enviar_texto(telefone, _msg("interesse_pos_demo"))
        return

    # Aguardando resposta de interesse após demo
    if est == "aguardando_interesse":
        if any(w in texto_lower for w in ("sim", "quero", "gostei", "interessei", "claro", "bora", "vamos", "show", "top", "saber", "mais", "conta")):
            banco.set_estado(telefone, "aguardando_decisao_assinar", {})
            whatsapp.enviar_texto(telefone, _msg("oferta_pos_demo", valor=f"{config.PLANO_VALOR:.2f}"))
        else:
            whatsapp.enviar_texto(telefone, _msg("nao_tem_interesse"))
            banco.set_estado(telefone, "inicio", {})
        return

    # Aguardando decisão de assinar
    if est == "aguardando_decisao_assinar":
        if any(w in texto_lower for w in ("assinar", "sim", "quero", "pagar", "contratar")):
            banco.set_estado(telefone, "coletando_dados", {})
            _conversar_coleta_dados(telefone, texto, estado)
        else:
            whatsapp.enviar_texto(telefone, _msg("nao_quer_assinar"))
        return

    # Coletando dados via LLM (Nome, CPF, Instagram)
    if est == "coletando_dados":
        _conversar_coleta_dados(telefone, texto, estado)
        return

    # Escolha do método de pagamento
    if est == "escolha_pagamento_assinatura":
        metodo = _interpretar_metodo_pagamento(texto)
        if not metodo:
            _pedir_metodo_pagamento(telefone, "escolha_pagamento_assinatura",
                "Não entendi o método. Pode repetir?")
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
                "Qual método você prefere agora?")
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
    Usa LLM para coletar Nome, CPF e Instagram de forma conversacional.
    Quando todos os dados estiverem confirmados, avança para pagamento.
    """
    prompt_coleta = _msg("prompt_coleta")

    historico = banco.get_historico(telefone, limite=10)
    banco.salvar_mensagem(telefone, "user", texto)

    mensagens = [{"role": "system", "content": prompt_coleta}] + historico + [{"role": "user", "content": texto}]

    tools = [{
        "type": "function",
        "function": {
            "name": "concluir_coleta_dados",
            "description": "Conclui o cadastro após coletar nome, cpf e instagram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome":      {"type": "string"},
                    "cpf":       {"type": "string"},
                    "instagram": {"type": "string"},
                },
                "required": ["nome", "cpf", "instagram"],
            },
        },
    }]

    try:
        modelo = getattr(config, "OPENAI_MODEL", "gpt-4o")
        resposta = _gpt.chat.completions.create(
            model=modelo,
            messages=mensagens,
            tools=tools,
        )
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
                cpf       = re.sub(r"\D", "", args.get("cpf") or "")
                instagram = (args.get("instagram") or "").strip()

                if not (nome and cpf and instagram):
                    whatsapp.enviar_texto(telefone, _msg("dados_coleta_quase_la"))
                    return

                if instagram.lower() in ("nao", "não", "n", "nenhum", "nao tenho", "não tenho"):
                    instagram = "NAO"
                elif not instagram.startswith("@"):
                    instagram = "@" + instagram.lstrip("@")

                # Salva dados no estado para usar em _iniciar_assinatura
                dados_cadastro = {"nome": nome, "cpf": cpf, "instagram": instagram}
                banco.set_estado(telefone, "escolha_pagamento_assinatura", dados_cadastro)
                banco.salvar_mensagem(telefone, "system", "[Dados coletados]")

                whatsapp.enviar_texto(telefone, _msg("dados_coletados_pagamento", nome=nome))
                return

        if not message.content and not message.tool_calls:
            whatsapp.enviar_texto(telefone, _msg("dados_coleta_vazio"))

    except Exception as e:
        logger.error(f"[Coleta dados] Erro: {e}")
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
        logger.error(f"Arquivo de exemplo não encontrado: {xlsx_path}")

    if pdf_path.exists():
        whatsapp.enviar_arquivo(telefone, str(pdf_path),
            caption=f"Ficha Operacional — {nicho_label} (PDF)")
        enviou_algo = True
    else:
        logger.error(f"Arquivo de exemplo não encontrado: {pdf_path}")

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


def _pedir_metodo_pagamento(telefone: str, estado_destino: str, abertura: str) -> None:
    banco.set_estado(telefone, estado_destino, {})
    whatsapp.enviar_texto(telefone, _msg("pedir_metodo_pagamento", abertura=abertura))


def _iniciar_assinatura(telefone: str, metodo: str, dados_cadastro: dict = None) -> None:
    """Cria o Assinante no banco (se ainda não existir), gera o link e envia ao cliente."""
    logger.info(f"[Asaas] Iniciando assinatura para {telefone} via {metodo}")

    # Cria o Assinante APENAS agora (na emissão do link de pagamento)
    dados = dados_cadastro or {}
    if not banco.get_assinante(telefone):
        from painel.models import Assinante
        Assinante.objects.get_or_create(
            telefone=telefone,
            defaults={
                "nome":      dados.get("nome", ""),
                "cpf":       dados.get("cpf", ""),
                "instagram": dados.get("instagram", ""),
                "status":    "pendente",
            }
        )
    else:
        if dados:
            banco.atualizar_assinante(telefone,
                nome=dados.get("nome", ""),
                cpf=dados.get("cpf", ""),
                instagram=dados.get("instagram", ""),
            )

    # Verificar se há cupom aplicado
    cupom_codigo = dados.get("cupom_codigo")
    cupom_valor = dados.get("cupom_valor")
    valor_primeiro = float(cupom_valor) if cupom_valor else config.PLANO_VALOR

    if cupom_codigo:
        logger.info(f"[Cupom] Usando cupom {cupom_codigo} — primeiro pagamento R$ {valor_primeiro:.2f}")

    try:
        if metodo == "cartao":
            from utils.asaas import criar_link_assinatura_cartao
            pagamento = criar_link_assinatura_cartao(telefone, valor_primeiro_pagamento=valor_primeiro)
            link = pagamento.get("url")
        else:
            from utils.asaas import criar_cobranca_pix
            pagamento = criar_cobranca_pix(
                telefone,
                valor_primeiro,
                f"Mindhub Mindnutri - Assinatura Mensal via Pix{' (cupom ' + cupom_codigo + ')' if cupom_codigo else ''}",
            )
            link = pagamento.get("invoice_url")
            codigo_pix = pagamento.get("pix_copy_paste", "")

        if not link:
            raise ValueError("Link de pagamento retornado vazio pelo Asaas")

        dados_estado = {"metodo_pagamento": metodo}
        if metodo == "cartao":
            dados_estado["payment_link_id"] = pagamento.get("payment_link_id", "")
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

        banco.set_estado(telefone, "aguardando_pagamento", dados_estado)

    except Exception as e:
        logger.error(f"ERRO ASAAS: {e}")
        if isinstance(e, requests.exceptions.HTTPError) and hasattr(e, 'response') and e.response is not None:
            logger.error(f"ASAAS RESPONSE: {e.response.text}")

        erro_body = e.response.text if isinstance(e, requests.exceptions.HTTPError) and hasattr(e, 'response') and e.response is not None else ""
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
    whatsapp.enviar_texto(telefone, _msg("menu_principal", nome=nome, fichas_rest=fichas_rest))



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
    bruto = (texto or "").strip()
    if not bruto:
        return []

    # Se é uma lista (da IA), já vem ok
    if isinstance(texto, list):
        return [str(p).strip() for p in texto if str(p).strip()]

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
        logger.debug(f"[Fluxo PDF] Foto salva em: {caminho}")
        return caminho
    except Exception as e:
        logger.error(f"[Fluxo PDF] Falha ao salvar foto do prato: {e}")
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


def _iniciar_fluxo_pos_coleta_tecnica(telefone: str, dados_tecnica: dict) -> None:
    """
    Dados coletados pela IA. Pergunta se quer PDF operacional.
    - SIM → coleta foto + modo de preparo → gera EXCEL + PDF juntos (combo)
    - NÃO → gera só o EXCEL
    """
    dados_fluxo = {
        "tecnica_dados": dados_tecnica,
        "modo_preparo": dados_tecnica.get("modo_preparo", []),
        "foto_path": "",
    }
    banco.set_estado(telefone, "aguardando_decisao_ficha_operacional", dados_fluxo)
    whatsapp.enviar_texto(telefone, _msg("pergunta_ficha_operacional"))
    logger.debug(f"[Fluxo] Pergunta sobre PDF enviada para {telefone}")


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
        logger.info(f"[Fluxo] Gerando combo XLSX+PDF para {telefone}")
        _gerar_e_enviar_arquivo(telefone, dados_combo, "combo", assinante)
    else:
        # Só Excel
        logger.info(f"[Fluxo] Gerando somente XLSX para {telefone}")
        _gerar_e_enviar_arquivo(telefone, dados_tecnica, "tecnica", assinante)

    banco.resetar_estado(telefone)


def _avancar_coleta_operacional(telefone: str, fluxo: dict, assinante: dict) -> None:
    foto_path = (fluxo.get("foto_path") or "").strip()
    modo_preparo = fluxo.get("modo_preparo") or fluxo.get("tecnica_dados", {}).get("modo_preparo", [])

    if not foto_path:
        banco.set_estado(telefone, "aguardando_foto_operacional", fluxo)
        whatsapp.enviar_texto(telefone, _msg("aguardando_foto"))
        logger.debug(f"[Fluxo PDF] Aguardando foto do prato de {telefone}")
        return

    if not modo_preparo:
        banco.set_estado(telefone, "aguardando_modo_preparo_operacional", fluxo)
        whatsapp.enviar_texto(telefone, _msg("aguardando_modo_preparo"))
        logger.debug(f"[Fluxo PDF] Aguardando modo de preparo de {telefone}")
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
        logger.info(f"[Fluxo PDF] Cliente {telefone} optou por gerar PDF operacional.")
        _avancar_coleta_operacional(telefone, fluxo, assinante)
        return

    if _eh_resposta_nao(texto):
        fluxo["gerar_operacional"] = False
        whatsapp.enviar_texto(telefone, _msg("somente_tecnica"))
        logger.info(f"[Fluxo PDF] Cliente {telefone} optou por gerar somente tecnica.")
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


def _fluxo_coleta_modo_preparo_operacional(telefone: str, texto: str, estado: dict, assinante: dict) -> None:
    fluxo = estado.get("dados", {})
    passos = _normalizar_lista_modo_preparo(texto)

    if not passos:
        whatsapp.enviar_texto(telefone, _msg("modo_preparo_nao_identificado"))
        return

    fluxo["modo_preparo"] = passos
    banco.set_estado(telefone, "aguardando_modo_preparo_operacional", fluxo)
    logger.debug(f"[Fluxo PDF] Modo de preparo recebido ({len(passos)} passos) para {telefone}")
    _finalizar_fluxo_geracao_integrada(telefone, fluxo, assinante)


# â”€â”€ CONVERSA COM IA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _conversar_com_ia(telefone: str, texto: str, assinante: dict) -> None:
    """
    Envia mensagem para a IA com todo o contexto e retorna resposta.
    Detecta quando a IA quer gerar um arquivo.
    """
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
        logger.warning(f"[IA] Falha ao carregar base de perdas: {e}")
        perdas_texto = ""

    contexto_extra = f"""
CONTEXTO DO CLIENTE:
- Nome: {assinante.get('nome', 'nao informado')}
- Estabelecimento: {assinante.get('estabelecimento', 'nao informado')}
- Nicho: {assinante.get('nicho', 'nao informado')}
- Cidade: {assinante.get('cidade', 'nao informado')}
- Fichas restantes este mes: {fichas_rest}
- Ingredientes ja cadastrados: {', '.join(nomes_ing) if nomes_ing else 'nenhum ainda'}

BASE DE PERDAS PADRAO (use como referencia ao perguntar sobre perdas):
{perdas_texto if perdas_texto else 'Nenhuma perda cadastrada.'}
"""

    from painel.models import ConfiguracaoIA
    _cfg = ConfiguracaoIA.get_config()
    _sys_prompt = _cfg.get_system_prompt() or SYSTEM_PROMPT
    system_com_contexto = _sys_prompt + "\n\n" + contexto_extra
    
    # Prepara mensagens para OpenAI (System prompt embutido no histÃ³rico)
    mensagens_openai = [{"role": "system", "content": system_com_contexto}] + historico

    try:
        # Detecta se deve gerar arquivo via ferramenta (formato OpenAI)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "gerar_ficha_tecnica",
                    "description": "Gera a ficha tÃ©cnica em XLSX quando todos os dados foram coletados e o cliente confirmou a geraÃ§Ã£o.",
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
                    "name": "gerar_ficha_operacional",
                    "description": "Gera a ficha operacional em PDF quando todos os dados foram coletados e o cliente confirmou.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nome_prato":        {"type": "string"},
                            "classificacao":     {"type": "string"},
                            "codigo":            {"type": "string"},
                            "rendimento_porcoes": {"type": "number"},
                            "ingredientes_op": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "qtd":  {"type": "string"},
                                        "nome": {"type": "string"},
                                    },
                                    "required": ["qtd", "nome"]
                                }
                            },
                            "modo_preparo": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["nome_prato", "classificacao", "ingredientes_op"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "salvar_ingredientes",
                    "description": "Salva ingredientes na base do cliente apÃ³s coletar nome, unidade, custo, FC e IC.",
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
                                        "custo":   {"type": "number"},
                                        "fc":      {"type": "number"},
                                        "ic":      {"type": "number"},
                                    },
                                    "required": ["nome", "unidade", "custo"]
                                }
                            }
                        },
                        "required": ["ingredientes"]
                    }
                }
            }
        ]

        # ConfiguraÃ§Ã£o do modelo caso nÃ£o tenha sido migrada
        modelo_escolhido = _cfg.modelo_ia or getattr(config, 'OPENAI_MODEL', 'gpt-4o')

        resposta = _gpt.chat.completions.create(
            model=modelo_escolhido,
            messages=mensagens_openai,
            tools=tools
        )

        message = resposta.choices[0].message

        # Processa resposta textual e tools (se houver)
        texto_resposta = message.content or ""
        tool_calls = message.tool_calls

        # Reseta contador de falhas
        _falhas[telefone] = 0

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
                    logger.error(f"Erro ao decodificar argumentos da função {tool_name}")
                    continue

                if tool_name == "gerar_ficha_tecnica":
                    tool_input["estabelecimento"] = assinante.get("estabelecimento", "")
                    _iniciar_fluxo_pos_coleta_tecnica(telefone, tool_input)
                    continue

                elif tool_name == "gerar_ficha_operacional":
                    if texto_resposta and not texto_enviado:
                        whatsapp.enviar_texto(telefone, texto_resposta)
                        texto_enviado = True
                    tool_input["estabelecimento"] = assinante.get("estabelecimento", "")
                    dados_pdf = _montar_dados_operacionais(
                        tool_input,
                        foto_path=tool_input.get("foto_path", ""),
                        modo_preparo=tool_input.get("modo_preparo", []),
                    )
                    _gerar_e_enviar_arquivo(telefone, dados_pdf, "operacional", assinante)

                elif tool_name == "salvar_ingredientes":
                    for ing in tool_input.get("ingredientes", []):
                        banco.salvar_ingrediente(
                            telefone,
                            ing["nome"],
                            ing.get("unidade", "kg"),
                            ing.get("custo", 0),
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
            banco.salvar_mensagem(telefone, "assistant", texto_resposta)
            whatsapp.enviar_texto(telefone, texto_resposta)

    except Exception as e:
        safe_msg = repr(e).encode('utf-8', 'ignore').decode('utf-8')
        logger.error(f"[OpenAI] Erro: {safe_msg}")
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
        logger.debug(f"[Credito] prato={nome_prato_limpo} cobrar_credito={cobrar_credito} tipo={tipo}")

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
            logger.info(f"[Gerador] Combo concluido: tecnica={caminho_tecnica} operacional={caminho_operacional}")
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
            logger.info(f"[Gerador] Arquivo {tipo} concluido: {caminho_final}")

        if cobrar_credito:
            banco.incrementar_ficha(telefone)
            logger.info(f"[Credito] +1 credito aplicado para {telefone} ({nome_prato_limpo})")
        else:
            logger.debug(f"[Credito] Nenhum credito adicional para {telefone} ({nome_prato_limpo})")

        _salvar_ingredientes_da_ficha(telefone, dados)

        assinante_atualizado = banco.get_assinante(telefone)
        fichas_rest = assinante_atualizado["fichas_limite_mes"] - assinante_atualizado["fichas_geradas_mes"]
        whatsapp.enviar_texto(telefone, _msg("ficha_gerada_sucesso", fichas_rest=fichas_rest))

    except Exception as e:
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        logger.error(f"[Gerador] Erro ao gerar arquivo: {safe_msg}")
        whatsapp.enviar_texto(telefone, _msg("erro_gerar_ficha"))
        banco.criar_notificacao(
            "erro_sistema",
            "critico",
            "Erro na geracao de arquivo",
            f"Erro ao gerar {tipo} para {nome_prato_limpo} - {telefone}: {e}",
            telefone,
        )


def _deve_consumir_credito_por_prato(telefone: str, nome_prato: str) -> bool:
    """Um prato no mes consome no maximo 1 credito (tecnica + operacional)."""
    ja_tem_tecnica = banco.possui_ficha_no_mes(telefone, nome_prato, "tecnica")
    ja_tem_operacional = banco.possui_ficha_no_mes(telefone, nome_prato, "operacional")
    return not (ja_tem_tecnica or ja_tem_operacional)


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
        logger.info(f"[Gerador] {tipo_arquivo} enviado para {telefone}: {caminho_final}")
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
    logger.info(f"[Banco] Ficha registrada tipo={tipo} prato={nome_prato}")


def _salvar_ingredientes_da_ficha(telefone: str, dados: dict) -> None:
    ingredientes = dados.get("ingredientes", [])
    for ing in ingredientes:
        banco.salvar_ingrediente(
            telefone,
            ing.get("nome", ""),
            ing.get("unidade", "kg"),
            ing.get("custo_unit", 0),
            ing.get("fc", 1.0),
            ing.get("ic", 1.0),
        )
    if ingredientes:
        logger.info(f"[Banco] Ingredientes atualizados: {len(ingredientes)} item(ns)")


def _calcular_custo_total(dados: dict) -> float:
    total = 0.0
    for ing in dados.get("ingredientes", []):
        total += ing.get("custo_unit", 0) * ing.get("peso_liquido", 0)
    return round(total, 2)


# â”€â”€ FALHAS E ALERTAS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _registrar_falha(telefone: str, assinante: dict) -> None:
    _falhas[telefone] = _falhas.get(telefone, 0) + 1
    qtd = _falhas[telefone]

    if qtd == 1:
        whatsapp.enviar_texto(telefone, _msg("falha_entender_1"))
    elif qtd == 2:
        whatsapp.enviar_texto(telefone, _msg("falha_entender_2"))
    elif qtd >= 3:
        _falhas[telefone] = 0
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
            banco.set_estado(
                telefone,
                "aguardando_pagamento",
                {"payment_link_id": pagamento.get("payment_link_id", ""), "metodo_pagamento": metodo},
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
        logger.error(f"[Renovacao] Erro ao gerar link de renovacao para {telefone}: {e}")
        whatsapp.enviar_texto(telefone, _msg("erro_renovacao"))

