import json
import re
import os
import tempfile
from datetime import datetime
from pathlib import Path
import logging
import traceback

# Configuração de log em arquivo
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

# Pasta de assets (logo, exemplos) — relativa à raiz do projeto Django (mindnutri_painel/)
ASSETS_DIR   = Path(__file__).parent.parent / "assets"
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
    # ── LOG DE ENTRADA ──────────────────────────────────────────
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

    # ── LOG DE DEBUG (TAREFA 3) ─────────────────────────────────
    print(f"[DEBUG] Telefone: {telefone} | Estado Atual: {estado['estado']}")
    logging.info(f"[DEBUG] Telefone: {telefone} | Estado Atual: {estado['estado']} | Status: {assinante['status']}")

    # ── Processar midia ──────────────────────────────────────────
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
        texto = "[DOCUMENTO ENVIADO] O cliente enviou um documento para analise."

    if not texto:
        whatsapp.enviar_texto(telefone, "Nao consegui entender sua mensagem. Pode repetir por texto?")
        return

    # ── Fluxo de onboarding (PRIORIDADE MAXIMA para status 'pendente') ──
    if assinante["status"] == "pendente":
        print(f"[Fluxo] {telefone} pendente -> _fluxo_boas_vindas (estado={estado['estado']})")
        _fluxo_boas_vindas(telefone, texto, estado, assinante)
        return

    if assinante["status"] in ("bloqueado", "inadimplente"):
        whatsapp.enviar_texto(telefone,
            "âš ï¸ Seu acesso estÃ¡ suspenso no momento.\n\n"
            "Para regularizar sua assinatura, acesse o link de pagamento ou entre em contato com o suporte Mindhub.")
        return

        if metodo == "cartao":
            whatsapp.enviar_texto(
                telefone,
                "Perfeito! Aqui esta seu link de pagamento em *cartao de credito*.\n\n"
                f"🔗 {link}\n\n"
                "Esse fluxo ativa a *assinatura mensal automatica* do Mindnutri. "
                "Assim que o pagamento for aprovado, seu acesso sera liberado automaticamente.",
            )
        else:
            mensagem_pix = (
                "Perfeito! Aqui esta seu link de pagamento em *Pix*.\n\n"
                f"🔗 {link}\n\n"
            )
            if codigo_pix:
                mensagem_pix += f"Codigo Pix copia e cola:\n{codigo_pix}\n\n"
            mensagem_pix += (
                "Assim que o pagamento for confirmado, seu acesso sera liberado automaticamente. "
                "Nas renovacoes via Pix, o pagamento segue manual a cada ciclo."
            )
            whatsapp.enviar_texto(telefone, mensagem_pix)
        return

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

    comandos_reset = ["cancelar", "recomeçar", "reiniciar", "menu", "/menu"]

    if texto_lower in comandos_reset:
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

    # ── Estado geral: conversa com a IA ─────────────────────────────
    _conversar_com_ia(telefone, texto, assinante)


# ── FLUXO DE BOAS-VINDAS (primeiro contato / cadastro) ──────────

def _fluxo_boas_vindas(telefone: str, texto: str, estado: dict, assinante: dict):
    """
    Fluxo de primeiro contato: coleta dados pessoais e depois oferece demonstracao.
    Sequencia: boas_vindas_inicio -> coletando_nome -> coletando_cpf
               -> coletando_instagram -> demonstracao_inicio -> escolha_nicho
               -> pos_exemplo -> assinar -> aguardando_pagamento
    """
    est = estado["estado"]
    print(f"[Boas-vindas] {telefone}: estado='{est}', texto='{texto}'")

    # ── 1. Saudacao e pedir o nome ──────────────────────────────
    if est == "boas_vindas_inicio":
        banco.set_estado(telefone, "coletando_nome", {})
        whatsapp.enviar_texto(telefone,
            "Ola! 👋 Bem-vindo ao *Mindnutri*, o agente de IA especializado "
            "em fichas tecnicas da Mindhub!\n\n"
            "Antes de comecarmos, preciso de algumas informacoes rapidas.\n\n"
            "Qual e o seu *nome completo*?")
        return

    # ── 2. Salvar nome e pedir CPF ──────────────────────────────
    if est == "coletando_nome":
        nome = texto.strip()
        if len(nome) < 2:
            whatsapp.enviar_texto(telefone,
                "Por favor, digite seu nome completo (minimo 2 caracteres).")
            return
        banco.atualizar_assinante(telefone, nome=nome)
        banco.set_estado(telefone, "coletando_cpf", {})
        whatsapp.enviar_texto(telefone,
            f"Prazer, *{nome}*! 😊\n\n"
            "Agora preciso do seu *CPF* (apenas numeros, ex: 12345678900).\n"
            "Ele e necessario para gerar o link de pagamento.")
        return

    # ── 3. Salvar CPF e pedir Instagram ─────────────────────────
    if est == "coletando_cpf":
        import re
        cpf_limpo = re.sub(r'\D', '', texto.strip())
        if len(cpf_limpo) != 11:
            whatsapp.enviar_texto(telefone,
                "CPF invalido. Por favor, digite os *11 digitos* do seu CPF (apenas numeros).\n"
                "Exemplo: 12345678900")
            return
        banco.atualizar_assinante(telefone, cpf=cpf_limpo)
        banco.set_estado(telefone, "coletando_instagram", {})
        whatsapp.enviar_texto(telefone,
            "Otimo! Agora me diz: qual e o *@ do Instagram* do seu negocio?\n\n"
            "Exemplo: @minhahamburgeria\n\n"
            "Se nao tiver, digite *NAO*.")
        return

    # ── 4. Salvar Instagram e oferecer demonstracao ─────────────
    if est == "coletando_instagram":
        ig = texto.strip()
        if ig.lower() not in ("nao", "n", "nenhum", "nao tenho", "nao tem"):
            # Garante que tem @
            if not ig.startswith("@"):
                ig = "@" + ig
            banco.atualizar_assinante(telefone, instagram=ig)
        banco.set_estado(telefone, "demonstracao_inicio", {})
        whatsapp.enviar_texto(telefone,
            "Perfeito, tudo anotado! ✅\n\n"
            "Agora vou te mostrar o que o Mindnutri e capaz de fazer. "
            "Posso criar fichas tecnicas profissionais em Excel, fichas operacionais "
            "em PDF e calcular custos de pratos -- tudo aqui pelo WhatsApp. 📋\n\n"
            "Quer ver um *exemplo gratis* antes de assinar?\n\n"
            "Responda *SIM* para ver um exemplo agora!")
        return

    # ── 5. Decidir se quer ver exemplo ──────────────────────────
    if est == "demonstracao_inicio":
        if any(w in texto.lower() for w in ("sim", "quero", "ver", "exemplo", "ok")):
            banco.set_estado(telefone, "demonstracao_escolha_nicho", {})
            whatsapp.enviar_texto(telefone,
                "Otimo! Escolha um nicho para ver o exemplo:\n\n"
                "1 Hamburguer\n"
                "2 Pizza\n"
                "3 Sobremesa\n\n"
                "Responda com o numero ou nome do nicho.")
        else:
            # Pula direto para a oferta de assinatura
            banco.set_estado(telefone, "demonstracao_assinar", {})
            whatsapp.enviar_texto(telefone,
                "Sem problema! Quando quiser ver um exemplo, e so pedir.\n\n"
                f"*Plano Mensal: R$ {config.PLANO_VALOR:.2f}/mes*\n"
                "30 fichas por mes | XLSX + PDF profissionais\n\n"
                "Responda *ASSINAR* para receber o link de pagamento. 😊")
        return

    # ── 6. Escolher nicho e enviar exemplo ──────────────────────
    if est == "demonstracao_escolha_nicho":
        _enviar_exemplo_por_nicho(telefone, texto)
        banco.set_estado(telefone, "demonstracao_pos_exemplo", {})
        return

    # ── 7. Pos-exemplo: oferecer plano ──────────────────────────
    if est == "demonstracao_pos_exemplo":
        banco.set_estado(telefone, "demonstracao_assinar", {})
        whatsapp.enviar_texto(telefone,
            "Gostou? Com o Mindnutri voce cria fichas assim para todos os seus pratos, "
            "com seus ingredientes, seus custos e sua marca. 🚀\n\n"
            f"*Plano Mensal: R$ {config.PLANO_VALOR:.2f}/mes*\n"
            "30 fichas por mes\n"
            "XLSX + PDF profissionais\n"
            "Calculo de custos instantaneo\n"
            "Base de ingredientes sempre atualizada\n\n"
            "Quer assinar agora?\n\n"
            "Responda *ASSINAR* para receber o link de pagamento.")
        return

    # ── 8. Assinar ──────────────────────────────────────────────
    if est == "demonstracao_assinar":
        if any(w in texto.lower() for w in ("assinar", "sim", "quero", "pagar")):
            _pedir_metodo_pagamento(
                telefone,
                "escolha_pagamento_assinatura",
                "Perfeito! Como voce prefere pagar a assinatura?",
            )
        else:
            whatsapp.enviar_texto(telefone,
                "Sem problema! Quando quiser assinar, e so responder *ASSINAR*. 😊")
        return

    # ── 9. Aguardando pagamento ─────────────────────────────────
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
        whatsapp.enviar_texto(telefone,
            "Ainda estamos aguardando a confirmacao do seu pagamento.\n\n"
            "Assim que compensar, seu acesso e liberado automaticamente! 💙\n\n"
            "Se ja pagou e ainda nao foi liberado, aguarde alguns minutos.")
        return

    # ── Fallback: estado desconhecido --> reseta ────────────────
    print(f"[Boas-vindas] Estado desconhecido '{est}' para {telefone}. Resetando...")
    banco.set_estado(telefone, "boas_vindas_inicio", {})
    _fluxo_boas_vindas(telefone, texto, banco.get_estado(telefone), assinante)


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

    print(f"[Exemplos] EXEMPLOS_DIR resolvido para: {EXEMPLOS_DIR.resolve()}")
    print(f"[Exemplos] xlsx_path={xlsx_path} existe={xlsx_path.exists()}")
    print(f"[Exemplos] pdf_path={pdf_path} existe={pdf_path.exists()}")

    enviou_algo = False

    if xlsx_path.exists():
        whatsapp.enviar_arquivo(telefone, str(xlsx_path),
            caption=f"Ficha Técnica — {nicho.capitalize()} (XLSX)")
        enviou_algo = True
    else:
        print(f"ERRO: Arquivo não encontrado em {xlsx_path}")
        logging.error(f"Arquivo de exemplo não encontrado: {xlsx_path}")

    if pdf_path.exists():
        whatsapp.enviar_arquivo(telefone, str(pdf_path),
            caption=f"Ficha Operacional — {nicho.capitalize()} (PDF)")
        enviou_algo = True
    else:
        print(f"ERRO: Arquivo não encontrado em {pdf_path}")
        logging.error(f"Arquivo de exemplo não encontrado: {pdf_path}")

    if not enviou_algo:
        whatsapp.enviar_texto(telefone,
            "Opa, tive um problema técnico ao buscar esse exemplo, "
            "mas você pode assinar para testar com seus dados! 🚀\n\n"
            "Responda *ASSINAR* para começar.")


def _interpretar_metodo_pagamento(texto: str) -> str | None:
    texto_lower = texto.lower().strip()
    if texto_lower in ("1", "cartao", "cartão", "credito", "crédito", "cartao de credito", "cartão de crédito"):
        return "cartao"
    if texto_lower in ("2", "pix"):
        return "pix"
    return None


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
    print(f"[Asaas] Iniciando criação de assinatura para {telefone}")
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
                f"🔗 {link}\n\n"
                "Esse fluxo ativa a *assinatura mensal automatica* do Mindnutri. "
                "Assim que o pagamento for aprovado, seu acesso sera liberado automaticamente.",
            )
        else:
            dados_estado["payment_id"] = pagamento.get("payment_id", "")
            mensagem_pix = (
                "Perfeito! Aqui esta seu link de pagamento em *Pix*.\n\n"
                f"🔗 {link}\n\n"
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
            f"Ótimo! Aqui está seu link de pagamento:\n\n"
            f"🔗 {link}\n\n"
            f"Após o pagamento ser confirmado, seu acesso é ativado automaticamente "
            f"e vamos começar a criar suas fichas! 🎉")

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
            "Desculpe, tive um problema técnico ao gerar seu link de pagamento. 😔\n\n"
            "Por favor, entre em contato com o suporte da Mindhub para completar sua assinatura:\n"
            f"📱 WhatsApp: {config.GESTOR_WHATSAPP}\n\n"
            "Enquanto isso, responda *ASSINAR* para tentar novamente!")

        # Alerta para o gestor
        if config.GESTOR_WHATSAPP:
            whatsapp.enviar_texto(config.GESTOR_WHATSAPP,
                f"🚨 *Alerta Mindnutri — Asaas Falhou*\n\n"
                f"Cliente {telefone} tentou assinar mas o Asaas retornou erro:\n"
                f"{str(e)[:200]}\n\n"
                f"Verifique a integração.")

        # NÃO muda estado — mantém em demonstracao_assinar para retry
        return


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
            f"Aqui esta seu link para renovacao via *{metodo}*:\n\n🔗 {link}\n\n"
            "Apos o pagamento, suas fichas sao renovadas automaticamente.",
        )
    except Exception:
        whatsapp.enviar_texto(
            telefone,
            "Em instantes nossa equipe te enviara o link de renovacao.",
        )
