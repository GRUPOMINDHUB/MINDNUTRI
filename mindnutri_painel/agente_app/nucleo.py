import json
import re
import os
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
import logging
import traceback

# ConfiguraÃ§Ã£o de log em arquivo
logging.basicConfig(
    filename='agente_debug.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

import openai
import requests

from django.conf import settings as config
from agente_app.prompt import SYSTEM_PROMPT
from utils import banco, whatsapp, midia, storage
from agente_app.gerador import xlsx_gerador, pdf_gerador

_gpt = openai.OpenAI(api_key=config.OPENAI_API_KEY)

# Pasta de assets (logo, exemplos) â€” relativa Ã  raiz do projeto Django (mindnutri_painel/)
ASSETS_DIR   = Path(__file__).parent.parent / "assets"
EXEMPLOS_DIR = Path(__file__).parent.parent / "exemplos"

# Contador de falhas de entendimento por telefone
_falhas: dict[str, int] = {}


# â”€â”€ ENTRADA PRINCIPAL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def processar_mensagem(telefone: str, tipo: str, texto: str = None,
                        midia_id: str = None, midia_bytes: bytes = None):
    """
    Ponto de entrada Ãºnico para todas as mensagens recebidas.
    Chamado pelo webhook do Django.
    """
    # â”€â”€ LOG DE ENTRADA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"[Recebido] Mensagem de {telefone}: {texto}")
    logging.info(f"[Recebido] telefone={telefone} tipo={tipo} texto={texto}")

    # Garante que assinante existe no banco (qualquer numero, sem restricao)
    if not banco.get_assinante(telefone):
        print(f"[Novo] Numero {telefone} nao encontrado no banco. Criando assinante...")
        logging.info(f"[Novo] Criando assinante para {telefone}")
        banco.criar_assinante(telefone)

    assinante = banco.get_assinante(telefone)
    estado    = banco.get_estado(telefone)

    # Forca estado inicial para assinantes novos sem estado definido
    if assinante["status"] == "pendente" and (not estado["estado"] or estado["estado"] == "inicio"):
        banco.set_estado(telefone, "boas_vindas_inicio", {})
        estado = banco.get_estado(telefone)

    # â”€â”€ LOG DE DEBUG (TAREFA 3) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"[DEBUG] Telefone: {telefone} | Estado Atual: {estado['estado']}")
    logging.info(f"[DEBUG] Telefone: {telefone} | Estado Atual: {estado['estado']} | Status: {assinante['status']}")

    # â”€â”€ Processar midia â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    estado_atual_midia = estado.get("estado", "")
    if estado_atual_midia in ("coletando_foto_preparo", "aguardando_foto_operacional") and tipo == "imagem" and midia_bytes:
        foto_path = _salvar_foto_prato_operacional(telefone, midia_bytes)
        if foto_path:
            texto = f"[FOTO_PRATO]{foto_path}"
            tipo = "texto"
            print(f"[Fluxo PDF] Foto recebida para {telefone}: {foto_path}")
        else:
            whatsapp.enviar_texto(
                telefone,
                "Nao consegui salvar sua foto agora. Pode tentar enviar novamente?",
            )
            return
    elif tipo == "audio" and midia_bytes:
        texto_transcrito = midia.transcrever_audio(midia_bytes)
        if not texto_transcrito:
            _registrar_falha(telefone, assinante)
            return
        texto = texto_transcrito

    elif tipo == "imagem" and midia_bytes:
        ingredientes_extraidos = midia.extrair_ingredientes_de_imagem(midia_bytes)
        texto = f"[IMAGEM ENVIADA]\nIngredientes identificados na imagem:\n{ingredientes_extraidos}"

    elif tipo == "documento" and midia_bytes:
        texto = "[DOCUMENTO ENVIADO] O cliente enviou um documento para analise."

    if not texto:
        whatsapp.enviar_texto(telefone, "Nao consegui entender sua mensagem. Pode repetir por texto?")
        return

    # â”€â”€ Fluxo de onboarding (PRIORIDADE MAXIMA para status 'pendente') â”€â”€
    if assinante["status"] == "pendente":
        print(f"[Fluxo] {telefone} pendente -> _fluxo_boas_vindas (estado={estado['estado']})")
        _fluxo_boas_vindas(telefone, texto, estado, assinante)
        return

    if assinante["status"] in ("bloqueado", "inadimplente"):
        whatsapp.enviar_texto(
            telefone,
            "Seu acesso esta suspenso no momento.\n\n"
            "Para regularizar sua assinatura, acesse o link de pagamento ou entre em contato com o suporte Mindhub.",
        )
        return

    if assinante["status"] == "cancelado":
        whatsapp.enviar_texto(telefone,
            "Sua assinatura foi cancelada. Para reativar, entre em contato com a Mindhub. ðŸ’™")
        return

    # â”€â”€ Verificar comandos especiais â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    texto_lower = texto.lower().strip()

    comandos_reset = ["cancelar", "recomeÃ§ar", "reiniciar", "menu", "/menu"]

    if texto_lower in comandos_reset:
        banco.resetar_estado(telefone)
        _enviar_menu_principal(telefone, assinante)
        return

    # â”€â”€ Fluxo de demonstraÃ§Ã£o (nÃ£o-assinante em fluxo de venda) â”€â”€
    if estado["estado"] == "demonstracao":
        _fluxo_demonstracao(telefone, texto, estado, assinante)
        return

    # â”€â”€ Verificar fichas disponÃ­veis antes de criar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    fichas_rest = assinante["fichas_limite_mes"] - assinante["fichas_geradas_mes"]
    if fichas_rest <= 3 and fichas_rest > 0:
        # Aviso proativo (uma vez)
        dados_est = estado.get("dados", {})
        if not dados_est.get("aviso_limite_enviado"):
            whatsapp.enviar_texto(telefone,
                f"âš ï¸ AtenÃ§Ã£o: vocÃª tem apenas *{fichas_rest} fichas restantes* este mÃªs.")
            dados_est["aviso_limite_enviado"] = True
            banco.set_estado(telefone, estado["estado"], dados_est)

    if fichas_rest <= 0:
        whatsapp.enviar_texto(telefone,
            "âš ï¸ VocÃª atingiu o limite de 30 fichas este mÃªs.\n\n"
            "Deseja renovar antecipadamente? Responda *SIM* para receber o link de pagamento.")
        banco.set_estado(telefone, "aguardando_renovacao", {})
        return

    # â”€â”€ DelegaÃ§Ã£o por estado â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    estado_atual = estado["estado"]

    if estado_atual == "aguardando_renovacao":
        if "sim" in texto_lower:
            _pedir_metodo_pagamento(
                telefone,
                "escolha_pagamento_renovacao",
                "Como voce prefere fazer a renovacao?",
            )
        else:
            banco.resetar_estado(telefone)
            _enviar_menu_principal(telefone, assinante)
        return

    if estado_atual == "escolha_pagamento_renovacao":
        metodo = _interpretar_metodo_pagamento(texto)
        if not metodo:
            _pedir_metodo_pagamento(
                telefone,
                "escolha_pagamento_renovacao",
                "Nao entendi o metodo de pagamento.",
            )
            return
        _enviar_link_renovacao(telefone, assinante, metodo)
        return

    if estado_atual.startswith("criando_ficha"):
        _fluxo_criacao_ficha(telefone, texto, estado, assinante)
        return

    if estado_atual == "aguardando_confirmacao_geracao":
        _fluxo_confirmacao_geracao(telefone, texto, estado, assinante)
        return

    if estado_atual in ("oferecendo_pdf", "aguardando_decisao_ficha_operacional"):
        _fluxo_oferecendo_pdf(telefone, texto, estado, assinante)
        return

    if estado_atual in ("coletando_foto_preparo", "aguardando_foto_operacional", "aguardando_modo_preparo_operacional"):
        _fluxo_coletando_foto_preparo(telefone, texto, estado, assinante)
        return

    # â”€â”€ Estado geral: conversa com a IA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _conversar_com_ia(telefone, texto, assinante)


# â”€â”€ FLUXO DE BOAS-VINDAS (primeiro contato / cadastro) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _conversar_onboarding(telefone: str, texto: str, assinante: dict):
    """
    Conduz a coleta de dados do onboarding usando Tool Isolation.
    A unica tool permitida nesse fluxo e concluir_coleta_dados.
    """
    onboarding_prompt = (
        "Você é o recepcionista do Mindnutri. Seu único objetivo é coletar 3 dados do usuário: "
        "Nome, CPF e @ do Instagram. Seja educado, acolhedor e direto. "
        "Se o usuário já informou algum dado na mensagem, absorva-o e peça apenas o que falta. "
        "Quando tiver os 3 dados confirmados, você DEVE OBRIGATORIAMENTE chamar a função "
        "'concluir_coleta_dados'."
    )

    historico = banco.get_historico(telefone, limite=20)
    banco.salvar_mensagem(telefone, "user", texto)

    mensagens_openai = [{"role": "system", "content": onboarding_prompt}] + historico + [{"role": "user", "content": texto}]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "concluir_coleta_dados",
                "description": "Conclui o onboarding apos coletar nome, cpf e instagram.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nome": {"type": "string"},
                        "cpf": {"type": "string"},
                        "instagram": {"type": "string"},
                    },
                    "required": ["nome", "cpf", "instagram"],
                },
            },
        }
    ]

    try:
        modelo_escolhido = getattr(config, "OPENAI_MODEL", "gpt-4o")
        resposta = _gpt.chat.completions.create(
            model=modelo_escolhido,
            messages=mensagens_openai,
            tools=tools,
        )

        message = resposta.choices[0].message

        if message.content and message.content.strip():
            texto_resposta = message.content.strip()
            banco.salvar_mensagem(telefone, "assistant", texto_resposta)
            whatsapp.enviar_texto(telefone, texto_resposta)

        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name != "concluir_coleta_dados":
                    continue

                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    whatsapp.enviar_texto(
                        telefone,
                        "Nao consegui confirmar seus dados. Pode reenviar nome, CPF e Instagram em uma unica mensagem?",
                    )
                    return

                nome = (args.get("nome") or "").strip()
                cpf = re.sub(r"\\D", "", args.get("cpf") or "")
                instagram = (args.get("instagram") or "").strip()

                if not (nome and cpf and instagram):
                    whatsapp.enviar_texto(
                        telefone,
                        "Perfeito, ja anotei parte dos dados. Me envie o que faltou: nome completo, CPF e @ do Instagram.",
                    )
                    return

                if instagram.lower() in ("nao", "não", "n", "nenhum", "nao tenho", "não tenho", "nao tem", "não tem"):
                    instagram = "NAO"
                elif not instagram.startswith("@"):
                    instagram = "@" + instagram.lstrip("@")

                banco.salvar_mensagem(telefone, "system", "[Coleta concluída]")
                banco.atualizar_assinante(telefone, nome=nome, cpf=cpf, instagram=instagram)
                banco.set_estado(telefone, "demonstracao_escolha_nicho", {})

                whatsapp.enviar_texto(
                    telefone,
                    f"Prazer em te conhecer, {nome}! 🎉\n\n"
                    "Quer ver um exemplo grátis do que consigo fazer antes de assinar?\n\n"
                    "Escolha um nicho:\n"
                    "1️⃣ Hambúrguer\n"
                    "2️⃣ Pizza\n"
                    "3️⃣ Sobremesa",
                )
                return

        if not message.content and not message.tool_calls:
            whatsapp.enviar_texto(
                telefone,
                "Estou aqui para te cadastrar rapidinho. Me diga seu nome, CPF e @ do Instagram.",
            )

    except Exception as e:
        safe_msg = repr(e).encode("utf-8", "ignore").decode("utf-8")
        logging.error(f"[Onboarding] Erro OpenAI: {safe_msg}")
        whatsapp.enviar_texto(
            telefone,
            "Tive uma instabilidade rapida aqui. Pode me enviar seu nome, CPF e Instagram novamente?",
        )
def _fluxo_boas_vindas(telefone: str, texto: str, estado: dict, assinante: dict):
    """
    Fluxo de primeiro contato (pendente):
    - onboarding inteligente via LLM + tool isolation
    - demonstracao
    - oferta de assinatura
    """
    est = estado["estado"]
    print(f"[Boas-vindas] {telefone}: estado='{est}', texto='{texto}'")

    if est in ("inicio", "boas_vindas_inicio", "coletando_nome", "coletando_cpf", "coletando_instagram", "demonstracao_inicio"):
        _conversar_onboarding(telefone, texto, assinante)
        return

    # Mantem a logica posterior de demonstracao e assinatura
    if est == "demonstracao_escolha_nicho":
        _enviar_exemplo_por_nicho(telefone, texto)
        banco.set_estado(telefone, "demonstracao_pos_exemplo", {})
        return

    if est == "demonstracao_pos_exemplo":
        banco.set_estado(telefone, "demonstracao_assinar", {})
        whatsapp.enviar_texto(telefone,
            "Gostou? Com o Mindnutri voce cria fichas assim para todos os seus pratos, "
            "com seus ingredientes, seus custos e sua marca.\n\n"
            f"*Plano Mensal: R$ {config.PLANO_VALOR:.2f}/mes*\n"
            "30 fichas por mes\n"
            "XLSX + PDF profissionais\n"
            "Calculo de custos instantaneo\n"
            "Base de ingredientes sempre atualizada\n\n"
            "Quer assinar agora?\n\n"
            "Responda *ASSINAR* para receber o link de pagamento.")
        return

    if est == "demonstracao_assinar":
        if any(w in texto.lower() for w in ("assinar", "sim", "quero", "pagar")):
            _pedir_metodo_pagamento(
                telefone,
                "escolha_pagamento_assinatura",
                "Perfeito! Como voce prefere pagar a assinatura?",
            )
        else:
            whatsapp.enviar_texto(telefone,
                "Sem problema! Quando quiser assinar, e so responder *ASSINAR*.")
        return

    if est == "escolha_pagamento_assinatura":
        metodo = _interpretar_metodo_pagamento(texto)
        if not metodo:
            _pedir_metodo_pagamento(
                telefone,
                "escolha_pagamento_assinatura",
                "Nao entendi o metodo de pagamento.",
            )
            return
        _iniciar_assinatura(telefone, metodo)
        return

    if est == "aguardando_pagamento":
        metodo_trocado = _interpretar_metodo_pagamento(texto)
        print(
            f"[Pagamento] {telefone}: aguardando_pagamento texto='{texto}' -> metodo_trocado='{metodo_trocado}'"
        )
        logging.info(
            f"[Pagamento] telefone={telefone} estado=aguardando_pagamento texto={texto} metodo_trocado={metodo_trocado}"
        )
        if metodo_trocado:
            whatsapp.enviar_texto(
                telefone,
                f"Perfeito, vou trocar seu pagamento para *{metodo_trocado.upper()}*.",
            )
            _iniciar_assinatura(telefone, metodo_trocado)
            return

        if any(chave in texto.lower() for chave in ("mudar", "trocar", "alterar", "outro metodo", "outro método")):
            _pedir_metodo_pagamento(
                telefone,
                "escolha_pagamento_assinatura",
                "Sem problema. Qual metodo voce prefere agora?",
            )
            return

        whatsapp.enviar_texto(telefone,
            "Ainda estamos aguardando a confirmacao do seu pagamento.\n\n"
            "Assim que compensar, seu acesso e liberado automaticamente.\n\n"
            "Se ja pagou e ainda nao foi liberado, aguarde alguns minutos.")
        return

    # Fallback seguro: mantem o usuario no onboarding ate concluir dados
    _conversar_onboarding(telefone, texto, assinante)
def _enviar_exemplo_por_nicho(telefone: str, texto: str):
    """Envia os arquivos de exemplo para o nicho escolhido."""
    texto_lower = texto.lower()

    if "1" in texto or "hamburguer" in texto_lower or "hambÃºrguer" in texto_lower or "burger" in texto_lower:
        nicho = "hamburguer"
    elif "2" in texto or "pizza" in texto_lower:
        nicho = "pizza"
    elif "3" in texto or "sobremesa" in texto_lower or "brownie" in texto_lower or "doce" in texto_lower:
        nicho = "sobremesa"
    else:
        nicho = "hamburguer"  # default

    whatsapp.enviar_texto(telefone,
        f"Perfeito! Veja aqui um exemplo de ficha tÃ©cnica e ficha operacional "
        f"para o segmento de *{nicho.capitalize()}*: ðŸ“‹")

    xlsx_path = EXEMPLOS_DIR / f"exemplo_{nicho}.xlsx"
    pdf_path  = EXEMPLOS_DIR / f"exemplo_{nicho}.pdf"

    print(f"[Exemplos] EXEMPLOS_DIR resolvido para: {EXEMPLOS_DIR.resolve()}")
    print(f"[Exemplos] xlsx_path={xlsx_path} existe={xlsx_path.exists()}")
    print(f"[Exemplos] pdf_path={pdf_path} existe={pdf_path.exists()}")

    enviou_algo = False

    if xlsx_path.exists():
        whatsapp.enviar_arquivo(telefone, str(xlsx_path),
            caption=f"Ficha TÃ©cnica â€” {nicho.capitalize()} (XLSX)")
        enviou_algo = True
    else:
        print(f"ERRO: Arquivo nÃ£o encontrado em {xlsx_path}")
        logging.error(f"Arquivo de exemplo nÃ£o encontrado: {xlsx_path}")

    if pdf_path.exists():
        whatsapp.enviar_arquivo(telefone, str(pdf_path),
            caption=f"Ficha Operacional â€” {nicho.capitalize()} (PDF)")
        enviou_algo = True
    else:
        print(f"ERRO: Arquivo nÃ£o encontrado em {pdf_path}")
        logging.error(f"Arquivo de exemplo nÃ£o encontrado: {pdf_path}")

    if not enviou_algo:
        whatsapp.enviar_texto(telefone,
            "Opa, tive um problema tÃ©cnico ao buscar esse exemplo, "
            "mas vocÃª pode assinar para testar com seus dados! ðŸš€\n\n"
            "Responda *ASSINAR* para comeÃ§ar.")


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


def _pedir_metodo_pagamento(telefone: str, estado_destino: str, abertura: str):
    banco.set_estado(telefone, estado_destino, {})
    whatsapp.enviar_texto(
        telefone,
        f"{abertura}\n\n"
        "1 Cartao de credito\n"
        "Assinatura recorrente automatica, sem boleto.\n\n"
        "2 Pix\n"
        "Pagamento do ciclo atual via Pix, sem boleto.\n\n"
        "Responda com *1*, *2*, *CARTAO* ou *PIX*.",
    )


def _iniciar_assinatura(telefone: str, metodo: str):
    """Gera o link conforme o metodo escolhido e envia ao cliente."""
    print(f"[Asaas] Iniciando criaÃ§Ã£o de assinatura para {telefone}")
    logging.info(f"[Asaas] Iniciando assinatura para {telefone} via {metodo}")
    try:
        if metodo == "cartao":
            from utils.asaas import criar_link_assinatura_cartao
            pagamento = criar_link_assinatura_cartao(telefone)
            link = pagamento.get("url")
        else:
            from utils.asaas import criar_cobranca_pix
            pagamento = criar_cobranca_pix(
                telefone,
                config.PLANO_VALOR,
                "Mindhub Mindnutri - Assinatura Mensal via Pix",
            )
            link = pagamento.get("invoice_url")
            codigo_pix = pagamento.get("pix_copy_paste", "")

        if not link:
            raise ValueError("Link de pagamento retornado vazio pelo Asaas")

        dados_estado = {"metodo_pagamento": metodo}
        if metodo == "cartao":
            dados_estado["payment_link_id"] = pagamento.get("payment_link_id", "")
            whatsapp.enviar_texto(
                telefone,
                "Perfeito! Aqui esta seu link de pagamento em *cartao de credito*.\n\n"
                f"ðŸ”— {link}\n\n"
                "Esse fluxo ativa a *assinatura mensal automatica* do Mindnutri. "
                "Assim que o pagamento for aprovado, seu acesso sera liberado automaticamente.",
            )
        else:
            dados_estado["payment_id"] = pagamento.get("payment_id", "")
            mensagem_pix = (
                "Perfeito! Aqui esta seu link de pagamento em *Pix*.\n\n"
                f"ðŸ”— {link}\n\n"
            )
            if codigo_pix:
                mensagem_pix += f"Codigo Pix copia e cola:\n{codigo_pix}\n\n"
            mensagem_pix += (
                "Assim que o pagamento for confirmado, seu acesso sera liberado automaticamente. "
                "Nas renovacoes via Pix, o pagamento segue manual a cada ciclo."
            )
            whatsapp.enviar_texto(telefone, mensagem_pix)

        banco.set_estado(telefone, "aguardando_pagamento", dados_estado)
        return

        whatsapp.enviar_texto(telefone,
            f"Ã“timo! Aqui estÃ¡ seu link de pagamento:\n\n"
            f"ðŸ”— {link}\n\n"
            f"ApÃ³s o pagamento ser confirmado, seu acesso Ã© ativado automaticamente "
            f"e vamos comeÃ§ar a criar suas fichas! ðŸŽ‰")

        dados_estado = {"metodo_pagamento": metodo}
        if metodo == "cartao":
            dados_estado["payment_link_id"] = pagamento.get("payment_link_id", "")
        else:
            dados_estado["payment_id"] = pagamento.get("payment_id", "")
        banco.set_estado(telefone, "aguardando_pagamento", dados_estado)

    except Exception as e:
        # Log completo para o terminal e ficheiro
        print(f"ERRO ASAAS DETALHADO: {str(e)}")
        logging.error(f"ERRO ASAAS DETALHADO: {str(e)}")
        if isinstance(e, requests.exceptions.HTTPError) and hasattr(e, 'response') and e.response is not None:
            print(f"ERRO ASAAS RESPONSE BODY: {e.response.text}")
            logging.error(f"ERRO ASAAS RESPONSE BODY: {e.response.text}")
        logging.error(traceback.format_exc())

        erro_body = e.response.text if isinstance(e, requests.exceptions.HTTPError) and hasattr(e, 'response') and e.response is not None else ""
        if metodo == "pix" and "Pix" in erro_body:
            whatsapp.enviar_texto(
                telefone,
                "O Pix ainda nao esta habilitado nesta conta do Asaas.\n\n"
                "Enquanto isso, eu consigo te enviar o link em *cartao de credito* sem boleto. "
                "Responda *CARTAO* para continuar.",
            )
            banco.set_estado(telefone, "escolha_pagamento_assinatura", {})
            return

        whatsapp.enviar_texto(telefone,
            "Desculpe, tive um problema tÃ©cnico ao gerar seu link de pagamento. ðŸ˜”\n\n"
            "Por favor, entre em contato com o suporte da Mindhub para completar sua assinatura:\n"
            f"ðŸ“± WhatsApp: {config.GESTOR_WHATSAPP}\n\n"
            "Enquanto isso, responda *ASSINAR* para tentar novamente!")

        # Alerta para o gestor
        if config.GESTOR_WHATSAPP:
            whatsapp.enviar_texto(config.GESTOR_WHATSAPP,
                f"ðŸš¨ *Alerta Mindnutri â€” Asaas Falhou*\n\n"
                f"Cliente {telefone} tentou assinar mas o Asaas retornou erro:\n"
                f"{str(e)[:200]}\n\n"
                f"Verifique a integraÃ§Ã£o.")

        # NÃƒO muda estado â€” mantÃ©m em demonstracao_assinar para retry
        return


# â”€â”€ MENU PRINCIPAL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _enviar_menu_principal(telefone: str, assinante: dict):
    nome = assinante.get("nome") or "cliente"
    fichas_rest = assinante["fichas_limite_mes"] - assinante["fichas_geradas_mes"]
    whatsapp.enviar_texto(telefone,
        f"OlÃ¡, {nome}! ðŸ‘‹ Como posso te ajudar hoje?\n\n"
        f"ðŸ“‹ *1* â€” Criar ficha tÃ©cnica (XLSX)\n"
        f"ðŸ“„ *2* â€” Criar ficha operacional (PDF)\n"
        f"ðŸ’° *3* â€” Calcular custo rÃ¡pido de um prato\n"
        f"ðŸ“¦ *4* â€” Ver meus ingredientes cadastrados\n\n"
        f"Fichas disponÃ­veis este mÃªs: *{fichas_rest}/30*\n\n"
        "Responda com o nÃºmero ou descreva o que precisa!")


# â”€â”€ FLUXO PRINCIPAL DE CRIAÃ‡ÃƒO DE FICHA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _fluxo_criacao_ficha(telefone: str, texto: str, estado: dict, assinante: dict):
    """
    Delega toda a lÃ³gica de criaÃ§Ã£o de ficha para a IA,
    mantendo contexto via histÃ³rico de conversa.
    """
    _conversar_com_ia(telefone, texto, assinante)


def _fluxo_confirmacao_geracao(telefone: str, texto: str, estado: dict, assinante: dict):
    """Aguarda confirmaÃ§Ã£o do cliente para gerar o arquivo."""
    if any(p in texto.lower() for p in ["sim", "gera", "pode", "ok", "yes", "confirma", "ðŸ‘"]):
        dados = estado.get("dados", {})
        tipo  = dados.get("tipo_geracao", "tecnica")
        _gerar_e_enviar_arquivo(telefone, dados, tipo, assinante)
        banco.resetar_estado(telefone)
    else:
        banco.resetar_estado(telefone)
        whatsapp.enviar_texto(telefone,
            "Ok, cancelei a geraÃ§Ã£o. Se quiser ajustar algo, Ã© sÃ³ me dizer! ðŸ˜Š")


def _eh_resposta_sim(texto: str) -> bool:
    texto_limpo = (texto or "").lower().strip()
    return any(p in texto_limpo for p in ("sim", "s", "quero", "gera", "ok", "pode", "yes"))


def _eh_resposta_nao(texto: str) -> bool:
    texto_limpo = (texto or "").lower().strip()
    return any(p in texto_limpo for p in ("nao", "não", "n", "agora nao", "agora não", "dispenso"))


def _normalizar_lista_modo_preparo(texto: str) -> list[str]:
    bruto = (texto or "").strip()
    if not bruto:
        return []

    linhas = [l.strip(" -•\t") for l in bruto.splitlines() if l.strip()]
    if len(linhas) == 1:
        linhas = [p.strip() for p in re.split(r";\s*", linhas[0]) if p.strip()]

    if not linhas:
        return []

    passos = []
    for linha in linhas:
        passo = re.sub(r"^\d+[\)\.\-:\s]+", "", linha).strip()
        if passo:
            passos.append(passo)
    return passos


def _salvar_foto_prato_operacional(telefone: str, midia_bytes: bytes) -> str | None:
    try:
        nome_foto = f"foto_prato_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        caminho = storage.salvar_arquivo(telefone, nome_foto, dados=midia_bytes)
        print(f"[Fluxo PDF] Foto salva em: {caminho}")
        return caminho
    except Exception as e:
        print(f"[Fluxo PDF] Falha ao salvar foto do prato: {e}")
        return None


def _formatar_qtd_operacional(valor, unidade: str) -> str:
    try:
        num = float(valor)
        if num.is_integer():
            txt = str(int(num))
        else:
            txt = f"{num:.3f}".rstrip("0").rstrip(".")
    except Exception:
        txt = str(valor or "").strip()

    unidade_limpa = (unidade or "").strip()
    return f"{txt} {unidade_limpa}".strip()


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


def _iniciar_fluxo_pos_coleta_tecnica(telefone: str, dados_tecnica: dict):
    dados_fluxo = {
        "tecnica_dados": dados_tecnica,
        "modo_preparo": dados_tecnica.get("modo_preparo", []),
        "foto_path": "",
    }
    banco.set_estado(telefone, "aguardando_decisao_ficha_operacional", dados_fluxo)
    whatsapp.enviar_texto(
        telefone,
        "Deseja gerar também a Ficha Operacional ilustrada em PDF para sua cozinha?",
    )
    print(f"[Fluxo PDF] Pergunta de complemento enviada para {telefone}")


def _finalizar_fluxo_geracao_integrada(telefone: str, fluxo: dict, assinante: dict):
    dados_tecnica = dict(fluxo.get("tecnica_dados") or {})
    gerar_operacional = bool(fluxo.get("gerar_operacional"))

    if gerar_operacional:
        dados_combo = _montar_dados_operacionais(
            dados_tecnica,
            foto_path=fluxo.get("foto_path", ""),
            modo_preparo=fluxo.get("modo_preparo") or dados_tecnica.get("modo_preparo", []),
        )
        print(f"[Fluxo PDF] Gerando combo tecnica+operacional para {telefone}")
        _gerar_e_enviar_arquivo(telefone, dados_combo, "combo", assinante)
    else:
        print(f"[Fluxo PDF] Gerando somente ficha tecnica para {telefone}")
        _gerar_e_enviar_arquivo(telefone, dados_tecnica, "tecnica", assinante)

    banco.resetar_estado(telefone)


def _avancar_coleta_operacional(telefone: str, fluxo: dict, assinante: dict):
    foto_path = (fluxo.get("foto_path") or "").strip()
    modo_preparo = fluxo.get("modo_preparo") or []

    if not foto_path:
        banco.set_estado(telefone, "aguardando_foto_operacional", fluxo)
        whatsapp.enviar_texto(
            telefone,
            "Perfeito! Me envie agora a foto do prato para montar a ficha operacional ilustrada.",
        )
        print(f"[Fluxo PDF] Aguardando foto do prato de {telefone}")
        return

    if not modo_preparo:
        banco.set_estado(telefone, "aguardando_modo_preparo_operacional", fluxo)
        whatsapp.enviar_texto(
            telefone,
            "Agora me envie o modo de preparo (passo a passo) para completar o PDF operacional.",
        )
        print(f"[Fluxo PDF] Aguardando modo de preparo de {telefone}")
        return

    _finalizar_fluxo_geracao_integrada(telefone, fluxo, assinante)


def _fluxo_decisao_ficha_operacional(telefone: str, texto: str, estado: dict, assinante: dict):
    fluxo = estado.get("dados", {})

    if _eh_resposta_sim(texto):
        fluxo["gerar_operacional"] = True
        fluxo["modo_preparo"] = fluxo.get("modo_preparo") or fluxo.get("tecnica_dados", {}).get("modo_preparo", [])
        banco.set_estado(telefone, "aguardando_decisao_ficha_operacional", fluxo)
        print(f"[Fluxo PDF] Cliente {telefone} optou por gerar PDF operacional.")
        _avancar_coleta_operacional(telefone, fluxo, assinante)
        return

    if _eh_resposta_nao(texto):
        fluxo["gerar_operacional"] = False
        whatsapp.enviar_texto(telefone, "Perfeito! Vou gerar agora somente a Ficha Tecnica em Excel.")
        print(f"[Fluxo PDF] Cliente {telefone} optou por gerar somente tecnica.")
        _finalizar_fluxo_geracao_integrada(telefone, fluxo, assinante)
        return

    whatsapp.enviar_texto(
        telefone,
        "Me confirma com *SIM* para gerar o PDF operacional tambem, ou *NAO* para seguir apenas com o Excel.",
    )


def _fluxo_oferecendo_pdf(telefone: str, texto: str, estado: dict, assinante: dict):
    """
    Compatibilidade de estado: delega para o fluxo legado de decisao do PDF.
    """
    _fluxo_decisao_ficha_operacional(telefone, texto, estado, assinante)


def _fluxo_coletando_foto_preparo(telefone: str, texto: str, estado: dict, assinante: dict):
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


def _fluxo_coleta_foto_operacional(telefone: str, texto: str, estado: dict, assinante: dict):
    fluxo = estado.get("dados", {})
    texto_limpo = (texto or "").strip()

    if texto_limpo.startswith("[FOTO_PRATO]"):
        fluxo["foto_path"] = texto_limpo.replace("[FOTO_PRATO]", "", 1).strip()
        banco.set_estado(telefone, "aguardando_foto_operacional", fluxo)
        whatsapp.enviar_texto(telefone, "Foto recebida com sucesso! ✅")
        _avancar_coleta_operacional(telefone, fluxo, assinante)
        return

    if any(p in texto_limpo.lower() for p in ("sem foto", "pular foto", "nao tenho foto", "não tenho foto")):
        fluxo["foto_path"] = ""
        banco.set_estado(telefone, "aguardando_foto_operacional", fluxo)
        whatsapp.enviar_texto(
            telefone,
            "Sem problemas. Podemos seguir sem foto, mas o PDF fica melhor com imagem. Me envie o modo de preparo.",
        )
        fluxo["modo_preparo"] = fluxo.get("modo_preparo") or []
        banco.set_estado(telefone, "aguardando_modo_preparo_operacional", fluxo)
        return

    whatsapp.enviar_texto(
        telefone,
        "Ainda preciso da foto do prato. Envie uma imagem para continuar.",
    )


def _fluxo_coleta_modo_preparo_operacional(telefone: str, texto: str, estado: dict, assinante: dict):
    fluxo = estado.get("dados", {})
    passos = _normalizar_lista_modo_preparo(texto)

    if not passos:
        whatsapp.enviar_texto(
            telefone,
            "Nao consegui identificar o passo a passo. Pode enviar o modo de preparo em texto (um passo por linha)?",
        )
        return

    fluxo["modo_preparo"] = passos
    banco.set_estado(telefone, "aguardando_modo_preparo_operacional", fluxo)
    print(f"[Fluxo PDF] Modo de preparo recebido ({len(passos)} passos) para {telefone}")
    _finalizar_fluxo_geracao_integrada(telefone, fluxo, assinante)


# â”€â”€ CONVERSA COM IA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _conversar_com_ia(telefone: str, texto: str, assinante: dict):
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

    contexto_extra = f"""
CONTEXTO DO CLIENTE:
- Nome: {assinante.get('nome', 'nÃ£o informado')}
- Estabelecimento: {assinante.get('estabelecimento', 'nÃ£o informado')}
- Nicho: {assinante.get('nicho', 'nÃ£o informado')}
- Cidade: {assinante.get('cidade', 'nÃ£o informado')}
- Fichas restantes este mÃªs: {fichas_rest}
- Ingredientes jÃ¡ cadastrados: {', '.join(nomes_ing) if nomes_ing else 'nenhum ainda'}
"""

    system_com_contexto = SYSTEM_PROMPT + "\n\n" + contexto_extra
    
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
        modelo_escolhido = getattr(config, 'OPENAI_MODEL', 'gpt-4o')

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
                    print(f"Erro ao decodificar argumentos da funÃ§Ã£o {tool_name}")
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
        print(f"[OpenAI] Erro: {safe_msg}")
        logging.error(f"[OpenAI] Erro: {safe_msg}")
        _registrar_falha(telefone, assinante)


# â”€â”€ GERAÃ‡ÃƒO E ENVIO DE ARQUIVOS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _gerar_e_enviar_arquivo(telefone: str, dados: dict, tipo: str, assinante: dict):
    """Gera e envia arquivo(s). Se tipo='combo', gera XLSX+PDF com um unico consumo de credito."""
    nome_prato = dados.get("nome_prato", "preparo")
    nome_prato_limpo = str(nome_prato).strip()

    try:
        if tipo == "combo":
            whatsapp.enviar_texto(
                telefone,
                f"⏳ Gerando sua Ficha Tecnica e a Ficha Operacional de *{nome_prato_limpo}*... aguarde um instante!",
            )
        else:
            whatsapp.enviar_texto(
                telefone,
                f"⏳ Gerando sua ficha de *{nome_prato_limpo}*... aguarde um instante!",
            )

        cobrar_credito = _deve_consumir_credito_por_prato(telefone, nome_prato_limpo)
        print(f"[Credito] prato={nome_prato_limpo} cobrar_credito={cobrar_credito} tipo={tipo}")

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
            print(f"[Gerador] Combo concluido: tecnica={caminho_tecnica} operacional={caminho_operacional}")
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
            print(f"[Gerador] Arquivo {tipo} concluido: {caminho_final}")

        if cobrar_credito:
            banco.incrementar_ficha(telefone)
            print(f"[Credito] +1 credito aplicado para {telefone} ({nome_prato_limpo})")
        else:
            print(f"[Credito] Nenhum credito adicional para {telefone} ({nome_prato_limpo})")

        _salvar_ingredientes_da_ficha(telefone, dados)

        assinante_atualizado = banco.get_assinante(telefone)
        fichas_rest = assinante_atualizado["fichas_limite_mes"] - assinante_atualizado["fichas_geradas_mes"]
        whatsapp.enviar_texto(
            telefone,
            f"✅ Ficha gerada com sucesso!\n\n"
            f"Fichas restantes este mes: *{fichas_rest}/30*\n\n"
            "Quer criar outra ficha ou calcular algum custo?",
        )

    except Exception as e:
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        print(f"[Gerador] Erro ao gerar arquivo: {safe_msg}")
        whatsapp.enviar_texto(
            telefone,
            "⚠️ Ocorreu um erro ao gerar a ficha. Nossa equipe foi notificada. "
            "Tente novamente em instantes!",
        )
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
        print(f"[Gerador] {tipo_arquivo} enviado para {telefone}: {caminho_final}")
        return caminho_final


def _registrar_ficha_gerada(telefone: str, dados: dict, tipo: str, nome_prato: str, caminho_final: str):
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
    print(f"[Banco] Ficha registrada tipo={tipo} prato={nome_prato}")


def _salvar_ingredientes_da_ficha(telefone: str, dados: dict):
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
        print(f"[Banco] Ingredientes atualizados: {len(ingredientes)} item(ns)")


def _calcular_custo_total(dados: dict) -> float:
    total = 0.0
    for ing in dados.get("ingredientes", []):
        total += ing.get("custo_unit", 0) * ing.get("peso_liquido", 0)
    return round(total, 2)


# â”€â”€ FALHAS E ALERTAS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _registrar_falha(telefone: str, assinante: dict):
    _falhas[telefone] = _falhas.get(telefone, 0) + 1
    qtd = _falhas[telefone]

    if qtd == 1:
        whatsapp.enviar_texto(telefone,
            "NÃ£o consegui entender sua mensagem. Pode repetir de outra forma? ðŸ˜Š")
    elif qtd == 2:
        whatsapp.enviar_texto(telefone,
            "Ainda nÃ£o consegui entender. Tente descrever o que precisa em poucas palavras.")
    elif qtd >= 3:
        _falhas[telefone] = 0
        whatsapp.enviar_texto(telefone,
            "Parece que estou com dificuldade em entender. "
            "Vou acionar nossa equipe para te ajudar em breve! ðŸ™")
        # Alerta para o gestor
        nome = assinante.get("nome", telefone)
        banco.criar_notificacao(
            "sem_entender", "aviso",
            "Agente nÃ£o entendeu cliente",
            f"{nome} ({telefone}) enviou 3 mensagens que o agente nÃ£o conseguiu interpretar.",
            telefone
        )
        if config.GESTOR_WHATSAPP:
            whatsapp.enviar_texto(
                config.GESTOR_WHATSAPP,
                f"âš ï¸ Alerta Mindnutri\n\n"
                f"O cliente *{nome}* ({telefone}) enviou 3 mensagens que o agente nÃ£o conseguiu interpretar.\n"
                f"Pode ser necessÃ¡rio atendimento manual."
            )


def _enviar_link_renovacao(telefone: str, assinante: dict, metodo: str):
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

        whatsapp.enviar_texto(
            telefone,
            f"Aqui esta seu link para renovacao via *{metodo}*:\n\nðŸ”— {link}\n\n"
            "Apos o pagamento, suas fichas sao renovadas automaticamente.",
        )
    except Exception:
        whatsapp.enviar_texto(
            telefone,
            "Em instantes nossa equipe te enviara o link de renovacao.",
        )

