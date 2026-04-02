from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('admin/login/', auth_views.LoginView.as_view(template_name='painel/login.html'), name='login'),
    path('admin/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('admin/', include('painel.urls')),
    path('', include('agente_app.urls')),
]
