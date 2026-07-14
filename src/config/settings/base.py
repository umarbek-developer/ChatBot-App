# from pathlib import Path
import os

import environ

env = environ.Env()

BASE_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!

DEBUG = env("DEBUG")
BASE_URL = env("BASE_URL")


if DEBUG == "1":
    DEBUG = True
else:
    DEBUG = False

# Application definition

INSTALLED_APPS = [
    "daphne",
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # third-party apps
    'channels',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'drf_spectacular',

    # own apps
    'apps.common',
    'apps.accounts',
    'apps.groups',
    'apps.messaging',
    'apps.utils',
    'apps.users',
    'apps.chat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR, 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ]
        }
    }
]

# WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators


# Tolerate empty (present-but-blank) env vars, which are common in .env files.
REDIS_HOST = env("REDIS_HOST", default="").strip() or "127.0.0.1"
_redis_port = env("REDIS_PORT", default="").strip()
REDIS_PORT = int(_redis_port) if _redis_port.isdigit() else 6379
REDIS_PASSWORD = env("REDIS_PASSWORD", default="").strip()

# Build a redis:// URL for a given logical db, embedding auth when a password is
# configured. Logical dbs are kept separate: Celery broker/result (0), the
# channel layer (1) and ephemeral realtime state (2).
_redis_auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""


def _redis_url(db):
    return f"redis://{_redis_auth}{REDIS_HOST}:{REDIS_PORT}/{db}"


# Redis-backed channel layer: required for cross-process fan-out (multiple
# Daphne/Uvicorn workers) and the ephemeral presence/typing state below.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [_redis_url(1)],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}

# Dedicated Redis connection (db 2) for ephemeral realtime state — presence
# sets, last-seen, typing/recording throttles — kept out of the Celery broker db.
REDIS_REALTIME_URL = _redis_url(2)



AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        # 'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'api.pagination.CustomPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
        # 'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'login': '5/day',
        'voice': '120/hour',
        'register': '10/hour',
        'otp_resend': '5/hour',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'apps.common.exceptions.custom_exception_handler',
    # 'UNAUTHENTICATED_USER': 'users.models.AnonymousUser',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Realtime Messaging Platform API',
    'DESCRIPTION': (
        'Telegram/Discord/Slack-style real-time messaging platform: groups, '
        'channels, direct messages, presence, notifications and media.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/v[0-9]+',
}



LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Tashkent'

USE_I18N = True

USE_TZ = False

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.1/howto/static-files/

STATIC_URL = '/static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

AUTH_USER_MODEL = 'users.User'

# Entry points (client-side JWT gate uses these paths; also correct for any
# @login_required view / the admin login redirect).
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/chat/'
LOGOUT_REDIRECT_URL = '/login/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


DB_TYPE = env("DB_TYPE")
DATABASES = {}
if DB_TYPE == "psql":
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "CONN_MAX_AGE": 60,
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
    }
else:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR + "/db.sqlite3",
    }



EMAIL_BACKEND = env("EMAIL_BACKEND", default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env("EMAIL_SMTP_HOST", default='smtp.gmail.com')
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST", default="")            # the Gmail sender address
EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD", default="")    # Gmail App Password (16 chars)
# A hung SMTP handshake must never block a request worker indefinitely.
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=20)
# Gmail rejects a From that isn't the authenticated account, so default to it.
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default=(f"Pulse <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "webmaster@localhost"),
)
SERVER_EMAIL = EMAIL_HOST_USER or "root@localhost"

# One-time-password policy.
OTP_TTL_MINUTES = env.int("OTP_TTL_MINUTES", default=10)
# Send OTP emails synchronously in DEBUG (instant, no worker required) and via
# Celery in production. Override explicitly with EMAIL_USE_CELERY if needed.
EMAIL_USE_CELERY = env.bool("EMAIL_USE_CELERY", default=not DEBUG)

BASE_URL_LINK = env("BASE_URL_LINK")

# ---- Logging: the email pipeline must never fail silently ----
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "loggers": {
        "email": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "api": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}


# ---- Celery ----
# Prefer explicit env overrides (e.g. a remote or passworded broker); otherwise
# fall back to the local Redis (db 0) derived above so REDIS_PASSWORD is honoured.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="").strip() or _redis_url(0)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="").strip() or _redis_url(0)

# autodiscover_tasks() only scans INSTALLED_APPS. send_otp_email_task lives under
# api/ (not an installed app), so the worker must import it explicitly or it will
# reject the message with "unregistered task" — and OTP email uses Celery in prod.
CELERY_IMPORTS = ("api.auth.tasks",)

CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_IGNORE_RESULT = False
CELERY_TASK_SOFT_TIME_LIMIT = 60

