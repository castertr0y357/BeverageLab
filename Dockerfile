# Use a slim Python 3.12 image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=soda_mixer.settings

# Set working directory
WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create a non-privileged user and group, and change ownership of the application folder
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser && \
    chown -R appuser:appgroup /app

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
