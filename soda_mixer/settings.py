"""Django settings for soda_mixer project."""

from pathlib import Path
import os
import sys

sys.stderr.write("🔬 [Startup settings.py] BOOTING DIANGO SERVER\n")
sys.stderr.flush()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def bootstrap_env():
    import secrets
    
    env_path = BASE_DIR / '.env'
    example_path = BASE_DIR / '.env.example'
    
    if not env_path.exists():
        if example_path.exists():
            sys.stderr.write("🔬 [Startup] - .env file missing. Bootstrapping from .env.example...\n")
            sys.stderr.flush()
            content = example_path.read_text(encoding='utf-8')
            # Generate a secure random Django SECRET_KEY
            chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
            secret_key = ''.join(secrets.choice(chars) for _ in range(50))
            
            lines = []
            for line in content.splitlines():
                if line.startswith('SECRET_KEY='):
                    lines.append(f"SECRET_KEY={secret_key}")
                else:
                    lines.append(line)
            content = '\n'.join(lines)
            
            try:
                env_path.write_text(content, encoding='utf-8')
                if os.name != 'nt':
                    try:
                        env_path.chmod(0o600)
                    except Exception:
                        pass
                sys.stderr.write("✅ [Startup] - .env file bootstrapped and secured.\n")
                sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"⚠️ [Startup] - Failed to write .env file: {e}\n")
                sys.stderr.flush()

    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip()
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            sys.stderr.write(f"⚠️ [Startup] - Error reading .env: {e}\n")
            sys.stderr.flush()


# Run bootstrapping
bootstrap_env()


# Startup configuration validation
REQUIRED_ENV_VARS = [
    'SECRET_KEY',
    'POSTGRES_DB',
    'POSTGRES_USER',
    'POSTGRES_PASSWORD',
    'DATABASE_HOST',
    'DATABASE_PORT',
]
missing_vars = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
if missing_vars:
    sys.stderr.write(f"❌ [Startup] - Config Error - Missing required environment variables: {', '.join(missing_vars)}\n")
    sys.stderr.write("Please check your configuration files and ensure they are populated.\n")
    sys.stderr.flush()
    sys.exit(1)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')

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
    'soda_mixer.flavors.apps.FlavorsConfig',
]

MIDDLEWARE = [
    'soda_mixer.flavors.middleware_correlation.LaboratoryCorrelationMiddleware',
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

# Speed up password hashing in tests to optimize execution times
if 'test' in sys.argv or any('test' in arg for arg in sys.argv):
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]