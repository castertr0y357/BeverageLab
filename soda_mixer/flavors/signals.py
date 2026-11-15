import logging
import sys
import threading
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .models import Ingredient

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Ingredient)
def capture_ingredient_previous_state(sender, instance, **kwargs):
    """Capture previous category and inventory state before saving an Ingredient."""
    if any(cmd in sys.argv for cmd in ['migrate', 'makemigrations', 'showmigrations', 'sqlmigrate']):
        return
    if instance.pk:
        prev = Ingredient.all_objects.filter(pk=instance.pk).values('category', 'is_in_inventory').first()
        if prev:
            instance._prev_category = prev['category']
            instance._prev_in_inventory = prev['is_in_inventory']
            return
    instance._prev_category = None
    instance._prev_in_inventory = None


@receiver(post_save, sender=Ingredient)
def invalidate_quick_cache_on_ingredient_save(sender, instance, created, **kwargs):
    """
    Invalidate affected CachedQuickDrink entries when an Ingredient changes category
    or is newly added/restocked into inventory.
    """
    if any(cmd in sys.argv for cmd in ['migrate', 'makemigrations', 'showmigrations', 'sqlmigrate']):
        return

    from .quick_cache_service import invalidate_quick_cache_for_ingredient_change

    old_category = getattr(instance, '_prev_category', None)
    prev_in_inventory = getattr(instance, '_prev_in_inventory', None)
    is_new_or_restocked = bool(
        instance.is_in_inventory and (created or prev_in_inventory is False)
    )

    invalidate_quick_cache_for_ingredient_change(
        ingredient_id=instance.id,
        old_category=old_category,
        new_category=instance.category,
        is_new_or_restocked=is_new_or_restocked,
    )


@receiver([post_save, post_delete], sender=Ingredient)
def trigger_cache_preheat_on_ingredient_change(sender, instance, **kwargs):
    """
    Automatically trigger a suggestions cache preheat request in a background thread
    when any ingredient is modified, ensuring prompt caching stays warm with the latest registry state.
    """
    # Skip preheating during database migrations to prevent lock conflicts
    if any(cmd in sys.argv for cmd in ['migrate', 'makemigrations', 'showmigrations', 'sqlmigrate']):
        return

    # Import inside to avoid circular imports during startup
    from .ai_service import AIAssistant
    
    logger.info(f"AIKeepWarm - Info - Database modification detected on ingredient '{instance.name}'. Triggering suggestions cache preheat.")
    
    if 'test' in sys.argv:
        # Skip preheating during tests to avoid slow network/LLM calls, except when verifying the signal connection
        if 'Mock' in type(AIAssistant.preheat_suggestions_cache).__name__:
            AIAssistant.preheat_suggestions_cache()
        return

    def run_preheat():
        AIAssistant.preheat_suggestions_cache()
        
    threading.Thread(target=run_preheat, daemon=True, name="LLMPreheatThread").start()
