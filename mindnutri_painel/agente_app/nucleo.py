import json
import re
import os
import tempfile
from datetime import datetime
from pathlib import Path

import openai

from django.conf import settings as config
from agente_app.prompt import SYSTEM_PROMPT
from utils import banco, whatsapp, midia, storage
from agente_app.gerador import xlsx_gerador, pdf_gerador

_gpt = openai.OpenAI(api_key=config.OPENAI_API_KEY)

# Pasta de assets (logo, exemplos)
ASSETS_DIR = Path(__file__).parent.parent / "assets"
EXEMPLOS_DIR = Path(__file__).parent.parent / "exemplos"

# Contador de falhas de entendimento por telefone
_falhas: dict[str, int] = {}


# ── ENTRADA PRINCIPAL ────────────────────────────────────────────

def processar_mensagem(telefone: str, tipo: str, texto: str = None,
                        midia_id: str = None, midia_bytes: bytes = None):
    """
    Ponto de entrada único para todas as mensagens recebidas.
    Chamado pelo webhook do Django.
    """
    # Garante que assinante existe no banco
    if not banco.get_assinante(telefone):
        banco.criar_assinante(telefone)

    assinante = banco.get_assinante(telefone)
    estado    = banco.get_estado(telefone)

    # ── Processar mídia ──────────────────────────────────────────
    if tipo == "audio" and midia_bytes:
        texto_transcrito = midia.transcrever_audio(midia_bytes)
        if not texto_transcrito:
            _registrar_falha(telefone, assinante)
            return
        texto = texto_transcrito

    elif tipo == "imagem" and midia_bytes:
        ingredientes_extraidos = midia.extrair_ingredientes_de_imagem(midia_bytes)
        texto = f"[IMAGEM ENVIADA]\nIngredientes identificados na imagem:\n{ingredientes_extraidos}"

    elif tipo == "documento" and midia_bytes:
        texto = "[DOCUMENTO ENVIADO] O cliente enviou um documento para análise."

    if not texto:
        whatsapp.enviar_texto(telefone, "N\u00e3o consegui entender sua mensagem. Pode repetir por texto?")
        return

    # ── Verificar fluxo de onboarding ────────────────────────────
    if assinante["status"] == "pendente":
        _fluxo_boas_vindas(telefone, texto, estado, assinante)
        return

    if assinante["status"] in ("bloqueado", "inadimplente"):
        whatsapp.enviar_texto(telefone,
            "⚠️ Seu acesso está suspenso no momento.\n\n"
            "Para regularizar sua assinatura, acesse o link de pagamento ou entre em contato com o suporte Mindhub.")
        return

    if assinante["status"] == "cancelado":
        whatsapp.enviar_texto(telefone,
            "Sua assinatura foi cancelada. Para reativar, entre em contato com a Mindhub. 💙")
        return

    # ── Verificar comandos especiais ────────────────────────────
    texto_lower = texto.lower().strip()

    if texto_lower in ("cancelar", "recomeçar", "reiniciar", "menu", "/menu"):
        banco.resetar_estado(telefone)
        _enviar_menu_principal(telefone, assinante)
        return

    # ── Fluxo de demonstração (não-assinante em fluxo de venda) ──
    if estado["estado"] == "demonstracao":
        _fluxo_demonstracao(telefone, texto, estado, assinante)
        return

    # ── Verificar fichas disponíveis antes de criar ───────────────
    fichas_rest = assinante["fichas_limite_mes"] - assinante["fichas_geradas_mes"]
    if fichas_rest <= 3 and fichas_rest > 0:
        # Aviso proativo (uma vez)
        dados_est = estado.get("dados", {})
        if not dados_est.get("aviso_limite_enviado"):
            whatsapp.enviar_texto(telefone,
                f"⚠️ Atenção: você tem apenas *{fichas_rest} fichas restantes* este mês.")
            dados_est["aviso_limite_enviado"] = True
            banco.set_estado(telefone, estado["estado"], dados_est)

    if fichas_rest <= 0:
        whatsapp.enviar_texto(telefone,
            "⚠️ Você atingiu o limite de 30 fichas este mês.\n\n"
            "Deseja renovar antecipadamente? Responda *SIM* para receber o link de pagamento.")
        banco.set_estado(telefone, "aguardando_renovacao", {})
        return

    # ── Delegação por estado ─────────────────────────────────────
    estado_atual = estado["estado"]

    if estado_atual == "aguardando_renovacao":
        if "sim" in texto_lower:
            _enviar_link_renovacao(telefone, assinante)
        else:
            banco.resetar_estado(telefone)
            _enviar_menu_principal(telefone, assinante)
        return

    if estado_atual.startswith("criando_ficha"):
        _fluxo_criacao_ficha(telefone, texto, estado, assinante)
        return

    if estado_atual == "aguardando_confirmacao_geracao":
        _fluxo_confirmacao_geracao(telefone, texto, estado, assinante)
        return

    # ── Estado geral: conversa com a IA ─────────────────────────────
    _conversar_com_ia(telefone, texto, assinante)


# ── FLUXO DE BOAS-VINDAS (primeiro contato / cadastro) ──────────

def _fluxo_boas_vindas(telefone: str, texto: str, estado: dict, assinante: dict):
    """Fluxo de primeiro contato e demonstração antes de assinar."""
    est = estado["estado"]

    if est == "inicio":
        banco.set_estado(telefone, "demonstracao_inicio", {})
        resp = (
            "Olá! 👋 Bem-vindo ao *Mindnutri*, o agente de IA especializado em fichas técnicas da Mindhub!\n\n"
            "Sou capaz de criar fichas técnicas profissionais em Excel, fichas operacionais em PDF "
            "e calcular custos de pratos — tudo aqui pelo WhatsApp. 📋\n\n"
            "Quer ver um exemplo do que consigo fazer antes de assinar?\n\n"
            "Responda *SIM* para ver um exemplo grátis agora!"
        )
        whatsapp.enviar_texto(telefone, resp)
        return

    if est == "demonstracao_inicio":
        if "sim" in texto.lower() or "quero" in texto.lower():
            banco.set_estado(telefone, "demonstracao_escolha_nicho", {})
            whatsapp.enviar_texto(telefone,
                "Ótimo! Escolha um nicho para ver o exemplo:\n\n"
                "1️⃣ Hambúrguer\n"
                "2️⃣ Pizza\n"
                "3️⃣ Sobremesa\n\n"
                "Responda com o número ou nome do nicho.")
        else:
            whatsapp.enviar_texto(telefone,
                "Tudo bem! Quando quiser conhecer o Mindnutri, é só chamar. 😊")
        return

    if est == "demonstracao_escolha_nicho":
        _enviar_exemplo_por_nicho(telefone, texto)
        banco.set_estado(telefone, "demonstracao_pos_exemplo", {})
        return

    if est == "demonstracao_pos_exemplo":
        banco.set_estado(telefone, "demonstracao_assinar", {})
        whatsapp.enviar_texto(telefone,
            "Gostou? Com o Mindnutri você cria fichas assim para todos os seus pratos, "
            "com seus ingredientes, seus custos e sua marca. 🚀\n\n"
            f"*Plano Mensal: R$ {config.PLANO_VALOR:.2f}/mês*\n"
            "✅ 30 fichas por mês\n"
            "✅ XLSX + PDF profissionais\n"
            "✅ Cálculo de custos instantâneo\n"
            "✅ Base de ingredientes sempre atualizada\n\n"
            "Quer assinar agora?\n\n"
            "Responda *ASSINAR* para receber o link de pagamento.")
        return

    if est == "demonstracao_assinar":
        if "assinar" in texto.lower() or "sim" in texto.lower() or "quero" in texto.lower():
            _iniciar_assinatura(telefone)
        else:
            whatsapp.enviar_texto(telefone,
                "Sem problema! Quando quiser assinar, é só responder *ASSINAR*. 😊")
        return


def _enviar_exemplo_por_nicho(telefone: str, texto: str):
    """Envia os arquivos de exemplo para o nicho escolhido."""
    texto_lower = texto.lower()

    if "1" in texto or "hamburguer" in texto_lower or "hambúrguer" in texto_lower or "burger" in texto_lower:
        nicho = "hamburguer"
    elif "2" in texto or "pizza" in texto_lower:
        nicho = "pizza"
    elif "3" in texto or "sobremesa" in texto_lower or "brownie" in texto_lower or "doce" in texto_lower:
        nicho = "sobremesa"
    else:
        nicho = "hamburguer"  # default

    whatsapp.enviar_texto(telefone,
        f"Perfeito! Veja aqui um exemplo de ficha técnica e ficha operacional "
        f"para o segmento de *{nicho.capitalize()}*: 📋")

    xlsx_path = EXEMPLOS_DIR / f"exemplo_{nicho}.xlsx"
    pdf_path  = EXEMPLOS_DIR / f"exemplo_{nicho}.pdf"

    if xlsx_path.exists():
        whatsapp.enviar_arquivo(str(xlsx_path),
            caption=f"Ficha Técnica — {nicho.capitalize()} (XLSX)")

    if pdf_path.exists():
        whatsapp.enviar_arquivo(str(pdf_path),
            caption=f"Ficha Operacional — {nicho.capitalize()} (PDF)")


def _iniciar_assinatura(telefone: str):
    """Gera link de pagamento no Asaas e envia para o cliente."""
    try:
        from utils.asaas import criar_cobranca_assinatura
        link = criar_cobranca_assinatura(telefone)
        whatsapp.enviar_texto(telefone,
            f"Ótimo! Aqui está seu link de pagamento:\n\n"
            f"🔗 {link}\n\n"
            f"Após o pagamento ser confirmado, seu acesso é ativado automaticamente "
            f"e vamos começar a criar suas fichas! 🎉")
    except Exception as e:
        print(f"[Asaas] Erro ao criar cobrança: {e}")
        whatsapp.enviar_texto(telefone,
            "Vou te passar o link de pagamento em instantes. "
            "Nossa equipe entrará em contato em breve! 😊")
    banco.set_estado(telefone, "aguardando_pagamento", {})


# ── MENU PRINCIPAL ───────────────────────────────────────────────

def _enviar_menu_principal(telefone: str, assinante: dict):
    nome = assinante.get("nome") or "cliente"
    fichas_rest = assinante["fichas_limite_mes"] - assinante["fichas_geradas_mes"]
    whatsapp.enviar_texto(telefone,
        f"Olá, {nome}! 👋 Como posso te ajudar hoje?\n\n"
        f"📋 *1* — Criar ficha técnica (XLSX)\n"
        f"📄 *2* — Criar ficha operacional (PDF)\n"
        f"💰 *3* — Calcular custo rápido de um prato\n"
        f"📦 *4* — Ver meus ingredientes cadastrados\n\n"
        f"Fichas disponíveis este mês: *{fichas_rest}/30*\n\n"
        "Responda com o número ou descreva o que precisa!")


# ── FLUXO PRINCIPAL DE CRIAÇÃO DE FICHA ──────────────────────────

def _fluxo_criacao_ficha(telefone: str, texto: str, estado: dict, assinante: dict):
    """
    Delega toda a lógica de criação de ficha para a IA,
    mantendo contexto via histórico de conversa.
    """
    _conversar_com_ia(telefone, texto, assinante)


def _fluxo_confirmacao_geracao(telefone: str, texto: str, estado: dict, assinante: dict):
    """Aguarda confirmação do cliente para gerar o arquivo."""
    if any(p in texto.lower() for p in ["sim", "gera", "pode", "ok", "yes", "confirma", "👍"]):
        dados = estado.get("dados", {})
        tipo  = dados.get("tipo_geracao", "tecnica")
        _gerar_e_enviar_arquivo(telefone, dados, tipo, assinante)
        banco.resetar_estado(telefone)
    else:
        banco.resetar_estado(telefone)
        whatsapp.enviar_texto(telefone,
            "Ok, cancelei a geração. Se quiser ajustar algo, é só me dizer! 😊")


# ── CONVERSA COM IA ──────────────────────────────────────────────

def _conversar_com_ia(telefone: str, texto: str, assinante: dict):
    """
    Envia mensagem para a IA com todo o contexto e retorna resposta.
    Detecta quando a IA quer gerar um arquivo.
    """
    # Salva mensagem do usuário
    banco.salvar_mensagem(telefone, "user", texto)

    # Monta histórico
    historico = banco.get_historico(telefone, limite=20)

    # Contexto do assinante
    ingredientes_cadastrados = banco.get_ingredientes(telefone)
    nomes_ing = [i["nome"] for i in ingredientes_cadastrados[:30]]
    fichas_rest = assinante["fichas_limite_mes"] - assinante["fichas_geradas_mes"]

    contexto_extra = f"""
CONTEXTO DO CLIENTE:
- Nome: {assinante.get('nome', 'não informado')}
- Estabelecimento: {assinante.get('estabelecimento', 'não informado')}
- Nicho: {assinante.get('nicho', 'não informado')}
- Cidade: {assinante.get('cidade', 'não informado')}
- Fichas restantes este mês: {fichas_rest}
- Ingredientes já cadastrados: {', '.join(nomes_ing) if nomes_ing else 'nenhum ainda'}
"""

    system_com_contexto = SYSTEM_PROMPT + "\n\n" + contexto_extra
    
    # Prepara mensagens para OpenAI (System prompt embutido no histórico)
    mensagens_openai = [{"role": "system", "content": system_com_contexto}] + historico

    try:
        # Detecta se deve gerar arquivo via ferramenta (formato OpenAI)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "gerar_ficha_tecnica",
                    "description": "Gera a ficha técnica em XLSX quando todos os dados foram coletados e o cliente confirmou a geração.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nome_prato":     {"type": "string"},
                            "classificacao":  {"type": "string"},
                            "codigo":         {"type": "string"},
                            "peso_porcao_kg": {"type": "number"},
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
                            "nome_prato":      {"type": "string"},
                            "classificacao":   {"type": "string"},
                            "codigo":          {"type": "string"},
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
                    "description": "Salva ingredientes na base do cliente após coletar nome, unidade, custo, FC e IC.",
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

        # Configuração do modelo caso não tenha sido migrada
        # (Presumimos que CLAUDE_MODEL virou OPENAI_MODEL ou iteramos)
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
            # Salvar no histórico que a ação foi tomada para a IA não repetir infinitamente
            msg_salvar = texto_resposta if texto_resposta else "[Arquivo gerado e enviado ao cliente]"
            banco.salvar_mensagem(telefone, "assistant", msg_salvar)

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                
                # A OpenAI retorna os argumentos em formato string JSON
                try:
                    tool_input = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    print(f"Erro ao decodificar argumentos da função {tool_name}")
                    continue

                if tool_name == "gerar_ficha_tecnica":
                    if texto_resposta:
                        whatsapp.enviar_texto(telefone, texto_resposta)
                    tool_input["estabelecimento"] = assinante.get("estabelecimento", "")
                    _gerar_e_enviar_arquivo(telefone, tool_input, "tecnica", assinante)

                elif tool_name == "gerar_ficha_operacional":
                    if texto_resposta:
                        whatsapp.enviar_texto(telefone, texto_resposta)
                    tool_input["estabelecimento"] = assinante.get("estabelecimento", "")
                    _gerar_e_enviar_arquivo(telefone, tool_input, "operacional", assinante)

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
                    if texto_resposta:
                        whatsapp.enviar_texto(telefone, texto_resposta)
                    # For salvar_ingredientes, replace the auto-msg if it was empty
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
        _registrar_falha(telefone, assinante)


# ── GERAÇÃO E ENVIO DE ARQUIVOS ──────────────────────────────────

def _gerar_e_enviar_arquivo(telefone: str, dados: dict, tipo: str, assinante: dict):
    """Gera o arquivo e envia via WhatsApp."""
    nome_prato = dados.get("nome_prato", "preparo")

    try:
        whatsapp.enviar_texto(telefone,
            f"⏳ Gerando sua ficha de *{nome_prato}*... aguarde um instante!")

        with tempfile.TemporaryDirectory() as tmpdir:
            nome_arquivo = storage.gerar_nome_arquivo(telefone, nome_prato, tipo)
            caminho_tmp  = os.path.join(tmpdir, nome_arquivo)

            if tipo == "tecnica":
                xlsx_gerador.gerar_ficha_xlsx(dados, caminho_tmp)
                caption = f"📊 Ficha Técnica — {nome_prato}"
            else:
                pdf_gerador.gerar_ficha_pdf(dados, caminho_tmp)
                caption = f"📄 Ficha Operacional — {nome_prato}"

            # Salva no storage permanente
            caminho_final = storage.salvar_arquivo(
                telefone, nome_arquivo, caminho_origem=caminho_tmp
            )

            # Envia via WhatsApp
            whatsapp.enviar_arquivo(telefone, caminho_final, caption=caption)

        # Registra no banco
        custo_total  = _calcular_custo_total(dados)
        peso_porcao  = dados.get("peso_porcao_kg", 0.1)
        ingredientes = dados.get("ingredientes", [])
        rendimento   = sum(i.get("peso_liquido",0) * i.get("ic",1) for i in ingredientes)
        num_porcoes  = rendimento / peso_porcao if peso_porcao > 0 else 0

        banco.salvar_ficha(telefone, {
            "nome_prato":   nome_prato,
            "tipo":         tipo,
            "codigo":       dados.get("codigo", ""),
            "custo_total":  custo_total,
            "custo_porcao": custo_total / num_porcoes if num_porcoes > 0 else 0,
            "num_porcoes":  round(num_porcoes, 1),
            "arquivo_path": caminho_final,
        })
        banco.incrementar_ficha(telefone)

        # Salva ingredientes na base do cliente
        for ing in ingredientes:
            banco.salvar_ingrediente(
                telefone,
                ing.get("nome", ""),
                ing.get("unidade", "kg"),
                ing.get("custo_unit", 0),
                ing.get("fc", 1.0),
                ing.get("ic", 1.0),
            )

        # Mensagem de confirmação
        assinante_atualizado = banco.get_assinante(telefone)
        fichas_rest = assinante_atualizado["fichas_limite_mes"] - assinante_atualizado["fichas_geradas_mes"]
        whatsapp.enviar_texto(telefone,
            f"✅ Ficha gerada com sucesso!\n\n"
            f"Fichas restantes este mês: *{fichas_rest}/30*\n\n"
            "Quer criar outra ficha ou calcular algum custo? 😊")

    except Exception as e:
        safe_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        print(f"[Gerador] Erro ao gerar arquivo: {safe_msg}")
        whatsapp.enviar_texto(telefone,
            "⚠️ Ocorreu um erro ao gerar a ficha. Nossa equipe foi notificada. "
            "Tente novamente em instantes!")
        banco.criar_notificacao(
            "erro_sistema", "critico",
            "Erro na geração de arquivo",
            f"Erro ao gerar {tipo} para {nome_prato} — {telefone}: {e}",
            telefone
        )


def _calcular_custo_total(dados: dict) -> float:
    total = 0.0
    for ing in dados.get("ingredientes", []):
        total += ing.get("custo_unit", 0) * ing.get("peso_liquido", 0)
    return round(total, 2)


# ── FALHAS E ALERTAS ─────────────────────────────────────────────

def _registrar_falha(telefone: str, assinante: dict):
    _falhas[telefone] = _falhas.get(telefone, 0) + 1
    qtd = _falhas[telefone]

    if qtd == 1:
        whatsapp.enviar_texto(telefone,
            "Não consegui entender sua mensagem. Pode repetir de outra forma? 😊")
    elif qtd == 2:
        whatsapp.enviar_texto(telefone,
            "Ainda não consegui entender. Tente descrever o que precisa em poucas palavras.")
    elif qtd >= 3:
        _falhas[telefone] = 0
        whatsapp.enviar_texto(telefone,
            "Parece que estou com dificuldade em entender. "
            "Vou acionar nossa equipe para te ajudar em breve! 🙏")
        # Alerta para o gestor
        nome = assinante.get("nome", telefone)
        banco.criar_notificacao(
            "sem_entender", "aviso",
            "Agente não entendeu cliente",
            f"{nome} ({telefone}) enviou 3 mensagens que o agente não conseguiu interpretar.",
            telefone
        )
        if config.GESTOR_WHATSAPP:
            whatsapp.enviar_texto(
                config.GESTOR_WHATSAPP,
                f"⚠️ Alerta Mindnutri\n\n"
                f"O cliente *{nome}* ({telefone}) enviou 3 mensagens que o agente não conseguiu interpretar.\n"
                f"Pode ser necessário atendimento manual."
            )


def _enviar_link_renovacao(telefone: str, assinante: dict):
    try:
        from utils.asaas import criar_cobranca_avulsa
        link = criar_cobranca_avulsa(telefone, config.PLANO_VALOR,
                                      "Renovação antecipada Mindnutri")
        whatsapp.enviar_texto(telefone,
            f"Aqui está seu link para renovação:\n\n🔗 {link}\n\n"
            "Após o pagamento, suas fichas são renovadas automaticamente! ✅")
    except Exception:
        whatsapp.enviar_texto(telefone,
            "Em instantes nossa equipe te enviará o link de renovação. 😊")
