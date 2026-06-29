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
