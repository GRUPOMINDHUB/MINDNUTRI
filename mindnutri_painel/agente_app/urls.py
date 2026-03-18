from django.urls import path
from agente_app import views

urlpatterns = [
    path('webhook/whatsapp/', views.webhook_whatsapp, name='webhook_whatsapp'),
    path('webhook/asaas/',    views.webhook_asaas,    name='webhook_asaas'),
]
