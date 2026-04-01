"""
Serviço de assinaturas Mindnutri.
Centraliza toda lógica de ciclo de vida:
  criar → pagar → ativar → usar → renovar → bloquear → reativar → cancelar
"""
import logging
from datetime import date, timedelta

from django.conf import settings as config

from assinaturas.asaas_client import asaas
from utils import banco, whatsapp

logger = logging.getLogger(__name__)


# ── CRIAÇÃO ───────────────────────────────────────────────────────

def iniciar_assinatura(telefone: str) -> str:
    """
    Cria ou recupera cliente no Asaas e gera link de pagamento.
    Retorna o link de pagamento.
    """
    assinante = banco.get_assinante(telefone)
    if not assinante:
        banco.criar_assinante(telefone)
        assinante = banco.get_assinante(telefone)

    nome = assinante.get("nome") or f"Cliente {telefone[-4:]}"

    # Busca ou cria cliente no Asaas
    customer_id = assinante.get("asaas_customer_id")
    if not customer_id:
        cliente_existente = asaas.buscar_cliente_por_telefone(telefone)
        if cliente_existente:
            customer_id = cliente_existente["id"]
        else:
            novo_cliente = asaas.criar_cliente(nome=nome, telefone=telefone)
            customer_id = novo_cliente["id"]
        banco.atualizar_assinante(telefone, asaas_customer_id=customer_id)

    # Cria assinatura
    subscription_id = assinante.get("asaas_subscription_id")
    if not subscription_id:
        assinatura = asaas.criar_assinatura(
            customer_id=customer_id,
            valor=config.PLANO_VALOR,
        )
        subscription_id = assinatura["id"]
        banco.atualizar_assinante(telefone, asaas_subscription_id=subscription_id)

    # Retorna link de pagamento
    link = asaas.link_pagamento_assinatura(subscription_id)
    return link


# ── ATIVAÇÃO (webhook PAYMENT_CONFIRMED) ─────────────────────────

def ativar_assinante(telefone: str, payment_data: dict):
    """Ativa assinante após confirmação de pagamento."""
    hoje = date.today()
    proxima = hoje + timedelta(days=30)

    banco.atualizar_assinante(telefone,
        status="ativo",
        data_inicio=hoje.isoformat(),
        proxima_cobranca=proxima.isoformat(),
        fichas_geradas_mes=0,
    )

    banco.criar_notificacao(
        "novo_assinante", "info",
        "Pagamento confirmado — acesso ativado",
        f"Assinante {telefone} — pagamento R${config.PLANO_VALOR:.2f} confirmado. Acesso ativo.",
        telefone,
    )

    _notificar_gestor_novo_assinante(telefone)
    _onboarding_boas_vindas(telefone)


# ── RENOVAÇÃO (webhook PAYMENT_CONFIRMED em assinatura existente) ─

def renovar_assinante(telefone: str):
    """Renova fichas e atualiza próxima cobrança."""
    hoje = date.today()
    proxima = hoje + timedelta(days=30)

    banco.atualizar_assinante(telefone,
        status="ativo",
        proxima_cobranca=proxima.isoformat(),
        fichas_geradas_mes=0,
    )

    whatsapp.enviar_texto(telefone,
        "✅ Sua assinatura foi renovada com sucesso!\n\n"
        f"Você tem *{config.PLANO_FICHAS_LIMITE} fichas disponíveis* até {proxima.strftime('%d/%m/%Y')}.\n\n"
        "Vamos criar fichas? É só chamar! 😊"
    )


# ── INADIMPLÊNCIA (webhook PAYMENT_OVERDUE) ───────────────────────

def bloquear_por_inadimplencia(telefone: str, payment_data: dict):
    """Bloqueia acesso quando pagamento vence sem pagamento."""
    banco.atualizar_assinante(telefone, status="inadimplente")

    banco.criar_notificacao(
        "inadimplencia", "critico",
        "Pagamento em atraso — acesso bloqueado",
        f"Assinante {telefone} com pagamento em atraso. Acesso suspenso automaticamente.",
        telefone,
    )

    # Gera nova cobrança com link de pagamento
    assinante = banco.get_assinante(telefone)
    link = ""
    try:
        customer_id = assinante.get("asaas_customer_id")
        if customer_id:
            cobranca = asaas.criar_cobranca(
                customer_id=customer_id,
                valor=config.PLANO_VALOR,
                descricao="Mindnutri — Regularização de assinatura",
                vencimento=date.today() + timedelta(days=3),
            )
            link = cobranca.get("invoiceUrl") or cobranca.get("bankSlipUrl", "")
    except Exception as e:
        logger.error("[Asaas] Erro ao gerar cobranca de regularizacao: %s", e)

    msg = (
        "⚠️ Seu acesso ao Mindnutri foi *suspenso* por falta de pagamento.\n\n"
        "Para reativar, efetue o pagamento:\n\n"
    )
    if link:
        msg += f"🔗 {link}\n\n"
    msg += "Assim que o pagamento for confirmado, seu acesso volta automaticamente. 💙"

    whatsapp.enviar_texto(telefone, msg)

    from utils.alertas_grupo import alertar_negocio
    alertar_negocio(
        "Inadimplência", "Acesso Bloqueado por Inadimplência",
        f"Pagamento em atraso. Acesso suspenso automaticamente.",
        telefone=telefone, nome=assinante.get('nome', telefone),
    )


# ── CANCELAMENTO (webhook SUBSCRIPTION_INACTIVATED) ──────────────

def cancelar_assinante(telefone: str):
    """Cancela assinatura e encerra acesso."""
    banco.atualizar_assinante(telefone, status="cancelado")

    banco.criar_notificacao(
        "cancelamento", "aviso",
        "Assinatura cancelada",
        f"Assinante {telefone} — assinatura cancelada.",
        telefone,
    )

    whatsapp.enviar_texto(telefone,
        "Sua assinatura Mindnutri foi encerrada.\n\n"
        "Foi um prazer te ajudar! Se quiser voltar, é só entrar em contato. 😊"
    )

    from utils.alertas_grupo import alertar_negocio
    alertar_negocio(
        "Não Renovação", "Assinatura Cancelada",
        f"Assinante cancelou a assinatura.",
        telefone=telefone,
    )


# ── RENOVAÇÃO ANTECIPADA (pedido pelo cliente) ────────────────────

def renovacao_antecipada(telefone: str) -> str:
    """Gera cobrança avulsa para renovação antecipada."""
    assinante = banco.get_assinante(telefone)
    customer_id = assinante.get("asaas_customer_id")

    if not customer_id:
        customer_id = _garantir_cliente_asaas(telefone, assinante)

    cobranca = asaas.criar_cobranca(
        customer_id=customer_id,
        valor=config.PLANO_VALOR,
        descricao="Mindnutri — Renovação antecipada",
    )
    return cobranca.get("invoiceUrl") or cobranca.get("bankSlipUrl", "")


# ── ONBOARDING PÓS-PAGAMENTO ──────────────────────────────────────

def _onboarding_boas_vindas(telefone: str):
    """Inicia coleta de dados do novo assinante."""
    assinante = banco.get_assinante(telefone)

    # Se já tem nome, pula o onboarding
    if assinante.get("nome"):
        whatsapp.enviar_texto(telefone,
            f"🎉 Bem-vindo de volta, {assinante['nome']}!\n\n"
            "Sua assinatura foi renovada. Vamos criar fichas? 😊"
        )
        banco.resetar_estado(telefone)
        return

    whatsapp.enviar_texto(telefone,
        "🎉 *Pagamento confirmado! Bem-vindo ao Mindnutri!*\n\n"
        "Sou o seu agente especializado em fichas técnicas.\n\n"
        "Antes de começarmos, preciso de algumas informações rápidas.\n\n"
        "Qual é o seu *nome completo*?"
    )
    banco.set_estado(telefone, "onboarding_nome", {})


def processar_onboarding(telefone: str, texto: str, estado: dict):
    """
    Gerencia o fluxo de onboarding após pagamento.
    Coleta: nome → estabelecimento → nicho → cidade →
            funcionários → faturamento → instagram
    """
    est   = estado["estado"]
    dados = estado.get("dados", {})

    if est == "onboarding_nome":
        dados["nome"] = texto.strip()
        banco.atualizar_assinante(telefone, nome=dados["nome"])
        banco.set_estado(telefone, "onboarding_estabelecimento", dados)
        whatsapp.enviar_texto(telefone,
            f"Prazer, {dados['nome']}! 😊\n\n"
            "Qual é o nome do seu *estabelecimento*?"
        )

    elif est == "onboarding_estabelecimento":
        dados["estabelecimento"] = texto.strip()
        banco.atualizar_assinante(telefone, estabelecimento=dados["estabelecimento"])
        banco.set_estado(telefone, "onboarding_nicho", dados)
        whatsapp.enviar_texto(telefone,
            "Qual é o *tipo do seu negócio*?\n\n"
            "1️⃣ Hambúrguer\n"
            "2️⃣ Sobremesa / Confeitaria\n"
            "3️⃣ Pizza\n"
            "4️⃣ Açaí\n"
            "5️⃣ Comida Brasileira\n"
            "6️⃣ Pães / Padaria\n"
            "7️⃣ Salgados\n"
            "8️⃣ Outro\n\n"
            "Responda com o número ou o nome."
        )

    elif est == "onboarding_nicho":
        nicho = _mapear_nicho(texto)
        dados["nicho"] = nicho
        banco.atualizar_assinante(telefone, nicho=nicho)
        banco.set_estado(telefone, "onboarding_cidade", dados)
        whatsapp.enviar_texto(telefone, "Em qual *cidade* você está?")

    elif est == "onboarding_cidade":
        dados["cidade"] = texto.strip()
        banco.atualizar_assinante(telefone, cidade=dados["cidade"])
        banco.set_estado(telefone, "onboarding_funcionarios", dados)
        whatsapp.enviar_texto(telefone,
            "Quantos *funcionários* trabalham no estabelecimento? (número)"
        )

    elif est == "onboarding_funcionarios":
        try:
            func = int("".join(filter(str.isdigit, texto)) or "1")
        except Exception:
            func = 1
        dados["funcionarios"] = func
        banco.atualizar_assinante(telefone, funcionarios=func)
        banco.set_estado(telefone, "onboarding_faturamento", dados)
        whatsapp.enviar_texto(telefone,
            "Qual é o *faturamento mensal estimado* do estabelecimento?\n\n"
            "Exemplo: R$ 15.000 ou 15000"
        )

    elif est == "onboarding_faturamento":
        fat = texto.strip()
        if not fat.startswith("R$"):
            # Tenta formatar
            nums = "".join(filter(lambda c: c.isdigit() or c == ".", fat))
            fat = f"R$ {nums}" if nums else fat
        dados["faturamento_estimado"] = fat
        banco.atualizar_assinante(telefone, faturamento_estimado=fat)
        banco.set_estado(telefone, "onboarding_instagram", dados)
        whatsapp.enviar_texto(telefone,
            "Qual é o *@ do Instagram* do seu negócio?\n\n"
            "(Pode pular respondendo *pular*)"
        )

    elif est == "onboarding_instagram":
        ig = texto.strip()
        if ig.lower() != "pular":
            if not ig.startswith("@"):
                ig = f"@{ig}"
            banco.atualizar_assinante(telefone, instagram=ig)
            dados["instagram"] = ig

        # Onboarding concluído
        banco.atualizar_assinante(telefone, status="ativo")
        banco.resetar_estado(telefone)

        nome = dados.get("nome", "")
        nicho = dados.get("nicho", "")
        whatsapp.enviar_texto(telefone,
            f"Perfeito, {nome}! Tudo pronto! 🎉\n\n"
            f"Seu perfil:\n"
            f"🏪 {dados.get('estabelecimento','')}\n"
            f"🍽 {_nicho_display(nicho)}\n"
            f"📍 {dados.get('cidade','')}\n\n"
            f"Você tem *{config.PLANO_FICHAS_LIMITE} fichas disponíveis* este mês.\n\n"
            "Posso criar sua primeira ficha técnica agora?\n"
            "É só me dizer o nome do prato! 😊"
        )


# ── ALERTAS AUTOMÁTICOS ───────────────────────────────────────────

def verificar_limites_fichas():
    """
    Verifica todos os assinantes e envia alertas de limite.
    Deve ser chamado periodicamente (ex: via cron diário).
    """
    from painel.models import Assinante
    from django.db.models import F

    assinantes = Assinante.objects.filter(
        status='ativo',
        fichas_geradas_mes__gte=F('fichas_limite_mes') - 3
    )

    for row in assinantes:
        tel  = row.telefone
        rest = row.fichas_limite_mes - row.fichas_geradas_mes
        nome = row.nome or tel

        if rest <= 0:
            banco.criar_notificacao(
                "limite_fichas", "critico",
                "Limite de fichas atingido",
                f"{nome} ({tel}) atingiu o limite de {row.fichas_limite_mes} fichas.",
                tel,
            )
        elif rest <= 3:
            banco.criar_notificacao(
                "limite_fichas", "aviso",
                "Limite de fichas próximo",
                f"{nome} ({tel}) usou {row.fichas_geradas_mes}/{row.fichas_limite_mes} fichas.",
                tel,
            )


def verificar_vencimentos():
    """
    Verifica cobranças vencendo em 3 dias e envia lembrete.
    Deve ser chamado diariamente.
    """
    try:
        cobrancas = asaas.listar_cobrancas_vencendo(dias=3)
        for c in cobrancas:
            customer_id = c.get("customer")
            link = c.get("invoiceUrl") or c.get("bankSlipUrl", "")

            assinante = _buscar_por_customer_id(customer_id)
            if not assinante:
                continue

            telefone = assinante["telefone"]
            whatsapp.enviar_texto(telefone,
                "⏰ Lembrete: sua assinatura Mindnutri vence em *3 dias*.\n\n"
                f"Para continuar usando, efetue o pagamento:\n🔗 {link}\n\n"
                "Qualquer dúvida, estamos aqui! 😊"
            )
    except Exception as e:
        logger.error("[Assinaturas] Erro ao verificar vencimentos: %s", e)


# ── HELPERS ───────────────────────────────────────────────────────

def _mapear_nicho(texto: str) -> str:
    t = texto.lower()
    if "1" in t or "hamb" in t or "burger" in t:
        return "hamburguer"
    elif "2" in t or "sobremesa" in t or "confeit" in t or "doce" in t:
        return "sobremesa"
    elif "3" in t or "pizza" in t:
        return "pizza"
    elif "4" in t or "acai" in t or "açaí" in t or "açai" in t:
        return "acai"
    elif "5" in t or "brasileira" in t or "caseira" in t:
        return "comida_brasileira"
    elif "6" in t or "pao" in t or "pão" in t or "pães" in t or "paes" in t or "padaria" in t:
        return "paes"
    elif "7" in t or "salgado" in t or "coxinha" in t or "pastel" in t or "empada" in t:
        return "salgado"
    elif "8" in t or "outro" in t:
        return "outro"
    return "outro"


def _nicho_display(nicho: str) -> str:
    return {
        "hamburguer":       "Hambúrguer",
        "sobremesa":        "Sobremesa / Confeitaria",
        "pizza":            "Pizza",
        "acai":             "Açaí",
        "comida_brasileira":"Comida Brasileira",
        "paes":             "Pães / Padaria",
        "salgado":          "Salgados",
    }.get(nicho, "Outro")


def _garantir_cliente_asaas(telefone: str, assinante: dict) -> str:
    existente = asaas.buscar_cliente_por_telefone(telefone)
    if existente:
        cid = existente["id"]
    else:
        novo = asaas.criar_cliente(
            nome=assinante.get("nome") or f"Cliente {telefone[-4:]}",
            telefone=telefone,
        )
        cid = novo["id"]
    banco.atualizar_assinante(telefone, asaas_customer_id=cid)
    return cid


def _buscar_por_customer_id(customer_id: str) -> dict | None:
    from painel.models import Assinante
    try:
        a = Assinante.objects.get(asaas_id=customer_id)
        return {
            "id": a.id,
            "telefone": a.telefone,
            "nome": a.nome,
        }
    except Assinante.DoesNotExist:
        return None


def _notificar_gestor_novo_assinante(telefone: str):
    assinante = banco.get_assinante(telefone)
    nome  = assinante.get("nome", telefone)
    estab = assinante.get("estabelecimento", "")
    nicho = _nicho_display(assinante.get("nicho", ""))

    if config.GESTOR_WHATSAPP:
        whatsapp.enviar_texto(
            config.GESTOR_WHATSAPP,
            f"🎉 Novo assinante Mindnutri!\n\n"
            f"👤 {nome}\n"
            f"🏪 {estab}\n"
            f"🍽 {nicho}\n"
            f"📱 {telefone}"
        )

    from utils.alertas_grupo import alertar_negocio
    alertar_negocio(
        "Novo Assinante", "Novo Assinante!",
        f"🏪 {estab}\n🍽 {nicho}",
        telefone=telefone, nome=nome,
    )
