import json
import os
import requests as _http
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import Assinante, FichaTecnica, Notificacao, ConfiguracaoIA, MensagemBot, PerdaIngrediente, Cupom


def _stats(request):
    """Retorna estatísticas globais para o contexto base."""
    hoje = timezone.localdate()
    total         = Assinante.objects.count()
    ativos        = Assinante.objects.filter(status='ativo').count()
    bloqueados    = Assinante.objects.filter(status='bloqueado').count()
    inadimplentes = Assinante.objects.filter(status='inadimplente').count()
    novas_fichas  = FichaTecnica.objects.filter(criada_em__date=hoje).count()
    notif_nao_lidas = Notificacao.objects.filter(lida=False).count()
    from django.conf import settings as s
    plano_valor = float(getattr(s, 'PLANO_VALOR', 89.90))
    receita_mensal = ativos * plano_valor
    return {
        'total_assinantes': total,
        'ativos': ativos,
        'bloqueados': bloqueados,
        'inadimplentes': inadimplentes,
        'novas_fichas_hoje': novas_fichas,
        'notif_nao_lidas': notif_nao_lidas,
        'receita_mensal': receita_mensal,
        'plano_valor': f'{plano_valor:.2f}'.replace('.', ','),
    }


@login_required
def dashboard(request):
    ctx = _stats(request)

    # Assinantes próximos do limite (>= 80%)
    alerta_fichas = Assinante.objects.filter(
        status='ativo',
        fichas_geradas_mes__gte=24
    ).order_by('-fichas_geradas_mes')[:5]

    # Últimas fichas geradas
    ultimas_fichas = FichaTecnica.objects.select_related('assinante').order_by('-criada_em')[:8]

    # Notificações não lidas
    notificacoes = Notificacao.objects.filter(lida=False).order_by('-criada_em')[:5]

    # Distribuição por nicho
    nichos = Assinante.objects.values('nicho').annotate(total=Count('id')).order_by('-total')

    # Novos assinantes últimos 30 dias
    trinta_dias = timezone.now() - timedelta(days=30)
    novos_30d = Assinante.objects.filter(criado_em__gte=trinta_dias).count()

    ctx.update({
        'alerta_fichas': alerta_fichas,
        'ultimas_fichas': ultimas_fichas,
        'notificacoes': notificacoes,
        'nichos': nichos,
        'novos_30d': novos_30d,
        'page': 'dashboard',
    })
    return render(request, 'painel/dashboard.html', ctx)


@login_required
def assinantes(request):
    ctx = _stats(request)
    qs = Assinante.objects.all()

    # Filtros
    status_filtro = request.GET.get('status', '')
    nicho_filtro  = request.GET.get('nicho', '')
    busca         = request.GET.get('q', '')

    if status_filtro:
        qs = qs.filter(status=status_filtro)
    if nicho_filtro:
        qs = qs.filter(nicho=nicho_filtro)
    if busca:
        qs = qs.filter(
            Q(nome__icontains=busca) |
            Q(estabelecimento__icontains=busca) |
            Q(telefone__icontains=busca)
        )

    ctx.update({
        'assinantes': qs,
        'status_filtro': status_filtro,
        'nicho_filtro': nicho_filtro,
        'busca': busca,
        'page': 'assinantes',
    })
    return render(request, 'painel/assinantes.html', ctx)


@login_required
def assinante_detalhe(request, pk):
    ctx = _stats(request)
    assinante = get_object_or_404(Assinante, pk=pk)
    fichas = assinante.fichas.all().order_by('-criada_em')
    ctx.update({
        'assinante': assinante,
        'fichas': fichas,
        'page': 'assinantes',
    })
    return render(request, 'painel/assinante_detalhe.html', ctx)


@login_required
def toggle_status(request, pk):
    """Bloquear ou desbloquear assinante manualmente."""
    if request.method == 'POST':
        assinante = get_object_or_404(Assinante, pk=pk)
        novo_status = request.POST.get('status')
        if novo_status in ['ativo', 'bloqueado', 'inadimplente', 'cancelado']:
            assinante.status = novo_status
            assinante.save()
            messages.success(request, f"Status de {assinante.nome} atualizado para {novo_status}.")
        return redirect('assinante_detalhe', pk=pk)
    return redirect('assinantes')


@login_required
def fichas(request):
    ctx = _stats(request)
    qs = FichaTecnica.objects.select_related('assinante').order_by('-criada_em')

    tipo_filtro = request.GET.get('tipo', '')
    busca       = request.GET.get('q', '')

    if tipo_filtro:
        qs = qs.filter(tipo=tipo_filtro)
    if busca:
        qs = qs.filter(
            Q(nome_prato__icontains=busca) |
            Q(assinante__nome__icontains=busca)
        )

    ctx.update({
        'fichas': qs[:100],
        'tipo_filtro': tipo_filtro,
        'busca': busca,
        'page': 'fichas',
    })
    return render(request, 'painel/fichas.html', ctx)


@login_required
def notificacoes(request):
    ctx = _stats(request)
    todas = Notificacao.objects.all().order_by('-criada_em')

    # Marcar como lida
    if request.method == 'POST':
        notif_id = request.POST.get('marcar_lida')
        marcar_todas = request.POST.get('marcar_todas')
        if notif_id:
            Notificacao.objects.filter(pk=notif_id).update(lida=True)
        elif marcar_todas:
            Notificacao.objects.filter(lida=False).update(lida=True)
        return redirect('notificacoes')

    ctx.update({
        'todas_notificacoes': todas,
        'page': 'notificacoes',
    })
    return render(request, 'painel/notificacoes.html', ctx)


@login_required
def api_stats(request):
    """Endpoint JSON para atualização dinâmica dos cards."""
    ctx = _stats(request)
    return JsonResponse(ctx)


# ── CONFIGURAÇÕES DA IA ──────────────────────────────────────────────────────

@login_required
def configuracoes_ia(request):
    ctx = _stats(request)
    config = ConfiguracaoIA.get_config()
    ctx.update({'config': config, 'page': 'configuracoes'})
    return render(request, 'painel/configuracoes.html', ctx)


@login_required
def api_salvar_prompt(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)
    data = json.loads(request.body)
    config = ConfiguracaoIA.get_config()
    config.persona             = data.get('persona', config.persona)
    config.metodologia         = data.get('metodologia', config.metodologia)
    config.instrucoes_geracao  = data.get('instrucoes_geracao', config.instrucoes_geracao)
    config.formato_saida       = data.get('formato_saida', config.formato_saida)
    config.save()
    return JsonResponse({'ok': True})


@login_required
def api_salvar_parametros(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)
    data = json.loads(request.body)
    config = ConfiguracaoIA.get_config()
    config.max_tokens  = int(data.get('max_tokens', config.max_tokens))
    config.temperatura = float(data.get('temperatura', config.temperatura))
    config.save()
    return JsonResponse({'ok': True})


@login_required
def api_preview_chat(request):
    """Processa uma mensagem no chat preview usando a mesma lógica do agente."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)

    data    = json.loads(request.body)
    mensagem = data.get('mensagem', '').strip()
    historico = data.get('historico', [])  # lista de {role, content} vinda do frontend

    if not mensagem:
        return JsonResponse({'ok': False, 'erro': 'Mensagem vazia'}, status=400)

    try:
        import openai as _openai_lib
        from django.conf import settings as dj_settings

        config = ConfiguracaoIA.get_config()

        client = _openai_lib.OpenAI(api_key=dj_settings.OPENAI_API_KEY)

        system_prompt = config.get_system_prompt()
        if not system_prompt:
            from agente_app.prompt import SYSTEM_PROMPT
            system_prompt = SYSTEM_PROMPT

        mensagens = [{"role": "system", "content": system_prompt}]
        mensagens += historico
        mensagens.append({"role": "user", "content": mensagem})

        resposta = client.chat.completions.create(
            model=config.modelo_ia,
            messages=mensagens,
            max_tokens=config.max_tokens,
            temperature=config.temperatura,
        )

        texto_resposta = resposta.choices[0].message.content or ''
        tokens_usados  = resposta.usage.total_tokens if resposta.usage else 0

        return JsonResponse({
            'ok': True,
            'resposta': texto_resposta,
            'tokens_usados': tokens_usados,
        })

    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


# ── CONEXÃO WHATSAPP ─────────────────────────────────────────────────────────

def _evo_url(path):
    from django.conf import settings as s
    return f"{s.EVOLUTION_API_URL.rstrip('/')}/{path}/{s.EVOLUTION_INSTANCE}"

def _evo_headers():
    from django.conf import settings as s
    return {'apikey': s.EVOLUTION_API_KEY, 'Content-Type': 'application/json'}


@login_required
def api_conexao_status(request):
    """Status da conexão WhatsApp + todos os serviços dependentes."""
    from django.conf import settings as s
    result = {}

    # WhatsApp (Evolution API)
    try:
        r = _http.get(_evo_url('instance/connectionState'), headers=_evo_headers(), timeout=5)
        d = r.json()
        state = (d.get('instance') or {}).get('state', d.get('state', 'unknown'))
        result['whatsapp'] = {'ok': True, 'state': state, 'connected': state == 'open'}
    except Exception as e:
        result['whatsapp'] = {'ok': False, 'state': 'error', 'connected': False, 'erro': str(e)}

    # OpenAI
    result['openai'] = {'ok': bool(getattr(s, 'OPENAI_API_KEY', None)), 'model': 'GPT-4o'}

    # Asaas
    asaas_env = 'prod' if 'asaas.com/api/v3' in getattr(s, 'ASAAS_BASE_URL', '') and 'sandbox' not in getattr(s, 'ASAAS_BASE_URL', '') else 'sandbox'
    result['asaas'] = {'ok': bool(getattr(s, 'ASAAS_API_KEY', None)), 'env': asaas_env}

    # Configurações (key mascarada)
    key = getattr(s, 'EVOLUTION_API_KEY', '')
    masked = (key[:4] + '****' + key[-4:]) if len(key) > 8 else '****'
    webhook = f"{s.EVOLUTION_API_URL.rstrip('/')} → {s.ALLOWED_HOSTS[0] if s.ALLOWED_HOSTS else 'localhost'}:8000/webhook/"
    result['config'] = {
        'instancia': s.EVOLUTION_INSTANCE,
        'api_url': s.EVOLUTION_API_URL,
        'api_key_masked': masked,
        'painel_url': s.EVOLUTION_API_URL.rstrip('/'),
        'webhook_url': f"{getattr(s, 'SITE_URL', 'http://localhost:8000')}/agente/webhook/",
    }

    return JsonResponse({'ok': True, **result})


@login_required
def api_conexao_qrcode(request):
    """Busca o QR Code para emparelhar o WhatsApp."""
    try:
        r = _http.get(_evo_url('instance/connect'), headers=_evo_headers(), timeout=10)
        d = r.json()
        # Evolution API v2: { "code": "...", "base64": "data:image/png;base64,..." }
        base64_img = d.get('base64') or (d.get('qrcode') or {}).get('base64', '')
        code = d.get('code') or (d.get('qrcode') or {}).get('code', '')
        return JsonResponse({'ok': True, 'base64': base64_img, 'code': code})
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


@login_required
def api_conexao_acao(request):
    """Desconectar ou reiniciar a instância WhatsApp."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)
    data = json.loads(request.body)
    acao = data.get('acao')
    hdrs = _evo_headers()
    try:
        if acao == 'desconectar':
            _http.delete(_evo_url('instance/logout'), headers=hdrs, timeout=10)
        elif acao == 'reiniciar':
            _http.put(_evo_url('instance/restart'), headers=hdrs, timeout=10)
        else:
            return JsonResponse({'ok': False, 'erro': 'Ação inválida'})
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


@login_required
def api_editar_assinante(request, pk):
    """Salva edições do cadastro do assinante via AJAX (POST JSON)."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)

    assinante = get_object_or_404(Assinante, pk=pk)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON inválido'}, status=400)

    campos_texto = ['nome', 'estabelecimento', 'nicho', 'cidade', 'instagram', 'cpf',
                    'faturamento_estimado', 'observacoes']
    campos_int   = ['funcionarios', 'fichas_limite_mes']

    for campo in campos_texto:
        if campo in data:
            setattr(assinante, campo, data[campo])

    for campo in campos_int:
        if campo in data:
            try:
                setattr(assinante, campo, int(data[campo]))
            except (ValueError, TypeError):
                return JsonResponse({'ok': False, 'erro': f'Valor inválido para {campo}'}, status=400)

    assinante.save()
    return JsonResponse({
        'ok': True,
        'nome': assinante.nome,
        'estabelecimento': assinante.estabelecimento,
        'nicho_display': assinante.get_nicho_display(),
    })


# ══════════════════════════════════════════════════════════════════════════════
# FINANCEIRO
# ══════════════════════════════════════════════════════════════════════════════

def _asaas_get(endpoint):
    """GET direto na API do Asaas."""
    from django.conf import settings as s
    url = f"{s.ASAAS_BASE_URL}/{endpoint}"
    hdrs = {"access_token": s.ASAAS_API_KEY, "Content-Type": "application/json"}
    r = _http.get(url, headers=hdrs, timeout=20)
    r.raise_for_status()
    return r.json()


def _asaas_post(endpoint, payload):
    """POST direto na API do Asaas."""
    from django.conf import settings as s
    url = f"{s.ASAAS_BASE_URL}/{endpoint}"
    hdrs = {"access_token": s.ASAAS_API_KEY, "Content-Type": "application/json"}
    r = _http.post(url, json=payload, headers=hdrs, timeout=20)
    r.raise_for_status()
    return r.json()


@login_required
def financeiro(request):
    from django.conf import settings as s
    ctx = _stats(request)
    ctx['page'] = 'financeiro'
    ctx['plano_valor_num'] = float(getattr(s, 'PLANO_VALOR', 89.90))
    return render(request, 'painel/financeiro.html', ctx)


@login_required
def api_financeiro_dados(request):
    """Busca cobranças do Asaas + monta dashboard.
    Regras:
    - Só mostra cobranças de assinantes locais (ignora clientes-teste do sandbox)
    - Lista: cobranças pagas + vencidas + apenas a PRÓXIMA pendente por assinante
    - Atrasados: vencidas 1-6 dias
    - Inadimplentes: vencidas 7+ dias
    """
    from django.conf import settings as s
    from datetime import date, timedelta

    # Parâmetros de filtro
    status_filtro = request.GET.get('status', '')
    busca = request.GET.get('q', '')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    offset = int(request.GET.get('offset', 0))
    limit = 20

    # Padrão: últimos 30 dias
    if not data_inicio:
        data_inicio = (date.today() - timedelta(days=30)).isoformat()
    if not data_fim:
        data_fim = date.today().isoformat()

    try:
        # ── Buscar TODAS as cobranças do Asaas ──
        all_payments = []
        try:
            resp = _asaas_get("payments?limit=100")
            all_payments = resp.get('data', [])
        except Exception:
            pass

        # ── Mapear customer_ids para assinantes locais ──
        # 1) Primeiro por asaas_id direto
        customer_ids = set(p.get('customer', '') for p in all_payments if p.get('customer'))
        assinantes_map = {}

        for a in Assinante.objects.all():
            if a.asaas_id and a.asaas_id in customer_ids:
                assinantes_map[a.asaas_id] = {'nome': a.nome, 'telefone': a.telefone, 'pk': a.pk}

        # 2) Para customer_ids sem match, buscar por telefone na API do Asaas
        for cid in customer_ids:
            if cid not in assinantes_map:
                try:
                    cust = _asaas_get(f"customers/{cid}")
                    cust_phone = cust.get('mobilePhone', '') or cust.get('phone', '')
                    cust_name = cust.get('name', cid)
                    if cust_phone:
                        # Normalizar: tentar match por final do telefone
                        phone_digits = ''.join(c for c in cust_phone if c.isdigit())
                        phone_tail = phone_digits[-11:] if len(phone_digits) >= 11 else phone_digits
                        local = Assinante.objects.filter(telefone__endswith=phone_tail).first()
                        if local:
                            assinantes_map[cid] = {'nome': local.nome, 'telefone': local.telefone, 'pk': local.pk}
                            continue
                    assinantes_map[cid] = {'nome': cust_name, 'telefone': cust_phone, 'pk': None}
                except Exception:
                    assinantes_map[cid] = {'nome': cid, 'telefone': '', 'pk': None}

        # ── Filtrar: só cobranças que mapeiam para assinantes locais (pk != None) ──
        all_payments = [p for p in all_payments if assinantes_map.get(p.get('customer', ''), {}).get('pk') is not None]

        # ── Consolidar por ASSINANTE (pk): 1 cobrança por assinante por status ──
        # Múltiplos customer_ids podem apontar pro mesmo assinante local (sandbox cria duplicatas)
        # Para cada assinante: guarda só a cobrança mais recente de cada tipo
        hoje = date.today()
        plano_valor = float(getattr(s, 'PLANO_VALOR', 89.90))

        # Agrupar payments por assinante (pk)
        por_assinante = {}  # pk -> list of payments
        for p in all_payments:
            cid = p.get('customer', '')
            info = assinantes_map.get(cid, {})
            pk = info.get('pk')
            if pk is not None:
                por_assinante.setdefault(pk, []).append(p)

        # Para cada assinante, selecionar: a paga mais recente, a vencida mais recente, a próxima pendente
        pagas = []
        vencidas_unicas = []  # 1 por assinante
        pendentes_unicas = []  # 1 por assinante

        for pk, payments in por_assinante.items():
            # Separar por status
            pk_pagas = [p for p in payments if p.get('status') in ('RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH')]
            pk_overdue = [p for p in payments if p.get('status') == 'OVERDUE']
            pk_pending = [p for p in payments if p.get('status') == 'PENDING']

            # Pagas: guardar a mais recente apenas
            if pk_pagas:
                pk_pagas.sort(key=lambda p: p.get('paymentDate', '') or p.get('dateCreated', ''), reverse=True)
                pagas.append(pk_pagas[0])

            # Vencidas: guardar só a mais recente (menor dias de atraso = vencimento mais recente)
            if pk_overdue:
                pk_overdue.sort(key=lambda p: p.get('dueDate', ''), reverse=True)
                vencidas_unicas.append(pk_overdue[0])

            # Pendentes: guardar só a próxima (menor dueDate)
            if pk_pending:
                pk_pending.sort(key=lambda p: p.get('dueDate', ''))
                pendentes_unicas.append(pk_pending[0])

        # Todas as cobranças visíveis (1 por assinante por tipo, sem duplicatas)
        visible_payments = pagas + vencidas_unicas + pendentes_unicas

        # ── Dashboard métricas ──
        receita_mes = 0.0
        a_receber = 0.0
        em_atraso = 0.0
        cobrancas_vencidas = 0

        for p in visible_payments:
            st = p.get('status', '')
            if st in ('RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH'):
                receita_mes += plano_valor
            elif st == 'PENDING':
                a_receber += plano_valor
            elif st == 'OVERDUE':
                em_atraso += plano_valor
                cobrancas_vencidas += 1

        total_ativos = Assinante.objects.filter(status='ativo').count()
        total_inadimplentes = Assinante.objects.filter(status='inadimplente').count()
        total_assinantes = total_ativos + total_inadimplentes
        total_cobrancas = len(visible_payments)
        taxa_cobrancas = round((cobrancas_vencidas / total_cobrancas * 100), 1) if total_cobrancas > 0 else 0
        taxa_assinantes = round((total_inadimplentes / total_assinantes * 100), 1) if total_assinantes > 0 else 0

        dashboard = {
            'receita_mes': f"{receita_mes:.2f}",
            'a_receber': f"{a_receber:.2f}",
            'em_atraso': f"{em_atraso:.2f}",
            'ativos_pagantes': total_ativos,
            'taxa_cobrancas': taxa_cobrancas,
            'taxa_assinantes': taxa_assinantes,
            'total_inadimplentes': total_inadimplentes,
        }

        # ── Atrasados (1-6 dias) — 1 por assinante ──
        atrasados = []
        for p in vencidas_unicas:
            due = p.get('dueDate', '')
            if due:
                try:
                    due_date = date.fromisoformat(due)
                    dias = (hoje - due_date).days
                    if 1 <= dias <= 6:
                        cid = p.get('customer', '')
                        info = assinantes_map.get(cid, {})
                        atrasados.append({
                            'payment_id': p['id'],
                            'nome': info.get('nome', cid),
                            'telefone': info.get('telefone', ''),
                            'pk': info.get('pk'),
                            'valor': f"{plano_valor:.2f}",
                            'dias_atraso': dias,
                            'due_date': due,
                        })
                except ValueError:
                    pass
        atrasados.sort(key=lambda x: -x['dias_atraso'])

        # ── Inadimplentes (7+ dias) — 1 por assinante ──
        inadimplentes = []
        for p in vencidas_unicas:
            due = p.get('dueDate', '')
            if due:
                try:
                    due_date = date.fromisoformat(due)
                    dias = (hoje - due_date).days
                    if dias >= 7:
                        cid = p.get('customer', '')
                        info = assinantes_map.get(cid, {})
                        inadimplentes.append({
                            'payment_id': p['id'],
                            'nome': info.get('nome', cid),
                            'telefone': info.get('telefone', ''),
                            'pk': info.get('pk'),
                            'valor': f"{plano_valor:.2f}",
                            'dias_atraso': dias,
                            'due_date': due,
                        })
                except ValueError:
                    pass
        inadimplentes.sort(key=lambda x: -x['dias_atraso'])

        # ── Normalizar lista de cobranças ──
        STATUS_ORDEM = {'OVERDUE': 0, 'PENDING': 1, 'RECEIVED': 2, 'CONFIRMED': 2, 'RECEIVED_IN_CASH': 2}
        STATUS_LABEL = {
            'PENDING': 'pendente', 'OVERDUE': 'vencido',
            'RECEIVED': 'pago', 'CONFIRMED': 'pago', 'RECEIVED_IN_CASH': 'pago',
        }

        # Aplicar filtro de status
        if status_filtro:
            filtro_map = {
                'pago': ('RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH'),
                'pendente': ('PENDING',),
                'vencido': ('OVERDUE',),
            }
            status_validos = filtro_map.get(status_filtro, ())
            visible_payments = [p for p in visible_payments if p.get('status', '') in status_validos]

        # Aplicar filtro de período (por dueDate)
        visible_payments = [
            p for p in visible_payments
            if data_inicio <= (p.get('dueDate') or p.get('dateCreated', '')) <= data_fim
            or p.get('status') == 'OVERDUE'  # Vencidas sempre aparecem
        ]

        # Aplicar filtro de busca
        if busca:
            busca_lower = busca.lower()
            filtered = []
            for p in visible_payments:
                cid = p.get('customer', '')
                info = assinantes_map.get(cid, {})
                nome_check = info.get('nome', '').lower()
                tel_check = info.get('telefone', '')
                if busca_lower in nome_check or busca in tel_check:
                    filtered.append(p)
            visible_payments = filtered

        # Ordenar: vencidas → pendentes → pagas
        visible_payments.sort(key=lambda p: STATUS_ORDEM.get(p.get('status', ''), 9))

        # Paginação
        total_visible = len(visible_payments)
        page_payments = visible_payments[offset:offset + limit]
        has_more = (offset + limit) < total_visible

        cobrancas = []
        for p in page_payments:
            cid = p.get('customer', '')
            info = assinantes_map.get(cid, {})
            st_raw = p.get('status', '')
            billing = p.get('billingType', '')
            metodo_label = {'BOLETO': 'Boleto', 'CREDIT_CARD': 'Cartão', 'PIX': 'Pix', 'UNDEFINED': '—'}.get(billing, billing or '—')

            cobrancas.append({
                'id': p['id'],
                'customer_id': cid,
                'nome': info.get('nome', cid),
                'telefone': info.get('telefone', ''),
                'pk': info.get('pk'),
                'valor': f"{plano_valor:.2f}",
                'status': STATUS_LABEL.get(st_raw, st_raw.lower()),
                'status_raw': st_raw,
                'metodo': metodo_label,
                'descricao': p.get('description', ''),
                'data_criacao': p.get('dateCreated', ''),
                'vencimento': p.get('dueDate', ''),
                'data_pagamento': p.get('paymentDate', ''),
                'invoice_url': p.get('invoiceUrl', ''),
            })

        return JsonResponse({
            'ok': True,
            'dashboard': dashboard,
            'atrasados': atrasados,
            'inadimplentes': inadimplentes,
            'cobrancas': cobrancas,
            'has_more': has_more,
            'offset': offset,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


@login_required
def api_financeiro_cobranca(request):
    """Detalhe de uma cobrança específica do Asaas."""
    payment_id = request.GET.get('id', '')
    if not payment_id:
        return JsonResponse({'ok': False, 'erro': 'ID não informado'}, status=400)

    try:
        p = _asaas_get(f"payments/{payment_id}")
        cid = p.get('customer', '')
        info = {}
        try:
            a = Assinante.objects.get(asaas_id=cid)
            info = {'nome': a.nome, 'telefone': a.telefone, 'pk': a.pk}
        except Assinante.DoesNotExist:
            # Buscar nome na API do Asaas + tentar match por telefone
            try:
                cust = _asaas_get(f"customers/{cid}")
                cust_name = cust.get('name', cid)
                cust_phone = cust.get('mobilePhone', '') or cust.get('phone', '')
                info = {'nome': cust_name, 'telefone': cust_phone, 'pk': None}
                if cust_phone:
                    phone_clean = cust_phone.lstrip('55') if len(cust_phone) > 11 else cust_phone
                    local = Assinante.objects.filter(
                        Q(telefone__endswith=phone_clean) | Q(telefone=cust_phone)
                    ).first()
                    if local:
                        info = {'nome': local.nome, 'telefone': local.telefone, 'pk': local.pk}
            except Exception:
                info = {'nome': cid, 'telefone': '', 'pk': None}

        # Tentar buscar histórico de eventos
        historico = []
        try:
            events = _asaas_get(f"payments/{payment_id}/events")
            for ev in events.get('data', []):
                historico.append({
                    'tipo': ev.get('type', ''),
                    'data': ev.get('dateCreated', ''),
                })
        except Exception:
            pass

        return JsonResponse({
            'ok': True,
            'cobranca': {
                'id': p['id'],
                'customer_id': cid,
                'nome': info.get('nome', cid),
                'telefone': info.get('telefone', ''),
                'pk': info.get('pk'),
                'valor': f"{float(p.get('value', 0)):.2f}",
                'status': p.get('status', ''),
                'metodo': p.get('billingType', ''),
                'descricao': p.get('description', ''),
                'data_criacao': p.get('dateCreated', ''),
                'vencimento': p.get('dueDate', ''),
                'data_pagamento': p.get('paymentDate', ''),
                'invoice_url': p.get('invoiceUrl', ''),
                'external_ref': p.get('externalReference', ''),
                'historico': historico,
            },
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


@login_required
def api_financeiro_nova_cobranca(request):
    """Cria cobrança manual e envia link via WhatsApp."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON inválido'}, status=400)

    telefone = data.get('telefone', '')
    valor = data.get('valor')
    descricao = data.get('descricao', 'Cobrança manual — Mindnutri')
    metodo = data.get('metodo', 'cartao')  # 'cartao' ou 'pix'

    if not telefone or not valor:
        return JsonResponse({'ok': False, 'erro': 'Telefone e valor são obrigatórios'}, status=400)

    try:
        valor = float(valor)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'erro': 'Valor inválido'}, status=400)

    try:
        from utils.asaas import criar_link_cartao_avulso, criar_cobranca_pix
        from utils.whatsapp import enviar_texto

        if metodo == 'pix':
            result = criar_cobranca_pix(telefone, valor, descricao)
            link = result.get('invoice_url', '')
            msg = (
                f"Olá! Segue sua cobrança no valor de R$ {valor:.2f}.\n\n"
                f"Pague via Pix acessando o link:\n{link}\n\n"
                f"Descrição: {descricao}"
            )
        else:
            result = criar_link_cartao_avulso(telefone, valor, descricao)
            link = result.get('url', '')
            msg = (
                f"Olá! Segue sua cobrança no valor de R$ {valor:.2f}.\n\n"
                f"Pague com cartão de crédito:\n{link}\n\n"
                f"Descrição: {descricao}"
            )

        enviar_texto(telefone, msg)

        return JsonResponse({'ok': True, 'link': link, 'metodo': metodo})

    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


@login_required
def api_financeiro_reenviar(request):
    """Reenvia link de pagamento ou gera novo e manda via WhatsApp."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON inválido'}, status=400)

    payment_id = data.get('payment_id', '')
    metodo = data.get('metodo', 'cartao')
    telefone = data.get('telefone', '')

    if not payment_id or not telefone:
        return JsonResponse({'ok': False, 'erro': 'Dados insuficientes'}, status=400)

    try:
        from utils.whatsapp import enviar_texto
        from django.conf import settings as s

        # Buscar cobrança original
        p = _asaas_get(f"payments/{payment_id}")
        # Sempre usar o PLANO_VALOR atual (não o valor antigo da cobrança)
        valor = float(getattr(s, 'PLANO_VALOR', 89.90))
        invoice_url = p.get('invoiceUrl', '')
        descricao = p.get('description', 'Cobrança Mindnutri')

        if metodo == 'pix':
            from utils.asaas import criar_cobranca_pix
            result = criar_cobranca_pix(telefone, valor, descricao)
            link = result.get('invoice_url', '')
            msg = (
                f"Olá! Geramos um novo link Pix para sua cobrança de R$ {valor:.2f}.\n\n"
                f"Acesse: {link}\n\n"
                f"Descrição: {descricao}"
            )
        else:
            if invoice_url:
                link = invoice_url
            else:
                from utils.asaas import criar_link_cartao_avulso
                result = criar_link_cartao_avulso(telefone, valor, descricao)
                link = result.get('url', '')

            msg = (
                f"Olá! Segue o link de pagamento de R$ {valor:.2f}.\n\n"
                f"Pague com cartão: {link}\n\n"
                f"Descrição: {descricao}"
            )

        enviar_texto(telefone, msg)
        return JsonResponse({'ok': True, 'link': link, 'metodo': metodo})

    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


# ── MENSAGENS DO BOT ─────────────────────────────────────────────────

@login_required
def api_mensagens(request):
    """GET: retorna todas as mensagens agrupadas por categoria."""
    from .mensagem_defaults import CATEGORIAS
    MensagemBot.inicializar_defaults()

    mensagens = list(MensagemBot.objects.all().values(
        'chave', 'categoria', 'descricao', 'texto', 'variaveis', 'ordem'
    ))

    # Agrupar por categoria
    grupos = {}
    for cat_key, cat_label in CATEGORIAS:
        grupos[cat_key] = {
            'label': cat_label,
            'mensagens': [],
        }

    for m in mensagens:
        cat = m['categoria']
        if cat in grupos:
            grupos[cat]['mensagens'].append(m)

    # Ordenar mensagens dentro de cada grupo
    for g in grupos.values():
        g['mensagens'].sort(key=lambda x: x['ordem'])

    return JsonResponse({'ok': True, 'grupos': grupos})


@login_required
def api_salvar_mensagens(request):
    """POST: recebe {chave: texto, ...} e atualiza em bulk."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'POST required'}, status=405)

    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON inválido'}, status=400)

    atualizados = 0
    for chave, texto in dados.items():
        rows = MensagemBot.objects.filter(chave=chave).update(texto=texto)
        atualizados += rows

    # Invalidar cache
    from .mensagens_cache import invalidar_cache
    invalidar_cache()

    return JsonResponse({'ok': True, 'atualizados': atualizados})


@login_required
def api_restaurar_mensagem(request):
    """POST: recebe {chave: "..."} e reseta ao texto padrão."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'POST required'}, status=405)

    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON inválido'}, status=400)

    chave = dados.get('chave', '')
    if not chave:
        return JsonResponse({'ok': False, 'erro': 'Chave não informada'}, status=400)

    from .mensagem_defaults import MENSAGENS_PADRAO
    padrao = next((m for m in MENSAGENS_PADRAO if m['chave'] == chave), None)
    if not padrao:
        return JsonResponse({'ok': False, 'erro': 'Chave não encontrada nos padrões'}, status=404)

    MensagemBot.objects.filter(chave=chave).update(texto=padrao['texto'])

    from .mensagens_cache import invalidar_cache
    invalidar_cache()

    return JsonResponse({'ok': True, 'texto': padrao['texto']})


# ── PERDAS DE INGREDIENTES ─────────────────────────────────────────

@login_required
def api_perdas(request):
    """Retorna todas as perdas agrupadas por categoria."""
    from .perdas_defaults import CATEGORIAS_PERDA
    perdas = PerdaIngrediente.carregar_todas()
    categorias = {cat[0]: cat[1] for cat in CATEGORIAS_PERDA}
    return JsonResponse({
        'ok': True,
        'perdas': perdas,
        'categorias': categorias,
    })


@login_required
def api_salvar_perdas(request):
    """Salva alterações em lote nas perdas."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'POST required'}, status=405)
    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON invalido'}, status=400)

    alteracoes = dados.get('alteracoes', [])
    for alt in alteracoes:
        nome = alt.get('nome', '')
        if not nome:
            continue
        PerdaIngrediente.objects.filter(nome=nome).update(
            perda_percentual=int(alt.get('perda_percentual', 0)),
            tipo_perda=alt.get('tipo_perda', 'nenhuma'),
        )
    return JsonResponse({'ok': True, 'salvas': len(alteracoes)})


@login_required
def api_adicionar_perda(request):
    """Adiciona uma nova perda."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'POST required'}, status=405)
    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON invalido'}, status=400)

    nome = (dados.get('nome') or '').strip()
    if not nome:
        return JsonResponse({'ok': False, 'erro': 'Nome obrigatorio'}, status=400)

    if PerdaIngrediente.objects.filter(nome__iexact=nome).exists():
        return JsonResponse({'ok': False, 'erro': 'Ingrediente ja existe'}, status=409)

    PerdaIngrediente.objects.create(
        nome=nome,
        categoria=dados.get('categoria', 'carnes'),
        perda_percentual=int(dados.get('perda_percentual', 0)),
        tipo_perda=dados.get('tipo_perda', 'nenhuma'),
    )
    return JsonResponse({'ok': True})


@login_required
def api_excluir_perda(request):
    """Exclui uma perda pelo nome."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'POST required'}, status=405)
    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON invalido'}, status=400)

    nome = (dados.get('nome') or '').strip()
    deleted, _ = PerdaIngrediente.objects.filter(nome=nome).delete()
    return JsonResponse({'ok': True, 'excluido': deleted > 0})


# ══════════════════════════════════════════════════════════════════════════════
# PRECIFICAÇÃO (Preço + Cupons)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def api_precificacao(request):
    """GET — retorna preço base e lista de cupons."""
    from django.conf import settings as s
    cupons = list(Cupom.objects.all().values(
        'id', 'codigo', 'valor_primeiro_pagamento', 'ativo', 'usos', 'criado_em'
    ))
    for c in cupons:
        c['valor_primeiro_pagamento'] = float(c['valor_primeiro_pagamento'])
        c['criado_em'] = c['criado_em'].strftime('%d/%m/%Y %H:%M') if c['criado_em'] else ''
    return JsonResponse({
        'ok': True,
        'preco_base': float(getattr(s, 'PLANO_VALOR', 89.90)),
        'cupons': cupons,
    })


@login_required
def api_salvar_preco(request):
    """POST — atualiza PLANO_VALOR no .env."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'POST required'}, status=405)
    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON invalido'}, status=400)

    novo_valor = dados.get('valor')
    if novo_valor is None:
        return JsonResponse({'ok': False, 'erro': 'valor obrigatorio'}, status=400)

    try:
        novo_valor = float(novo_valor)
        if novo_valor <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'erro': 'Valor inválido'}, status=400)

    # Atualizar no runtime
    from django.conf import settings as s
    s.PLANO_VALOR = novo_valor

    # Persistir no .env
    env_path = os.path.join(s.BASE_DIR, '.env')
    _atualizar_env(env_path, 'PLANO_VALOR', f'{novo_valor:.2f}')

    return JsonResponse({'ok': True, 'valor': novo_valor})


def _atualizar_env(env_path, chave, valor):
    """Atualiza ou adiciona uma variável no arquivo .env."""
    linhas = []
    encontrou = False
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            linhas = f.readlines()

    novas = []
    for linha in linhas:
        if linha.strip().startswith(f'{chave}=') or linha.strip().startswith(f'{chave} ='):
            novas.append(f'{chave}={valor}\n')
            encontrou = True
        else:
            novas.append(linha)

    if not encontrou:
        novas.append(f'{chave}={valor}\n')

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(novas)


@login_required
def api_cupom_salvar(request):
    """POST — cria ou edita um cupom."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'POST required'}, status=405)
    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON invalido'}, status=400)

    cupom_id = dados.get('id')
    codigo = (dados.get('codigo') or '').strip().upper()
    valor = dados.get('valor')
    ativo = dados.get('ativo', True)

    if not codigo:
        return JsonResponse({'ok': False, 'erro': 'Código obrigatório'}, status=400)
    try:
        valor = float(valor)
        if valor < 0:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'erro': 'Valor inválido'}, status=400)

    if cupom_id:
        try:
            cupom = Cupom.objects.get(pk=cupom_id)
            cupom.codigo = codigo
            cupom.valor_primeiro_pagamento = valor
            cupom.ativo = ativo
            cupom.save()
        except Cupom.DoesNotExist:
            return JsonResponse({'ok': False, 'erro': 'Cupom não encontrado'}, status=404)
    else:
        if Cupom.objects.filter(codigo__iexact=codigo).exists():
            return JsonResponse({'ok': False, 'erro': 'Código já existe'}, status=400)
        cupom = Cupom.objects.create(
            codigo=codigo,
            valor_primeiro_pagamento=valor,
            ativo=ativo,
        )

    return JsonResponse({'ok': True, 'id': cupom.pk})


@login_required
def api_cupom_excluir(request):
    """POST — exclui um cupom."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'POST required'}, status=405)
    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON invalido'}, status=400)

    cupom_id = dados.get('id')
    deleted, _ = Cupom.objects.filter(pk=cupom_id).delete()
    return JsonResponse({'ok': True, 'excluido': deleted > 0})
