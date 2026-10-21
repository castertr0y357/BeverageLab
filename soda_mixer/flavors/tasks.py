import threading
import time
import logging

logger = logging.getLogger(__name__)

def keep_warm_loop():
    logger.info("Keep-Warm - Started LLM Keep-Warm background thread.")
    while True:
        try:
            # Lazy import to avoid circular imports during app loading
            from .models import LLMProvider
            from .ai_service import AIAssistant
            
            # Find all enabled providers with keep_warm enabled
            providers = LLMProvider.objects.filter(is_enabled=True, enable_keep_warm=True)
            for provider in providers:
                logger.info(f"Keep-Warm - Triggering pulse for provider '{provider.name}'")
                success = AIAssistant.keep_warm_provider(provider)
                if success:
                    logger.info(f"Keep-Warm - Pulse succeeded for provider '{provider.name}'")
                else:
                    logger.warning(f"Keep-Warm - Pulse failed or skipped for provider '{provider.name}'")
        except Exception as e:
            logger.error(f"Keep-Warm background task error: {e}", exc_info=True)
            
        # Sleep for 5 minutes (300 seconds)
        time.sleep(300)

def start_keep_warm_task():
    thread = threading.Thread(target=keep_warm_loop, daemon=True, name="LLMKeepWarmThread")
    thread.start()
    logger.info("Keep-Warm - Dispatched LLM Keep-Warm daemon thread.")


def backup_scheduler_loop():
    """Periodic daemon loop checking every 60s if a scheduled GFS backup is due."""
    logger.info("BackupScheduler - Started automated GFS backup daemon thread.")
    while True:
        try:
            from django.db import connection
            from django.utils import timezone
            from .models import BackupConfiguration
            from .backup_service import determine_gfs_tier, execute_backup

            # Check configuration
            config = BackupConfiguration.get_config()
            if config.is_enabled:
                now = timezone.now()
                target_hour, target_min = map(int, config.backup_time.split(':'))
                is_due_time = (now.hour > target_hour) or (now.hour == target_hour and now.minute >= target_min)
                not_run_today = (config.last_run_at is None) or (config.last_run_at.date() < now.date())

                if is_due_time and not_run_today:
                    # Acquire advisory lock to prevent multiple Gunicorn workers from running duplicate backups
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_try_advisory_lock(987654321);")
                        locked = cursor.fetchone()[0]

                    if locked:
                        try:
                            # Re-verify not_run_today after acquiring lock
                            config.refresh_from_db()
                            if (config.last_run_at is None) or (config.last_run_at.date() < now.date()):
                                tier = determine_gfs_tier(now, config)
                                logger.info(f"BackupScheduler - Executing scheduled {tier} database backup...")
                                execute_backup(tier=tier, config=config)
                                logger.info(f"BackupScheduler - Scheduled {tier} database backup succeeded.")
                        finally:
                            with connection.cursor() as cursor:
                                cursor.execute("SELECT pg_advisory_unlock(987654321);")
        except Exception as e:
            logger.error(f"BackupScheduler - Error in scheduler loop: {e}", exc_info=True)

        # Sleep for 60 seconds
        time.sleep(60)


def start_backup_scheduler_task():
    thread = threading.Thread(target=backup_scheduler_loop, daemon=True, name="BackupSchedulerThread")
    thread.start()
    logger.info("BackupScheduler - Dispatched automated GFS backup daemon thread.")
