#!/bin/bash

# Fail on any error
set -e

# Wait for database
echo "------------------------------------------------"
echo "🔬 BEVERAGE LABORATORY STARTUP PROTOCOL"
echo "------------------------------------------------"
echo "Waiting for PostgreSQL at $DATABASE_HOST:$DATABASE_PORT..."

while ! nc -z $DATABASE_HOST $DATABASE_PORT; do
  sleep 0.1
done

echo "✅ PostgreSQL is reachable."

# Generate new migrations if needed
echo "Step 1: Checking for molecular model changes..."
python manage.py makemigrations --no-input

# Apply migrations
echo "Step 2: Calibrating database schema (Applying migrations)..."
python manage.py migrate --no-input

# Create default superuser if it doesn't exist
echo "Step 3: Verifying laboratory administrator..."
python manage.py shell <<EOF
from django.contrib.auth import get_user_model
import os

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@beveragelab.local')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'adminpass123')

if not User.objects.filter(username=username).exists():
    print(f"Creating default lab administrator: {username}")
    User.objects.create_superuser(username, email, password)
else:
    print(f"Laboratory administrator '{username}' is synchronized.")
EOF

# Start server
echo "------------------------------------------------"
echo "🚀 INITIATING LABORATORY SERVER"
echo "------------------------------------------------"

# Deployment verification - confirm which middleware and settings are active
echo "Step 4: Deployment verification..."
python -c "
from django.conf import settings
import django
django.setup()
csrf_mw = [m for m in settings.MIDDLEWARE if 'csrf' in m.lower() or 'Csrf' in m]
print(f'CSRF Middleware: {csrf_mw}')
print(f'CSRF_TRUSTED_ORIGINS: {settings.CSRF_TRUSTED_ORIGINS}')
print(f'SECURE_PROXY_SSL_HEADER: {getattr(settings, \"SECURE_PROXY_SSL_HEADER\", \"NOT SET\")}')
print(f'USE_X_FORWARDED_HOST: {getattr(settings, \"USE_X_FORWARDED_HOST\", \"NOT SET\")}')
"

exec "$@"
