#!/usr/bin/env python
"""Database Backup and Restore utility for BeverageLab using Docker Compose."""

import os
import sys
import subprocess
import gzip
from datetime import datetime

# Default configuration from env
DB_NAME = os.environ.get('POSTGRES_DB', 'soda_mixer')
DB_USER = os.environ.get('POSTGRES_USER', 'postgres')
BACKUP_DIR = 'backups'


def load_env_file():
    """Manually parse .env file to load env vars for local run."""
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    try:
                        k, v = stripped.split('=', 1)
                        # Remove quotes if present
                        v = v.strip('"').strip("'")
                        os.environ.setdefault(k.strip(), v.strip())
                    except ValueError:
                        pass


def backup():
    """Execute pg_dump against the database container and save a compressed backup."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"Created backup directory: {BACKUP_DIR}")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.sql.gz")

    print(f"[STARTUP] Starting database backup protocol for '{DB_NAME}'...")

    # We use docker compose exec to run pg_dump inside the db container
    # -T disables pseudo-TTY allocation to prevent stdout formatting issues
    command = ['docker', 'compose', 'exec', '-T', 'db', 'pg_dump', '-U', DB_USER, DB_NAME]

    try:
        # Run command and capture output
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"[ERROR] Backup failed: {stderr.decode('utf-8').strip()}")
            return False

        # Compress and save
        with gzip.open(backup_file, 'wb') as f:
            f.write(stdout)

        print(f"[SUCCESS] Backup successfully created: {backup_file}")
        return True
    except Exception as e:
        print(f"[ERROR] Backup execution failed: {e}")
        return False


def restore(backup_path: str):
    """Restore the database from a compressed backup file."""
    if not os.path.exists(backup_path):
        print(f"[ERROR] Backup file not found: {backup_path}")
        return False

    print(f"[STARTUP] Initiating restore protocol from '{backup_path}'...")

    # Decompress backup file
    try:
        with gzip.open(backup_path, 'rb') as f:
            sql_content = f.read()
    except Exception as e:
        print(f"[ERROR] Failed to decompress backup: {e}")
        return False

    # Clean the current database schema first (drop and recreate public schema)
    clean_command = [
        'docker', 'compose', 'exec', '-T', 'db', 'psql', 
        '-U', DB_USER, '-d', DB_NAME, 
        '-c', 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
    ]
    
    try:
        print("[CLEANUP] Cleaning database schemas...")
        clean_proc = subprocess.run(clean_command, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Database cleanup failed: {e.stderr.decode('utf-8').strip()}")
        return False

    # Run psql restore command
    restore_command = ['docker', 'compose', 'exec', '-T', 'db', 'psql', '-U', DB_USER, '-d', DB_NAME]

    try:
        restore_proc = subprocess.Popen(restore_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = restore_proc.communicate(input=sql_content)

        if restore_proc.returncode != 0:
            print(f"[ERROR] Restore failed: {stderr.decode('utf-8').strip()}")
            return False

        print("[SUCCESS] Database successfully restored and calibrated.")
        return True
    except Exception as e:
        print(f"[ERROR] Restore execution failed: {e}")
        return False


def main():
    load_env_file()
    
    # Reload parameters from env after loading file
    global DB_NAME, DB_USER
    DB_NAME = os.environ.get('POSTGRES_DB', DB_NAME)
    DB_USER = os.environ.get('POSTGRES_USER', DB_USER)

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python backup.py --backup              (Create compressed database backup)")
        print("  python backup.py --restore [path]      (Restore database from a compressed backup file)")
        sys.exit(1)

    action = sys.argv[1]
    if action == '--backup':
        success = backup()
    elif action == '--restore':
        if len(sys.argv) < 3:
            print("[ERROR] Error: Please specify the path of the backup file to restore.")
            sys.exit(1)
        success = restore(sys.argv[2])
    else:
        print(f"[ERROR] Error: Unknown argument '{action}'")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
