from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from .models import Assinante, FichaTecnica, Notificacao


def _stats(request):
    """Retorna estatísticas globais para o contexto base."""
    hoje = timezone.localdate()
    total         = Assinante.objects.count()
    ativos        = Assinante.objects.filter(status='ativo').count()
    bloqueados    = Assinante.objects.filter(status='bloqueado').count()
    inadimplentes = Assinante.objects.filter(status='inadimplente').count()
    novas_fichas  = FichaTecnica.objects.filter(criada_em__date=hoje).count()
    notif_nao_lidas = Notificacao.objects.filter(lida=False).count()
    receita_mensal = ativos * 59.90
    return {
        'total_assinantes': total,
        'ativos': ativos,
        'bloqueados': bloqueados,
        'inadimplentes': inadimplentes,
        'novas_fichas_hoje': novas_fichas,
        'notif_nao_lidas': notif_nao_lidas,
        'receita_mensal': receita_mensal,
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
