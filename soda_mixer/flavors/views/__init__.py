"""Views package for BeverageLab flavors app.

Exposes modular views to URLs.
"""

from .main import dashboard, ingredient_list, ingredient_detail, recipe_list, recipe_detail, mix_history_list
from .lab import lab_dispatcher, lab_view, synopsis_view
from .ingredients import (
    add_ingredient, edit_ingredient, delete_ingredient, delete_category,
    toggle_inventory_api, create_category_api, delete_recipe_category_api, delete_ingredient_profile_api
)
from .recipes import (
    create_recipe, edit_recipe, delete_recipe, add_recipe_api, rate_recipe_api,
    update_recipe_categories_api, save_mix_to_history_api, promote_mix_to_recipe_api,
    delete_history_api, export_recipe_to_mealie_api
)
from .ai import (
    get_recommendations_api, generate_name_api, get_category_suggestions_api,
    ai_chat_api, save_llm_provider_api, delete_llm_provider_api,
    fetch_provider_models_api, discover_provider_models_api, ai_suggest_api,
    ai_synthesize_api, ai_analyze_ingredient_api, ai_bulk_analyze_api, random_pairing_api,
    ai_quick_recommendations_api, ai_vibe_creation_api
)
from .auth import login_view, login_api, logout_api
from .settings import settings_view, save_settings_api, export_data, import_data
from .coffee_chemistry import coffee_chemistry_api
from .soda_chemistry import soda_chemistry_api
from .cryo_chemistry import cryo_chemistry_api
from .tasks import task_status_api

__all__ = [
    'dashboard', 'lab_dispatcher', 'lab_view', 'synopsis_view', 'ingredient_list', 'ingredient_detail', 'recipe_list', 'recipe_detail', 'mix_history_list',
    'add_ingredient', 'edit_ingredient', 'delete_ingredient', 'delete_category',
    'toggle_inventory_api', 'create_category_api', 'delete_recipe_category_api', 'delete_ingredient_profile_api',
    'create_recipe', 'edit_recipe', 'delete_recipe', 'add_recipe_api', 'rate_recipe_api',
    'update_recipe_categories_api', 'save_mix_to_history_api', 'promote_mix_to_recipe_api',
    'delete_history_api', 'export_recipe_to_mealie_api',
    'get_recommendations_api', 'generate_name_api', 'get_category_suggestions_api',
    'ai_chat_api', 'save_llm_provider_api', 'delete_llm_provider_api',
    'fetch_provider_models_api', 'discover_provider_models_api', 'ai_suggest_api',
    'ai_synthesize_api', 'ai_analyze_ingredient_api', 'ai_bulk_analyze_api', 'random_pairing_api',
    'ai_quick_recommendations_api', 'ai_vibe_creation_api',
    'coffee_chemistry_api',
    'soda_chemistry_api',
    'cryo_chemistry_api',
    'login_view', 'login_api', 'logout_api',
    'settings_view', 'save_settings_api', 'export_data', 'import_data',
    'task_status_api'
]

