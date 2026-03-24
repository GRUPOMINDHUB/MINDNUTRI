import json
from datetime import datetime, timedelta, date
from django.utils import timezone
from painel.models import Assinante, FichaTecnica, Notificacao, Conversa, Ingrediente, EstadoConversa

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

def criar_assinante(telefone: str) -> dict:
    Assinante.objects.get_or_create(telefone=telefone)
    return get_assinante(telefone)

def atualizar_assinante(telefone: str, **campos):
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

def assinante_ativo(telefone: str) -> bool:
    v = get_assinante(telefone)
    return v is not None and v["status"] == "ativo"

def fichas_disponiveis(telefone: str) -> bool:
    v = get_assinante(telefone)
    if not v:
        return False
    return v["fichas_geradas_mes"] < v["fichas_limite_mes"]

def incrementar_ficha(telefone: str):
    try:
        a = Assinante.objects.get(telefone=telefone)
        a.fichas_geradas_mes += 1
        a.total_fichas_geradas += 1
        a.save()
    except Assinante.DoesNotExist:
        pass


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

def salvar_mensagem(telefone: str, role: str, content: str):
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

def _limpar_historico_antigo(telefone: str):
    limite = timezone.now() - timedelta(days=2)
    Conversa.objects.filter(telefone=telefone, criado_em__lt=limite).delete()

# ── ESTADO DA CONVERSA ────────────────────────────────────────────

def get_estado(telefone: str) -> dict:
    obj, created = EstadoConversa.objects.get_or_create(telefone=telefone)
    return {
        "estado": obj.estado,
        "dados": json.loads(obj.dados_temp or "{}")
    }

def set_estado(telefone: str, estado: str, dados: dict = None):
    dados_str = json.dumps(dados or {}, ensure_ascii=False)
    obj, created = EstadoConversa.objects.get_or_create(telefone=telefone)
    obj.estado = estado
    obj.dados_temp = dados_str
    obj.save()

def resetar_estado(telefone: str):
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
    ings = Ingrediente.objects.filter(telefone=telefone).order_by('nome')
    return [{
        "nome": i.nome,
        "unidade": i.unidade,
        "custo_unitario": i.custo_unitario,
        "fc": float(i.fc),
        "ic": float(i.ic)
    } for i in ings]

def get_ingrediente(telefone: str, nome: str) -> dict | None:
    try:
        i = Ingrediente.objects.get(telefone=telefone, nome__iexact=nome)
        return {
            "nome": i.nome,
            "unidade": i.unidade,
            "custo_unitario": i.custo_unitario,
            "fc": float(i.fc),
            "ic": float(i.ic)
        }
    except Ingrediente.DoesNotExist:
        return None

def salvar_ingrediente(telefone: str, nome: str, unidade: str,
                        custo: float, fc: float = 1.0, ic: float = 1.0):
    assinante = Assinante.objects.filter(telefone=telefone).first()
    obj, created = Ingrediente.objects.update_or_create(
        telefone=telefone, nome=nome,
        defaults={
            'unidade': unidade,
            'custo_unitario': custo,
            'fc': fc,
            'ic': ic,
            'assinante': assinante
        }
    )


# ── NOTIFICAÇÕES ──────────────────────────────────────────────────

def criar_notificacao(tipo: str, nivel: str, titulo: str,
                       mensagem: str, telefone: str = None):
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
