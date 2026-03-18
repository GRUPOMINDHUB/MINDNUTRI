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
]
