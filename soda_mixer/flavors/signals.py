import logging
import threading
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Ingredient

logger = logging.getLogger(__name__)

@receiver([post_save, post_delete], sender=Ingredient)
def trigger_cache_preheat_on_ingredient_change(sender, instance, **kwargs):
    """
    Automatically trigger a suggestions cache preheat request in a background thread
    when any ingredient is modified, ensuring prompt caching stays warm with the latest registry state.
    """
    import sys
    # Skip preheating during database migrations to prevent lock conflicts
    if any(cmd in sys.argv for cmd in ['migrate', 'makemigrations', 'showmigrations', 'sqlmigrate']):
        return

    # Import inside to avoid circular imports during startup
    from .ai_service import AIAssistant
    
    logger.info(f"AIKeepWarm - Info - Database modification detected on ingredient '{instance.name}'. Triggering suggestions cache preheat.")
    
    if 'test' in sys.argv:
        # Run synchronously during tests to prevent background thread database connection leaks
        AIAssistant.preheat_suggestions_cache()
        return

    def run_preheat():
        AIAssistant.preheat_suggestions_cache()
        
    threading.Thread(target=run_preheat, daemon=True, name="LLMPreheatThread").start()
