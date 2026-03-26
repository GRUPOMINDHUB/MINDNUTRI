from django.urls import path
from . import views

urlpatterns = [
    path('',                        views.dashboard,          name='dashboard'),
    path('assinantes/',             views.assinantes,         name='assinantes'),
    path('assinantes/<int:pk>/',    views.assinante_detalhe,  name='assinante_detalhe'),
    path('assinantes/<int:pk>/status/', views.toggle_status,  name='toggle_status'),
    path('fichas/',                 views.fichas,             name='fichas'),
    path('notificacoes/',           views.notificacoes,       name='notificacoes'),
    path('api/stats/',              views.api_stats,          name='api_stats'),
    # Configurações da IA
    path('configuracoes/',          views.configuracoes_ia,       name='configuracoes_ia'),
    path('api/salvar-prompt/',      views.api_salvar_prompt,      name='api_salvar_prompt'),
    path('api/salvar-parametros/',  views.api_salvar_parametros,  name='api_salvar_parametros'),
    path('api/preview-chat/',       views.api_preview_chat,       name='api_preview_chat'),
    # Edição de assinante
    path('assinantes/<int:pk>/editar/', views.api_editar_assinante, name='api_editar_assinante'),
    # Financeiro
    path('financeiro/',                   views.financeiro,               name='financeiro'),
    path('api/financeiro/dados/',         views.api_financeiro_dados,     name='api_financeiro_dados'),
    path('api/financeiro/cobranca/',      views.api_financeiro_cobranca,  name='api_financeiro_cobranca'),
    path('api/financeiro/nova-cobranca/', views.api_financeiro_nova_cobranca, name='api_financeiro_nova_cobranca'),
    path('api/financeiro/reenviar/',      views.api_financeiro_reenviar,  name='api_financeiro_reenviar'),
    # Conexão WhatsApp
    path('api/conexao/status/',     views.api_conexao_status,     name='api_conexao_status'),
    path('api/conexao/qrcode/',     views.api_conexao_qrcode,     name='api_conexao_qrcode'),
    path('api/conexao/acao/',       views.api_conexao_acao,       name='api_conexao_acao'),
    # Mensagens do Bot
    path('api/mensagens/',              views.api_mensagens,            name='api_mensagens'),
    path('api/salvar-mensagens/',       views.api_salvar_mensagens,     name='api_salvar_mensagens'),
    path('api/restaurar-mensagem/',     views.api_restaurar_mensagem,   name='api_restaurar_mensagem'),
    # Perdas de Ingredientes
    path('api/perdas/',                 views.api_perdas,               name='api_perdas'),
    path('api/salvar-perdas/',          views.api_salvar_perdas,        name='api_salvar_perdas'),
    path('api/adicionar-perda/',        views.api_adicionar_perda,      name='api_adicionar_perda'),
    path('api/excluir-perda/',          views.api_excluir_perda,        name='api_excluir_perda'),
    # Precificação (Preço + Cupons)
    path('api/precificacao/',            views.api_precificacao,         name='api_precificacao'),
    path('api/salvar-preco/',            views.api_salvar_preco,         name='api_salvar_preco'),
    path('api/cupom/salvar/',            views.api_cupom_salvar,         name='api_cupom_salvar'),
    path('api/cupom/excluir/',           views.api_cupom_excluir,        name='api_cupom_excluir'),
]
