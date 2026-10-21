"""Settings and data management views."""

import gzip
import json
import logging
import os
import subprocess
import sys
from typing import Dict, Any, Tuple

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib.auth.decorators import user_passes_test

from ..models import SystemConfiguration, LLMProvider

logger = logging.getLogger(__name__)


def _get_db_env_and_params() -> Tuple[Dict[str, str], str, str, str, str]:
    """Extract database connection parameters and build subprocess environment."""
    db_conf = settings.DATABASES.get('default', {})
    db_name = str(db_conf.get('NAME') or os.environ.get('POSTGRES_DB', 'soda_mixer'))
    db_user = str(db_conf.get('USER') or os.environ.get('POSTGRES_USER', 'postgres'))
    db_password = str(db_conf.get('PASSWORD') or os.environ.get('POSTGRES_PASSWORD', 'postgres'))
    db_host = str(db_conf.get('HOST') or os.environ.get('DATABASE_HOST', 'localhost'))
    db_port = str(db_conf.get('PORT') or os.environ.get('DATABASE_PORT', '5432'))

    env = os.environ.copy()
    env['PGPASSWORD'] = db_password
    return env, db_name, db_user, db_host, db_port


@user_passes_test(lambda u: u.is_staff)
def settings_view(request: HttpRequest) -> HttpResponse:
    """Settings page for backups and system management."""
    config = SystemConfiguration.get_config()
    providers = LLMProvider.objects.all().order_by('name')
    return render(request, 'flavors/settings.html', {
        'config': config,
        'providers': providers,
        'provider_types': LLMProvider.PROVIDER_CHOICES
    })


@user_passes_test(lambda u: u.is_staff)
@csrf_exempt
@require_http_methods(["POST"])
def save_settings_api(request: HttpRequest) -> JsonResponse:
    """Update global system configuration."""
    try:
        data = json.loads(request.body)
        config = SystemConfiguration.get_config()
        config.mealie_url = data.get('mealie_url', '').strip()
        config.mealie_api_key = data.get('mealie_api_key', '').strip()
        config.save()
        logger.info("SystemSettings - Info - Global laboratory configuration updated.")
        return JsonResponse({'status': 'success', 'message': 'Configuration saved successfully.'})
    except Exception as e:
        logger.error(f"SystemSettings - Error - Failed to save global settings: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@user_passes_test(lambda u: u.is_staff)
def export_data(request: HttpRequest) -> HttpResponse:
    """Export a compressed PostgreSQL database backup (.sql.gz)."""
    try:
        env, db_name, db_user, db_host, db_port = _get_db_env_and_params()
        command = [
            'pg_dump',
            '--no-owner',
            '--no-acl',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            db_name,
        ]

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        stdout, stderr = process.communicate(timeout=120)

        if process.returncode != 0:
            err_msg = stderr.decode('utf-8', errors='replace').strip()
            logger.error(f"DatabaseBackup - Error - pg_dump failed: {err_msg}")
            return HttpResponse("Backup Export Failed: Unable to dump database.", status=500)

        compressed_data = gzip.compress(stdout)
        response = HttpResponse(compressed_data, content_type='application/gzip')
        filename = f"beveragelab_backup_{timezone.now().strftime('%Y%m%d_%H%M%S')}.sql.gz"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        logger.info(f"DatabaseBackup - Info - Successfully generated database backup: {filename}")
        return response
    except Exception as e:
        logger.error(f"DatabaseBackup - Error - Failed to export database backup: {e}")
        return HttpResponse(f"Backup Export Failed: {str(e)}", status=500)


def _extract_and_validate_sql_payload(raw_bytes: bytes) -> bytes:
    """Validate file magic bytes (gzip or plain SQL) and return uncompressed SQL bytes."""
    if not raw_bytes:
        raise ValueError("Uploaded backup file is empty.")

    # Check gzip magic signature (1f 8b)
    if raw_bytes.startswith(b'\x1f\x8b'):
        try:
            sql_bytes = gzip.decompress(raw_bytes)
        except Exception as exc:
            raise ValueError("Corrupted gzip backup archive.") from exc
    else:
        sql_bytes = raw_bytes

    # Verify the uncompressed content looks like a valid SQL dump
    sample = sql_bytes[:2048].lstrip()
    if sample.startswith(b'\xef\xbb\xbf'):
        sample = sample[3:].lstrip()

    try:
        sample_str = sample.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError("Invalid file signature. File is not a valid SQL or .sql.gz database backup.") from exc

    valid_prefixes = (
        '--',
        '/*',
        'SET ',
        'SELECT ',
        'CREATE ',
        'DROP ',
        'ALTER ',
        'INSERT ',
        'COPY ',
        'BEGIN',
        '\\connect',
        '\\restrict',
    )
    if not sample_str or not any(sample_str.upper().startswith(p.upper()) for p in valid_prefixes):
        raise ValueError("Invalid file signature. File is not a valid SQL or .sql.gz database backup.")

    return sql_bytes


@user_passes_test(lambda u: u.is_staff)
@csrf_exempt
@require_http_methods(["POST"])
def import_data(request: HttpRequest) -> JsonResponse:
    """Restore the database from a compressed (.sql.gz) or plain (.sql) PostgreSQL backup file."""
    if 'backup_file' not in request.FILES:
        logger.warning("DatabaseRestore - Warning - Restore requested but no file was provided.")
        return JsonResponse({'error': 'No file provided'}, status=400)

    try:
        uploaded_file = request.FILES['backup_file']
        raw_bytes = uploaded_file.read()

        try:
            sql_content = _extract_and_validate_sql_payload(raw_bytes)
        except ValueError as ve:
            logger.warning(f"DatabaseRestore - Warning - Backup file failed signature verification: {ve}")
            return JsonResponse({'error': str(ve)}, status=400)

        env, db_name, db_user, db_host, db_port = _get_db_env_and_params()

        # Close active Django ORM connections so schema drop/recreate is not blocked (only outside of test runs)
        if not getattr(settings, 'IS_TESTING', False) and 'test' not in sys.argv:
            connections.close_all()

        # 1. Clean current public schema
        clean_command = [
            'psql',
            '-v', 'ON_ERROR_STOP=1',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            '-d', db_name,
            '-c', 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
        ]
        clean_proc = subprocess.run(
            clean_command,
            capture_output=True,
            env=env,
            timeout=60
        )
        if clean_proc.returncode != 0:
            err_msg = clean_proc.stderr.decode('utf-8', errors='replace').strip()
            logger.error(f"DatabaseRestore - Error - Schema cleanup failed: {err_msg}")
            return JsonResponse({'error': 'Database schema cleanup failed prior to restore.'}, status=500)

        # 2. Restore SQL dump into the clean schema
        restore_command = [
            'psql',
            '-v', 'ON_ERROR_STOP=1',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            '-d', db_name,
        ]
        restore_proc = subprocess.Popen(
            restore_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        _, stderr = restore_proc.communicate(input=sql_content, timeout=180)

        if restore_proc.returncode != 0:
            err_msg = stderr.decode('utf-8', errors='replace').strip()
            logger.error(f"DatabaseRestore - Error - psql restore failed: {err_msg}")
            return JsonResponse({'error': 'Database restore failed during SQL execution.'}, status=500)

        # 3. Ensure any newer migrations on this instance are applied seamlessly
        try:
            call_command('migrate', interactive=False, verbosity=0)
        except Exception as mig_err:
            logger.warning(f"DatabaseRestore - Warning - Post-restore migration check returned warning: {mig_err}")

        logger.info("DatabaseRestore - Info - Successfully restored database from backup archive.")
        return JsonResponse({
            'status': 'success',
            'message': 'Database backup restored and calibrated successfully.'
        })

    except Exception as e:
        logger.error(f"DatabaseRestore - Error - Failed to restore database from backup file: {e}")
        return JsonResponse({'error': str(e)}, status=500)
