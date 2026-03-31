import json
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from painel.models import Assinante, Conversa, EstadoConversa, FichaTecnica, Ingrediente, Notificacao

logger = logging.getLogger(__name__)

# ── ASSINANTES ────────────────────────────────────────────────────

def get_assinante(telefone: str) -> dict | None:
    try:
        a = Assinante.objects.get(telefone=telefone)
        return {
            "id": a.id,
            "telefone": a.telefone,
            "nome": a.nome,
            "estabelecimento": a.estabelecimento,
            "nicho": a.nicho,
            "cidade": a.cidade,
            "instagram": a.instagram,
            "cpf": a.cpf,
            "funcionarios": a.funcionarios,
            "faturamento_estimado": a.faturamento_estimado,
            "status": a.status,
            "asaas_customer_id": a.asaas_id,
            "asaas_subscription_id": getattr(a, 'asaas_subscription_id', ''),
            "fichas_geradas_mes": a.fichas_geradas_mes,
            "fichas_limite_mes": a.fichas_limite_mes,
            "total_fichas": a.total_fichas_geradas,
            "data_inicio": a.data_inicio.isoformat() if a.data_inicio else None,
            "proxima_cobranca": a.proxima_cobranca.isoformat() if a.proxima_cobranca else None,
        }
    except Assinante.DoesNotExist:
        return None

def criar_assinante(telefone: str) -> dict | None:
    Assinante.objects.get_or_create(telefone=telefone)
    return get_assinante(telefone)

def atualizar_assinante(telefone: str, **campos) -> None:
    try:
        a = Assinante.objects.get(telefone=telefone)
        if 'asaas_customer_id' in campos:
            a.asaas_id = campos.pop('asaas_customer_id')
        if 'total_fichas' in campos:
            a.total_fichas_geradas = campos.pop('total_fichas')

        for k, v in campos.items():
            if hasattr(a, k):
                setattr(a, k, v)
        a.save()
    except Assinante.DoesNotExist:
        pass

def incrementar_ficha(telefone: str) -> bool:
    """Incrementa fichas atomicamente via F(). Retorna False se limite atingido."""
    atualizado = Assinante.objects.filter(
        telefone=telefone,
        fichas_geradas_mes__lt=F('fichas_limite_mes'),
    ).update(
        fichas_geradas_mes=F('fichas_geradas_mes') + 1,
        total_fichas_geradas=F('total_fichas_geradas') + 1,
    )
    if atualizado == 0:
        logger.warning("[Credito] Limite atingido ou assinante inexistente: %s", telefone)
    return atualizado > 0


def possui_ficha_no_mes(telefone: str, nome_prato: str, tipo: str | None = None) -> bool:
    """Retorna True se ja existir ficha para o prato no mes atual."""
    try:
        assinante = Assinante.objects.get(telefone=telefone)
    except Assinante.DoesNotExist:
        return False

    hoje = timezone.localdate()
    qs = FichaTecnica.objects.filter(
        assinante=assinante,
        nome_prato__iexact=(nome_prato or "").strip(),
        criada_em__year=hoje.year,
        criada_em__month=hoje.month,
    )
    if tipo:
        qs = qs.filter(tipo=tipo)
    return qs.exists()


# ── CONVERSAS ─────────────────────────────────────────────────────

def salvar_mensagem(telefone: str, role: str, content: str) -> None:
    assinante = Assinante.objects.filter(telefone=telefone).first()
    Conversa.objects.create(
        telefone=telefone,
        role=role,
        content=content,
        assinante=assinante
    )
    _limpar_historico_antigo(telefone)

def get_historico(telefone: str, limite: int = 20) -> list[dict]:
    # Returns last N messages in chronological order (created older first)
    messages = Conversa.objects.filter(telefone=telefone).order_by('-criado_em')[:limite]

    historico = []
    for m in reversed(messages):
        # Ignore empty messages to prevent OpenAI API from throwing errors or hallucinating
        if m.content and m.content.strip():
            historico.append({"role": m.role, "content": m.content})

    return historico

def _limpar_historico_antigo(telefone: str) -> None:
    limite = timezone.now() - timedelta(days=2)
    Conversa.objects.filter(telefone=telefone, criado_em__lt=limite).delete()

def limpar_historico(telefone: str) -> None:
    """Apaga todo o histórico de conversa de um telefone (usado no reset completo)."""
    Conversa.objects.filter(telefone=telefone).delete()

def get_tempo_inativo_minutos(telefone: str) -> int:
    """Retorna quantos minutos se passaram desde a última atualização do estado."""
    try:
        obj = EstadoConversa.objects.get(telefone=telefone)
        delta = timezone.now() - obj.atualizado_em
        return int(delta.total_seconds() / 60)
    except EstadoConversa.DoesNotExist:
        return 0

# ── ESTADO DA CONVERSA ────────────────────────────────────────────

def get_estado(telefone: str) -> dict:
    obj, created = EstadoConversa.objects.get_or_create(telefone=telefone)
    return {
        "estado": obj.estado,
        "dados": json.loads(obj.dados_temp or "{}")
    }

def set_estado(telefone: str, estado: str, dados: dict | None = None) -> None:
    dados_str = json.dumps(dados or {}, ensure_ascii=False)
    with transaction.atomic():
        obj, created = EstadoConversa.objects.select_for_update().get_or_create(
            telefone=telefone
        )
        obj.estado = estado
        obj.dados_temp = dados_str
        obj.save()

def resetar_estado(telefone: str) -> None:
    set_estado(telefone, "inicio", {})


# ── FICHAS ────────────────────────────────────────────────────────

def salvar_ficha(telefone: str, dados: dict) -> int:
    try:
        a = Assinante.objects.get(telefone=telefone)
        ficha = FichaTecnica.objects.create(
            assinante=a,
            nome_prato=dados.get("nome_prato", "Prato"),
            tipo=dados.get("tipo", "tecnica"),
            codigo=dados.get("codigo", ""),
            custo_total=dados.get("custo_total"),
            custo_porcao=dados.get("custo_porcao"),
            num_porcoes=dados.get("num_porcoes"),
            arquivo_url=dados.get("arquivo_path", "")
        )
        return ficha.id
    except Assinante.DoesNotExist:
        return 0


# ── INGREDIENTES ──────────────────────────────────────────────────

def get_ingredientes(telefone: str) -> list[dict]:
    """Retorna ingredientes cadastrados — SEM custo (preco se pede a cada ficha)."""
    ings = Ingrediente.objects.filter(telefone=telefone).order_by('nome')
    return [{
        "nome": i.nome,
        "unidade": i.unidade,
        "fc": float(i.fc),
        "ic": float(i.ic)
    } for i in ings]

def salvar_ingrediente(telefone: str, nome: str, unidade: str,
                        fc: float = 1.0, ic: float = 1.0) -> None:
    """Salva ingrediente SEM custo — preco muda e deve ser pedido a cada ficha."""
    assinante = Assinante.objects.filter(telefone=telefone).first()
    obj, created = Ingrediente.objects.update_or_create(
        telefone=telefone, nome=nome,
        defaults={
            'unidade': unidade,
            'custo_unitario': 0,
            'fc': fc,
            'ic': ic,
            'assinante': assinante
        }
    )


# ── NOTIFICAÇÕES ──────────────────────────────────────────────────

def criar_notificacao(tipo: str, nivel: str, titulo: str,
                       mensagem: str, telefone: str | None = None) -> None:
    assinante = None
    if telefone:
        assinante = Assinante.objects.filter(telefone=telefone).first()

    Notificacao.objects.create(
        tipo=tipo,
        nivel=nivel,
        titulo=titulo,
        mensagem=mensagem,
        assinante=assinante
    )
