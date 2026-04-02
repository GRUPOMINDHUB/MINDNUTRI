from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from core import views as core_views

urlpatterns = [
    path('', core_views.home, name='home'),
    path('mindnutri/', core_views.mindnutri_landing, name='mindnutri_landing'),
    path('mindnutri/django-admin/', admin.site.urls),
    path('mindnutri/login/', auth_views.LoginView.as_view(template_name='painel/login.html'), name='login'),
    path('mindnutri/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('mindnutri/admin/', include('painel.urls')),
    path('', include('agente_app.urls')),
]
