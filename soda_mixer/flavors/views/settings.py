"""Settings and data management views."""

import gzip
import json
import logging
import os
import re
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

from ..models import SystemConfiguration, LLMProvider, BackupConfiguration, BackupRecord
from ..tasks_registry import submit_task

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
    backup_config = BackupConfiguration.get_config()
    backup_records = BackupRecord.objects.all().order_by('-created_at')[:50]
    providers = LLMProvider.objects.all().order_by('name')
    return render(request, 'flavors/settings.html', {
        'config': config,
        'backup_config': backup_config,
        'backup_records': backup_records,
        'storage_choices': BackupConfiguration.STORAGE_CHOICES,
        'weekday_choices': BackupConfiguration.WEEKDAY_CHOICES,
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


def _sanitize_sql_for_compat(sql_bytes: bytes) -> bytes:
    """Sanitize SQL dump to ensure cross-version PostgreSQL compatibility.

    PostgreSQL 17+ pg_dump emits 'SET transaction_timeout = 0;' which causes PostgreSQL <= 16
    to fail with 'ERROR: unrecognized configuration parameter "transaction_timeout"' when
    executed with ON_ERROR_STOP=1.
    """
    pattern = rb'(?im)^([ \t]*(?:SET\s+transaction_timeout|SELECT\s+pg_catalog\.set_config\(\s*\'transaction_timeout).*)$'
    return re.sub(pattern, rb'-- \1', sql_bytes)


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

    return _sanitize_sql_for_compat(sql_bytes)


def _restore_sql_into_database(sql_content: bytes, preserve_config: bool = True) -> None:
    """Executes schema clean, psql restore, migrations, and optional backup config preservation."""
    sql_content = _sanitize_sql_for_compat(sql_content)
    env, db_name, db_user, db_host, db_port = _get_db_env_and_params()

    saved_backup_config_data = None
    saved_backup_records_data = []

    if preserve_config:
        try:
            curr_conf = BackupConfiguration.get_config()
            saved_backup_config_data = {
                'is_enabled': curr_conf.is_enabled,
                'backup_time': curr_conf.backup_time,
                'weekly_day': curr_conf.weekly_day,
                'monthly_day': curr_conf.monthly_day,
                'keep_daily': curr_conf.keep_daily,
                'keep_weekly': curr_conf.keep_weekly,
                'keep_monthly': curr_conf.keep_monthly,
                'preserve_config_on_restore': curr_conf.preserve_config_on_restore,
                'storage_type': curr_conf.storage_type,
                'local_path': curr_conf.local_path,
                's3_endpoint_url': curr_conf.s3_endpoint_url,
                's3_bucket': curr_conf.s3_bucket,
                's3_region': curr_conf.s3_region,
                's3_access_key': curr_conf.s3_access_key,
                's3_secret_key': curr_conf.s3_secret_key,
                's3_prefix': curr_conf.s3_prefix,
                'cifs_server': curr_conf.cifs_server,
                'cifs_share': curr_conf.cifs_share,
                'cifs_subpath': curr_conf.cifs_subpath,
                'cifs_username': curr_conf.cifs_username,
                'cifs_password': curr_conf.cifs_password,
                'cifs_domain': curr_conf.cifs_domain,
                'nfs_server': curr_conf.nfs_server,
                'nfs_export': curr_conf.nfs_export,
                'nfs_subpath': curr_conf.nfs_subpath,
                'encryption_passphrase': curr_conf.encryption_passphrase,
                'webhook_url': curr_conf.webhook_url,
            }
            for rec in BackupRecord.objects.all():
                saved_backup_records_data.append({
                    'uuid': rec.uuid,
                    'filename': rec.filename,
                    'tier': rec.tier,
                    'storage_type': rec.storage_type,
                    'file_size': rec.file_size,
                    'is_encrypted': rec.is_encrypted,
                    'status': rec.status,
                    'error_message': rec.error_message,
                    'created_at': rec.created_at,
                })
        except Exception as e:
            logger.warning(f"DatabaseRestore - Warning - Could not snapshot active backup config: {e}")

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
        raise RuntimeError(f"Database schema cleanup failed prior to restore: {err_msg}")

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
        raise RuntimeError(f"Database restore failed during SQL execution: {err_msg}")

    # 3. Ensure any newer migrations on this instance are applied seamlessly
    try:
        call_command('migrate', interactive=False, verbosity=0)
    except Exception as mig_err:
        logger.warning(f"DatabaseRestore - Warning - Post-restore migration check returned warning: {mig_err}")

    # 4. Restore preserved backup schedule and records
    if preserve_config and saved_backup_config_data:
        try:
            curr_conf = BackupConfiguration.get_config()
            for k, v in saved_backup_config_data.items():
                setattr(curr_conf, k, v)
            curr_conf.save()

            for rdata in saved_backup_records_data:
                BackupRecord.objects.update_or_create(
                    uuid=rdata['uuid'],
                    defaults=rdata
                )
            logger.info("DatabaseRestore - Info - Preserved active backup configuration and catalog after restore.")
        except Exception as e:
            logger.warning(f"DatabaseRestore - Warning - Failed to re-apply preserved backup config: {e}")


@user_passes_test(lambda u: u.is_staff)
@csrf_exempt
@require_http_methods(["POST"])
def import_data(request: HttpRequest) -> JsonResponse:
    """Restore the database from an uploaded compressed (.sql.gz) or plain (.sql) PostgreSQL backup file."""
    if 'backup_file' not in request.FILES:
        logger.warning("DatabaseRestore - Warning - Restore requested but no file was provided.")
        return JsonResponse({'error': 'No file provided'}, status=400)

    try:
        uploaded_file = request.FILES['backup_file']
        raw_bytes = uploaded_file.read()
        passphrase = request.POST.get('passphrase', '').strip()

        # Decrypt if encrypted
        if raw_bytes.startswith(b"BLABENC1"):
            from ..backup_service import decrypt_payload
            try:
                raw_bytes = decrypt_payload(raw_bytes, passphrase)
            except Exception as dec_err:
                return JsonResponse({'error': str(dec_err)}, status=400)

        try:
            sql_content = _extract_and_validate_sql_payload(raw_bytes)
        except ValueError as ve:
            logger.warning(f"DatabaseRestore - Warning - Backup file failed signature verification: {ve}")
            return JsonResponse({'error': str(ve)}, status=400)

        curr_conf = BackupConfiguration.get_config()
        _restore_sql_into_database(sql_content, preserve_config=curr_conf.preserve_config_on_restore)

        logger.info("DatabaseRestore - Info - Successfully restored database from backup archive.")
        return JsonResponse({
            'status': 'success',
            'message': 'Database backup restored and calibrated successfully.'
        })

    except Exception as e:
        logger.error(f"DatabaseRestore - Error - Failed to restore database from backup file: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@user_passes_test(lambda u: u.is_staff)
@csrf_exempt
@require_http_methods(["POST"])
def save_backup_config_api(request: HttpRequest) -> JsonResponse:
    """Save automated GFS backup schedule and storage target configuration."""
    try:
        data = json.loads(request.body)
        config = BackupConfiguration.get_config()

        config.is_enabled = bool(data.get('is_enabled', False))
        config.backup_time = data.get('backup_time', '02:00').strip()
        config.weekly_day = int(data.get('weekly_day', 6))
        config.monthly_day = int(data.get('monthly_day', 1))
        config.keep_daily = max(0, int(data.get('keep_daily', 7)))
        config.keep_weekly = max(0, int(data.get('keep_weekly', 4)))
        config.keep_monthly = max(0, int(data.get('keep_monthly', 3)))
        config.preserve_config_on_restore = bool(data.get('preserve_config_on_restore', True))

        config.storage_type = data.get('storage_type', 'LOCAL')
        config.local_path = data.get('local_path', '/backups').strip()

        config.s3_endpoint_url = data.get('s3_endpoint_url', '').strip() or None
        config.s3_bucket = data.get('s3_bucket', '').strip()
        config.s3_region = data.get('s3_region', 'us-east-1').strip()
        config.s3_access_key = data.get('s3_access_key', '').strip()
        config.s3_secret_key = data.get('s3_secret_key', '').strip()
        config.s3_prefix = data.get('s3_prefix', 'beveragelab/').strip()

        config.cifs_server = data.get('cifs_server', '').strip()
        config.cifs_share = data.get('cifs_share', '').strip()
        config.cifs_subpath = data.get('cifs_subpath', '').strip()
        config.cifs_username = data.get('cifs_username', '').strip()
        config.cifs_password = data.get('cifs_password', '').strip()
        config.cifs_domain = data.get('cifs_domain', '').strip()

        config.nfs_server = data.get('nfs_server', '').strip()
        config.nfs_export = data.get('nfs_export', '').strip()
        config.nfs_subpath = data.get('nfs_subpath', '').strip()

        config.encryption_passphrase = data.get('encryption_passphrase', '').strip()
        config.webhook_url = data.get('webhook_url', '').strip()

        config.save()
        logger.info("BackupConfig - Info - Successfully updated automated backup configuration.")
        return JsonResponse({'status': 'success', 'message': 'Backup configuration saved successfully.'})
    except Exception as e:
        logger.error(f"BackupConfig - Error - Failed to save backup configuration: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@user_passes_test(lambda u: u.is_staff)
@csrf_exempt
@require_http_methods(["POST"])
def test_backup_storage_api(request: HttpRequest) -> JsonResponse:
    """Test read/write connection to the active or requested storage target."""
    try:
        from ..backup_service import get_storage_driver
        data = json.loads(request.body) if request.body else {}
        config = BackupConfiguration.get_config()

        # Allow testing unsaved form values
        if data.get('storage_type'):
            config.storage_type = data.get('storage_type')
        if data.get('local_path'):
            config.local_path = data.get('local_path')
        if 's3_bucket' in data:
            config.s3_bucket = data.get('s3_bucket')
            config.s3_endpoint_url = data.get('s3_endpoint_url') or None
            config.s3_region = data.get('s3_region') or 'us-east-1'
            config.s3_access_key = data.get('s3_access_key')
            config.s3_secret_key = data.get('s3_secret_key')
            config.s3_prefix = data.get('s3_prefix')
        if 'cifs_server' in data:
            config.cifs_server = data.get('cifs_server')
            config.cifs_share = data.get('cifs_share')
            config.cifs_subpath = data.get('cifs_subpath')
            config.cifs_username = data.get('cifs_username')
            config.cifs_password = data.get('cifs_password')
            config.cifs_domain = data.get('cifs_domain')
        if 'nfs_server' in data:
            config.nfs_server = data.get('nfs_server')
            config.nfs_export = data.get('nfs_export')
            config.nfs_subpath = data.get('nfs_subpath')

        driver = get_storage_driver(config)
        success, message = driver.test_connection()
        return JsonResponse({'status': 'success' if success else 'failed', 'message': message})
    except Exception as e:
        logger.error(f"BackupStorage - Error - Test connection failed: {e}")
        return JsonResponse({'status': 'failed', 'message': str(e)})


def _run_backup_now_task(update_progress, tier='MANUAL'):
    """Background task function to execute backup and update progress."""
    from ..backup_service import execute_backup
    execute_backup(tier=tier, progress_callback=update_progress)


@user_passes_test(lambda u: u.is_staff)
@csrf_exempt
@require_http_methods(["POST"])
def run_backup_now_api(request: HttpRequest) -> JsonResponse:
    """Dispatches an asynchronous backup task, returning task_id for progress polling."""
    try:
        task = submit_task("Database Backup Snapshot", _run_backup_now_task, tier='MANUAL')
        return JsonResponse({
            'status': 'accepted',
            'task_id': str(task.uuid),
            'message': 'Backup protocol initiated.'
        }, status=202)
    except Exception as e:
        logger.error(f"BackupNow - Error - Failed to dispatch backup task: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@user_passes_test(lambda u: u.is_staff)
def download_backup_file(request: HttpRequest, uuid: Any) -> HttpResponse:
    """Stream a backup file directly from its storage driver."""
    try:
        record = BackupRecord.objects.get(uuid=uuid)
        config = BackupConfiguration.get_config()
        # Temporarily use record's storage type
        original_type = config.storage_type
        config.storage_type = record.storage_type
        from ..backup_service import get_storage_driver
        driver = get_storage_driver(config)
        config.storage_type = original_type

        file_bytes = driver.retrieve_file(record.filename)
        content_type = 'application/octet-stream' if record.is_encrypted else 'application/gzip'
        response = HttpResponse(file_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{record.filename}"'
        return response
    except BackupRecord.DoesNotExist:
        return HttpResponse("Backup not found", status=404)
    except Exception as e:
        logger.error(f"BackupDownload - Error - Failed to download backup {uuid}: {e}")
        return HttpResponse(f"Download failed: {str(e)}", status=500)


@user_passes_test(lambda u: u.is_staff)
@csrf_exempt
@require_http_methods(["POST"])
def restore_backup_record_api(request: HttpRequest, uuid: Any) -> JsonResponse:
    """Restore the database from an existing BackupRecord in storage."""
    try:
        record = BackupRecord.objects.get(uuid=uuid)
        config = BackupConfiguration.get_config()

        data = json.loads(request.body) if request.body else {}
        passphrase = data.get('passphrase', '').strip() or config.encryption_passphrase

        original_type = config.storage_type
        config.storage_type = record.storage_type
        from ..backup_service import get_storage_driver, decrypt_payload
        driver = get_storage_driver(config)
        config.storage_type = original_type

        raw_bytes = driver.retrieve_file(record.filename)
        if record.is_encrypted or raw_bytes.startswith(b"BLABENC1"):
            raw_bytes = decrypt_payload(raw_bytes, passphrase)

        sql_content = _extract_and_validate_sql_payload(raw_bytes)
        _restore_sql_into_database(sql_content, preserve_config=config.preserve_config_on_restore)

        logger.info(f"BackupRestore - Info - Successfully restored from snapshot {record.filename}")
        return JsonResponse({
            'status': 'success',
            'message': f"Database successfully restored from snapshot '{record.filename}'."
        })
    except BackupRecord.DoesNotExist:
        return JsonResponse({'error': 'Backup record not found.'}, status=404)
    except Exception as e:
        logger.error(f"BackupRestore - Error - Failed to restore snapshot {uuid}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@user_passes_test(lambda u: u.is_staff)
@csrf_exempt
@require_http_methods(["POST"])
def delete_backup_record_api(request: HttpRequest, uuid: Any) -> JsonResponse:
    """Delete a backup from storage and delete its catalog record."""
    try:
        record = BackupRecord.objects.get(uuid=uuid)
        config = BackupConfiguration.get_config()
        original_type = config.storage_type
        config.storage_type = record.storage_type
        from ..backup_service import get_storage_driver
        driver = get_storage_driver(config)
        config.storage_type = original_type

        driver.delete_file(record.filename)
        record.delete()
        logger.info(f"BackupDelete - Info - Deleted snapshot {record.filename}")
        return JsonResponse({'status': 'success', 'message': 'Snapshot deleted successfully.'})
    except BackupRecord.DoesNotExist:
        return JsonResponse({'error': 'Backup record not found.'}, status=404)
    except Exception as e:
        logger.error(f"BackupDelete - Error - Failed to delete snapshot {uuid}: {e}")
        return JsonResponse({'error': str(e)}, status=500)
