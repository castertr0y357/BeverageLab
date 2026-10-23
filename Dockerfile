# Use a slim Python 3.12 image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=soda_mixer.settings

# Set working directory
WORKDIR /app

# Install system dependencies for psycopg2, PostgreSQL client, and libnfs userspace utilities
RUN apt-get update && apt-get install -y \
    libpq-dev \
    postgresql-client \
    libnfs14 \
    libnfs-dev \
    libnfs-utils \
    gcc \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Pre-collect static assets for WhiteNoise
RUN SECRET_KEY=build-time-secret-key-placeholder \
    POSTGRES_DB=build_db \
    POSTGRES_USER=build_user \
    POSTGRES_PASSWORD=build_pw \
    DATABASE_HOST=localhost \
    DATABASE_PORT=5432 \
    python manage.py collectstatic --no-input

# Create a non-privileged user and group, create /backups and /staticfiles directories, and set permissions
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser && \
    mkdir -p /backups /staticfiles /app/staticfiles && \
    chown -R appuser:appgroup /app /backups /staticfiles && \
    chmod 700 /backups

# Copy entrypoint script and make it executable
RUN chmod +x entrypoint.sh

# Expose port 8000
EXPOSE 8000

# Switch to the non-privileged user
USER appuser

# Run the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

# Start Gunicorn with async gevent workers to handle long-running LLM calls without blocking
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--timeout", "120", "--workers", "3", "--worker-class", "gevent", "soda_mixer.wsgi:application"]
