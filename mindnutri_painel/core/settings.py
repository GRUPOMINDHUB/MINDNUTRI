from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent.parent


def _split_env_list(value: str):
    return [item.strip() for item in value.split(",") if item.strip()]

# ── SEGURANÇA ────────────────────────────────────────────────────
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "mindnutri-dev-key-TROQUE-EM-PRODUCAO")

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = _split_env_list(
    os.getenv("DJANGO_ALLOWED_HOSTS", "grupomindhub.com.br,www.grupomindhub.com.br,localhost,127.0.0.1")
)

CSRF_TRUSTED_ORIGINS = _split_env_list(
    os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "https://grupomindhub.com.br,https://www.grupomindhub.com.br,http://localhost,http://127.0.0.1",
    )
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'painel',
    'agente_app',
    'assinaturas',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ── BANCO DE DADOS ───────────────────────────────────────────────
_DB_URL = os.getenv("DATABASE_URL", "")
if _DB_URL:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(
            _DB_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

FORCE_SCRIPT_NAME = os.getenv("DJANGO_FORCE_SCRIPT_NAME", "").strip() or None
STATIC_URL = f"{FORCE_SCRIPT_NAME or ''}/static/"
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── LOGGING (com rotação) ────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(name)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'agente_debug.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# ── Sentry (opcional — defina SENTRY_DSN no .env) ────────────────
_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=_SENTRY_DSN, traces_sample_rate=0.1)
    except ImportError:
        pass

LOGIN_URL = '/mindnutri/login/'
LOGIN_REDIRECT_URL = '/mindnutri/admin/'
LOGOUT_REDIRECT_URL = '/mindnutri/login/'

# ── HTTPS / Cookies seguros em produção ──────────────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    CSRF_TRUSTED_ORIGINS = [
        f"https://{h.strip()}"
        for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    ]

# ── Site URL (para webhooks, links externos) ───────────────────
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

# ── Mindnutri Configs ────────────────────────────────────────────
# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Anthropic (Vision)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# Evolution API
EVOLUTION_API_URL      = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY      = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE     = os.getenv("EVOLUTION_INSTANCE", "mindnutri")

# Asaas
ASAAS_API_KEY  = os.getenv("ASAAS_API_KEY", "")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://sandbox.asaas.com/api/v3")
ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "")

# Storage
STORAGE_TYPE       = os.getenv("STORAGE_TYPE", "local")
STORAGE_LOCAL_PATH = os.getenv("STORAGE_LOCAL_PATH", "./arquivos_gerados")

# Gestor
GESTOR_WHATSAPP = os.getenv("GESTOR_WHATSAPP", "")

# Grupo WhatsApp Alertas
WHATSAPP_GRUPO_ALERTAS = os.getenv("WHATSAPP_GRUPO_ALERTAS", "")

# Plano
PLANO_VALOR         = float(os.getenv("PLANO_VALOR", "89.90"))
PLANO_FICHAS_LIMITE = int(os.getenv("PLANO_FICHAS_LIMITE", "30"))

# Modelo OpenAI
OPENAI_MODEL = "gpt-4.1"
