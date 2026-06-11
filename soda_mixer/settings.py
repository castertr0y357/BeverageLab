"""Django settings for soda_mixer project."""

from pathlib import Path
import os
import sys

sys.stderr.write("🔬 [Startup settings.py] BOOTING DIANGO SERVER\n")
sys.stderr.flush()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-sodamixer-k+^*c1*gx3ladold+7umgx_xz$!+bdncu3x%@^9x*))7%_n&d0'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

# Reverse proxy support
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Build CSRF_TRUSTED_ORIGINS list from environment config and fallbacks
CSRF_TRUSTED_ORIGINS = []

# 1. Direct environment configuration
raw_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if raw_csrf:
    for origin in raw_csrf.split(','):
        origin = origin.strip()
        if origin:
            CSRF_TRUSTED_ORIGINS.append(origin)

# 2. Derive from SERVICE_URL_WEB
service_url = os.environ.get('SERVICE_URL_WEB', '').strip()
if service_url:
    CSRF_TRUSTED_ORIGINS.append(service_url)
    if service_url.startswith('http://'):
        CSRF_TRUSTED_ORIGINS.append(service_url.replace('http://', 'https://'))
    elif service_url.startswith('https://'):
        CSRF_TRUSTED_ORIGINS.append(service_url.replace('https://', 'http://'))

# 3. Derive from SERVICE_FQDN_WEB
service_fqdn = os.environ.get('SERVICE_FQDN_WEB', '').strip()
if service_fqdn:
    CSRF_TRUSTED_ORIGINS.append(f"http://{service_fqdn}")
    CSRF_TRUSTED_ORIGINS.append(f"https://{service_fqdn}")

# 4. Derive from ALLOWED_HOSTS
for host in ALLOWED_HOSTS:
    host = host.strip()
    if host and host != '*':
        if host.startswith('.'):
            host = host[1:]
        CSRF_TRUSTED_ORIGINS.append(f"http://{host}")
        CSRF_TRUSTED_ORIGINS.append(f"https://{host}")

# De-duplicate the list
CSRF_TRUSTED_ORIGINS = list(set(CSRF_TRUSTED_ORIGINS))





# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'soda_mixer.flavors',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'soda_mixer.flavors.middleware.LaboratoryCsrfMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'soda_mixer.flavors.middleware.LaboratoryAccessMiddleware',
]

ROOT_URLCONF = 'soda_mixer.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'soda_mixer' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'soda_mixer.wsgi.application'


# Database - PostgreSQL configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'soda_mixer'),
        'USER': os.environ.get('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.environ.get('DATABASE_HOST', 'localhost'),
        'PORT': os.environ.get('DATABASE_PORT', '5432'),
    }
}


# Password validation
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


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'soda_mixer' / 'static']

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication Protocol Configuration
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'