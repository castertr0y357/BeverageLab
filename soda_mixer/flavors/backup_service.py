"""Backup engine services: encryption, storage drivers, GFS rotation, and webhook alerts."""

import ctypes
import ctypes.util
import gzip
import ipaddress
import json
import logging
import os
import subprocess
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

import requests
from django.conf import settings
from django.utils import timezone as dj_timezone

from .models import BackupConfiguration, BackupRecord

logger = logging.getLogger(__name__)

ENCRYPTION_MAGIC = b"BLABENC1"


# ---------------------------------------------------------------------------
# 1. AES-256-GCM Encryption / Decryption Layer
# ---------------------------------------------------------------------------

def encrypt_payload(data: bytes, passphrase: str) -> bytes:
    """Encrypt payload using AES-256-GCM with PBKDF2-HMAC-SHA256 key derivation."""
    if not passphrase:
        return data

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    )
    key = kdf.derive(passphrase.encode('utf-8'))
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)

    # Format: MAGIC (8 bytes) + salt (16 bytes) + nonce (12 bytes) + ciphertext (includes 16-byte tag)
    return ENCRYPTION_MAGIC + salt + nonce + ciphertext


def decrypt_payload(data: bytes, passphrase: str) -> bytes:
    """Decrypt an AES-256-GCM encrypted payload, or return as-is if unencrypted."""
    if not data.startswith(ENCRYPTION_MAGIC):
        return data

    if not passphrase:
        raise ValueError("Backup payload is encrypted but no decryption passphrase was provided.")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    magic_len = len(ENCRYPTION_MAGIC)
    salt = data[magic_len:magic_len + 16]
    nonce = data[magic_len + 16:magic_len + 28]
    ciphertext = data[magic_len + 28:]

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    )
    key = kdf.derive(passphrase.encode('utf-8'))
    aesgcm = AESGCM(key)

    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError("Failed to decrypt backup. Invalid decryption passphrase or corrupted archive.") from exc


# ---------------------------------------------------------------------------
# 2. Storage Drivers: Local, S3, CIFS/SMB, Direct Userspace NFS
# ---------------------------------------------------------------------------

class BaseStorageDriver:
    """Abstract interface for backup storage drivers."""
    def test_connection(self) -> Tuple[bool, str]:
        raise NotImplementedError

    def store_file(self, filename: str, data: bytes) -> None:
        raise NotImplementedError

    def retrieve_file(self, filename: str) -> bytes:
        raise NotImplementedError

    def delete_file(self, filename: str) -> bool:
        raise NotImplementedError


class LocalStorageDriver(BaseStorageDriver):
    """Stores backups on a persistent local filesystem volume (e.g. /backups)."""
    def __init__(self, directory: str = "/backups"):
        self.directory = directory

    def _ensure_dir(self):
        if not os.path.exists(self.directory):
            os.makedirs(self.directory, mode=0o700, exist_ok=True)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            self._ensure_dir()
            test_file = os.path.join(self.directory, ".test_write.tmp")
            with open(test_file, 'wb') as f:
                f.write(b"test")
            os.remove(test_file)
            return True, f"Local directory '{self.directory}' is writable."
        except Exception as e:
            return False, f"Local storage error: {e}"

    def store_file(self, filename: str, data: bytes) -> None:
        self._ensure_dir()
        target = os.path.join(self.directory, filename)
        with open(target, 'wb') as f:
            f.write(data)
        os.chmod(target, 0o600)

    def retrieve_file(self, filename: str) -> bytes:
        target = os.path.join(self.directory, filename)
        if not os.path.exists(target):
            raise FileNotFoundError(f"Local backup '{filename}' not found.")
        with open(target, 'rb') as f:
            return f.read()

    def delete_file(self, filename: str) -> bool:
        target = os.path.join(self.directory, filename)
        if os.path.exists(target):
            os.remove(target)
            return True
        return False


class S3StorageDriver(BaseStorageDriver):
    """Stores backups on Amazon S3 or S3-compatible endpoints (MinIO, R2, B2)."""
    def __init__(self, config: BackupConfiguration):
        self.config = config
        self.is_mock = os.environ.get('MOCK_MODE', 'False').lower() in ('true', '1', 't')

    def _get_client(self):
        import boto3
        from botocore.config import Config
        return boto3.client(
            's3',
            endpoint_url=self.config.s3_endpoint_url or None,
            aws_access_key_id=self.config.s3_access_key or None,
            aws_secret_access_key=self.config.s3_secret_key or None,
            region_name=self.config.s3_region or 'us-east-1',
            config=Config(signature_version='s3v4')
        )

    def _get_key(self, filename: str) -> str:
        prefix = (self.config.s3_prefix or '').strip('/')
        return f"{prefix}/{filename}" if prefix else filename

    def test_connection(self) -> Tuple[bool, str]:
        if self.is_mock:
            return True, "Mock S3 connection verified."
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.config.s3_bucket)
            return True, f"Bucket '{self.config.s3_bucket}' reachable."
        except Exception as e:
            return False, f"S3 error: {e}"

    def store_file(self, filename: str, data: bytes) -> None:
        if self.is_mock:
            return
        client = self._get_client()
        key = self._get_key(filename)
        client.put_object(Bucket=self.config.s3_bucket, Key=key, Body=data)

    def retrieve_file(self, filename: str) -> bytes:
        if self.is_mock:
            return b"mock-s3-content"
        client = self._get_client()
        key = self._get_key(filename)
        resp = client.get_object(Bucket=self.config.s3_bucket, Key=key)
        return resp['Body'].read()

    def delete_file(self, filename: str) -> bool:
        if self.is_mock:
            return True
        try:
            client = self._get_client()
            key = self._get_key(filename)
            client.delete_object(Bucket=self.config.s3_bucket, Key=key)
            return True
        except Exception:
            return False


class CIFSStorageDriver(BaseStorageDriver):
    """Pure-Python CIFS/SMB storage driver via smbprotocol."""
    def __init__(self, config: BackupConfiguration):
        self.config = config
        self.is_mock = os.environ.get('MOCK_MODE', 'False').lower() in ('true', '1', 't')

    def _register_session(self):
        import smbclient
        smbclient.register_session(
            self.config.cifs_server,
            username=self.config.cifs_username,
            password=self.config.cifs_password,
            domain=self.config.cifs_domain or None,
        )

    def _get_path(self, filename: str = "") -> str:
        server = self.config.cifs_server.strip('\\/').replace('/', '\\')
        share = self.config.cifs_share.strip('\\/').replace('/', '\\')
        subpath = (self.config.cifs_subpath or '').strip('\\/').replace('/', '\\')
        base = f"\\\\{server}\\{share}"
        if subpath:
            base = f"{base}\\{subpath}"
        if filename:
            return f"{base}\\{filename}"
        return base

    def test_connection(self) -> Tuple[bool, str]:
        if self.is_mock:
            return True, "Mock SMB connection verified."
        try:
            import smbclient
            self._register_session()
            base_path = self._get_path()
            smbclient.makedirs(base_path, exist_ok=True)
            test_path = f"{base_path}\\.test_write.tmp"
            with smbclient.open_file(test_path, mode="wb") as f:
                f.write(b"test")
            smbclient.remove(test_path)
            return True, f"SMB share '{self.config.cifs_share}' verified."
        except Exception as e:
            return False, f"SMB error: {e}"

    def store_file(self, filename: str, data: bytes) -> None:
        if self.is_mock:
            return
        import smbclient
        self._register_session()
        base_path = self._get_path()
        smbclient.makedirs(base_path, exist_ok=True)
        target = self._get_path(filename)
        with smbclient.open_file(target, mode="wb") as f:
            f.write(data)

    def retrieve_file(self, filename: str) -> bytes:
        if self.is_mock:
            return b"mock-smb-content"
        import smbclient
        self._register_session()
        target = self._get_path(filename)
        with smbclient.open_file(target, mode="rb") as f:
            return f.read()

    def delete_file(self, filename: str) -> bool:
        if self.is_mock:
            return True
        try:
            import smbclient
            self._register_session()
            target = self._get_path(filename)
            smbclient.remove(target)
            return True
        except Exception:
            return False


class UserspaceNFSDriver(BaseStorageDriver):
    """Direct userspace NFS client interacting via libnfs.so without kernel mounts."""
    def __init__(self, config: BackupConfiguration):
        self.config = config
        self.is_mock = os.environ.get('MOCK_MODE', 'False').lower() in ('true', '1', 't')

    def _get_lib(self):
        try:
            return ctypes.CDLL("libnfs.so.14")
        except OSError:
            libname = ctypes.util.find_library("nfs") or "libnfs.so"
            return ctypes.CDLL(libname)

    def _open_context(self):
        lib = self._get_lib()
        lib.nfs_init_context.restype = ctypes.c_void_p
        ctx = lib.nfs_init_context()
        if not ctx:
            raise RuntimeError("Failed to initialize libnfs context.")

        server_b = self.config.nfs_server.encode('utf-8')
        export_b = self.config.nfs_export.encode('utf-8')

        ret = lib.nfs_mount(ctypes.c_void_p(ctx), server_b, export_b)
        if ret != 0:
            lib.nfs_get_error.restype = ctypes.c_char_p
            err = lib.nfs_get_error(ctypes.c_void_p(ctx)).decode('utf-8', errors='replace')
            lib.nfs_destroy_context(ctypes.c_void_p(ctx))
            raise RuntimeError(f"NFS mount failed: {err}")
        return lib, ctx

    def _get_rel_path(self, filename: str = "") -> str:
        sub = (self.config.nfs_subpath or '').strip('/')
        if sub and filename:
            return f"/{sub}/{filename}"
        elif sub:
            return f"/{sub}"
        elif filename:
            return f"/{filename}"
        return "/"

    def test_connection(self) -> Tuple[bool, str]:
        if self.is_mock:
            return True, "Mock NFS connection verified."
        try:
            lib, ctx = self._open_context()
            try:
                # Test opendir on export root
                rel = self._get_rel_path()
                lib.nfs_opendir.restype = ctypes.c_void_p
                dir_handle = lib.nfs_opendir(ctypes.c_void_p(ctx), rel.encode('utf-8'))
                if not dir_handle:
                    lib.nfs_get_error.restype = ctypes.c_char_p
                    err = lib.nfs_get_error(ctypes.c_void_p(ctx)).decode('utf-8', errors='replace')
                    return False, f"NFS opendir error: {err}"
                lib.nfs_closedir(ctypes.c_void_p(ctx), ctypes.c_void_p(dir_handle))
                return True, f"NFS export '{self.config.nfs_export}' reachable."
            finally:
                lib.nfs_destroy_context(ctypes.c_void_p(ctx))
        except Exception as e:
            return False, f"NFS connection error: {e}"

    def store_file(self, filename: str, data: bytes) -> None:
        if self.is_mock:
            return
        lib, ctx = self._open_context()
        try:
            rel = self._get_rel_path(filename)
            # O_WRONLY | O_CREAT | O_TRUNC = 0x0001 | 0x0040 | 0x0200 = 0x0241
            lib.nfs_open2.restype = ctypes.c_void_p
            fh = lib.nfs_open2(ctypes.c_void_p(ctx), rel.encode('utf-8'), 0x0241, 0o600)
            if not fh:
                lib.nfs_get_error.restype = ctypes.c_char_p
                err = lib.nfs_get_error(ctypes.c_void_p(ctx)).decode('utf-8', errors='replace')
                raise RuntimeError(f"NFS open for write failed: {err}")
            try:
                written = lib.nfs_write(ctypes.c_void_p(ctx), ctypes.c_void_p(fh), ctypes.c_char_p(data), len(data))
                if written < len(data):
                    raise RuntimeError("NFS write incomplete.")
            finally:
                lib.nfs_close(ctypes.c_void_p(ctx), ctypes.c_void_p(fh))
        finally:
            lib.nfs_destroy_context(ctypes.c_void_p(ctx))

    def retrieve_file(self, filename: str) -> bytes:
        if self.is_mock:
            return b"mock-nfs-content"
        lib, ctx = self._open_context()
        try:
            rel = self._get_rel_path(filename)
            lib.nfs_open2.restype = ctypes.c_void_p
            fh = lib.nfs_open2(ctypes.c_void_p(ctx), rel.encode('utf-8'), 0, 0)
            if not fh:
                lib.nfs_get_error.restype = ctypes.c_char_p
                err = lib.nfs_get_error(ctypes.c_void_p(ctx)).decode('utf-8', errors='replace')
                raise RuntimeError(f"NFS open for read failed: {err}")
            try:
                chunks = []
                buf_size = 1024 * 1024
                buf = ctypes.create_string_buffer(buf_size)
                while True:
                    read_bytes = lib.nfs_read(ctypes.c_void_p(ctx), ctypes.c_void_p(fh), buf_size, buf)
                    if read_bytes <= 0:
                        break
                    chunks.append(buf.raw[:read_bytes])
                return b"".join(chunks)
            finally:
                lib.nfs_close(ctypes.c_void_p(ctx), ctypes.c_void_p(fh))
        finally:
            lib.nfs_destroy_context(ctypes.c_void_p(ctx))

    def delete_file(self, filename: str) -> bool:
        if self.is_mock:
            return True
        try:
            lib, ctx = self._open_context()
            try:
                rel = self._get_rel_path(filename)
                ret = lib.nfs_unlink(ctypes.c_void_p(ctx), rel.encode('utf-8'))
                return ret == 0
            finally:
                lib.nfs_destroy_context(ctypes.c_void_p(ctx))
        except Exception:
            return False


def get_storage_driver(config: BackupConfiguration) -> BaseStorageDriver:
    """Factory selecting the storage driver for the active configuration."""
    if config.storage_type == 'S3':
        return S3StorageDriver(config)
    elif config.storage_type == 'CIFS':
        return CIFSStorageDriver(config)
    elif config.storage_type == 'NFS':
        return UserspaceNFSDriver(config)
    return LocalStorageDriver(config.local_path or "/backups")


# ---------------------------------------------------------------------------
# 3. GFS Rotation and Webhook Alerts
# ---------------------------------------------------------------------------

def determine_gfs_tier(dt: datetime, config: BackupConfiguration) -> str:
    """Classifies a backup run into Monthly, Weekly, or Daily tier."""
    if config.keep_monthly > 0 and dt.day == config.monthly_day:
        return 'MONTHLY'
    if config.keep_weekly > 0 and dt.weekday() == config.weekly_day:
        return 'WEEKLY'
    return 'DAILY'


def enforce_gfs_retention(config: BackupConfiguration) -> List[str]:
    """Deletes older backups exceeding the retention count for each tier."""
    driver = get_storage_driver(config)
    pruned_files = []

    limits = {
        'DAILY': config.keep_daily,
        'WEEKLY': config.keep_weekly,
        'MONTHLY': config.keep_monthly,
    }

    for tier, keep_count in limits.items():
        if keep_count <= 0:
            continue
        records = list(BackupRecord.objects.filter(tier=tier, status='SUCCESS').order_by('-created_at'))
        if len(records) > keep_count:
            excess = records[keep_count:]
            for rec in excess:
                try:
                    driver.delete_file(rec.filename)
                except Exception as del_err:
                    logger.warning(f"BackupEngine - Warning - Failed to delete storage file {rec.filename}: {del_err}")
                pruned_files.append(rec.filename)
                rec.delete()

    return pruned_files


def is_safe_webhook_url(url_str: str) -> bool:
    """Enforce SSRF defenses: Ensure webhook resolves to a valid public IP."""
    try:
        parsed = urllib.parse.urlparse(url_str)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            return False
        import socket
        ip_str = socket.gethostbyname(parsed.hostname)
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
        return True
    except Exception:
        return False


def dispatch_webhook_failure(webhook_url: str, error_msg: str, tier: str = "SCHEDULED") -> None:
    """Sends a failure notification payload to Discord, Slack, Gotify, or generic webhook."""
    if not webhook_url:
        return

    # Skip in tests or SSRF failure
    if not is_safe_webhook_url(webhook_url):
        logger.warning(f"BackupEngine - Warning - Blocked webhook dispatch to unsafe URL: {webhook_url}")
        return

    payload = {
        "content": f"🚨 **BeverageLab Backup Failure**: Scheduled `{tier}` backup failed: {error_msg}",
        "text": f"🚨 BeverageLab Backup Failure: {error_msg}",
        "title": "BeverageLab Backup Alert",
        "message": error_msg,
        "timestamp": dj_timezone.now().isoformat(),
    }
    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as exc:
        logger.error(f"BackupEngine - Error - Webhook notification failed: {exc}")


# ---------------------------------------------------------------------------
# 4. Backup Execution Orchestrator
# ---------------------------------------------------------------------------

def execute_backup(
    tier: str = 'MANUAL',
    config: Optional[BackupConfiguration] = None,
    progress_callback: Optional[Any] = None
) -> BackupRecord:
    """Executes pg_dump, compresses, optionally encrypts, and stores the backup snapshot."""
    if config is None:
        config = BackupConfiguration.get_config()

    def update_p(val, msg=""):
        if progress_callback:
            progress_callback(val, status='RUNNING', result_data={'message': msg} if msg else None)

    update_p(10, "Extracting database parameters...")
    from .views.settings import _get_db_env_and_params
    env, db_name, db_user, db_host, db_port = _get_db_env_and_params()

    timestamp = dj_timezone.now().strftime('%Y%m%d_%H%M%S')
    base_name = f"beveragelab_{tier.lower()}_{timestamp}.sql.gz"
    is_encrypted = bool(config.encryption_passphrase)
    filename = f"{base_name}.enc" if is_encrypted else base_name

    rec = BackupRecord(
        filename=filename,
        tier=tier,
        storage_type=config.storage_type,
        is_encrypted=is_encrypted,
        status='FAILED',
    )

    try:
        update_p(25, f"Running pg_dump against {db_name}...")
        cmd = [
            'pg_dump',
            '--no-owner',
            '--no-acl',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            db_name,
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        stdout, stderr = proc.communicate(timeout=180)

        if proc.returncode != 0:
            err = stderr.decode('utf-8', errors='replace').strip()
            raise RuntimeError(f"pg_dump failed: {err}")

        update_p(50, "Compressing SQL payload...")
        compressed_sql = gzip.compress(stdout)

        update_p(65, "Encrypting archive..." if is_encrypted else "Packaging archive...")
        final_payload = encrypt_payload(compressed_sql, config.encryption_passphrase) if is_encrypted else compressed_sql

        update_p(80, f"Uploading to {config.get_storage_type_display()}...")
        driver = get_storage_driver(config)
        driver.store_file(filename, final_payload)

        rec.file_size = len(final_payload)
        rec.status = 'SUCCESS'
        rec.save()

        # Update telemetry
        config.last_run_at = dj_timezone.now()
        config.last_status = 'SUCCESS'
        config.last_error = ''
        config.save()

        # Enforce GFS retention if scheduled
        if tier in ('DAILY', 'WEEKLY', 'MONTHLY'):
            update_p(90, "Enforcing GFS retention policy...")
            enforce_gfs_retention(config)

        update_p(100, "Backup protocol completed.")
        logger.info(f"BackupEngine - Info - Successfully created {tier} backup: {filename}")
        return rec

    except Exception as e:
        err_msg = str(e)
        logger.error(f"BackupEngine - Error - Backup failed: {err_msg}", exc_info=True)
        rec.error_message = err_msg
        rec.save()

        config.last_run_at = dj_timezone.now()
        config.last_status = 'FAILURE'
        config.last_error = err_msg
        config.save()

        if tier != 'MANUAL' and config.webhook_url:
            dispatch_webhook_failure(config.webhook_url, err_msg, tier=tier)

        raise

