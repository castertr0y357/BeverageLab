"""URL configuration for Soda Mixer flavors app."""

from django.urls import path
from . import views

urlpatterns = [
    # Main pages
    path('', views.dashboard, name='dashboard'),

    # Lab Environments
    path('lab/synopsis/', views.synopsis_view, name='synopsis_view'),
    path('lab/<str:lab_type>/', views.lab_dispatcher, name='lab_dispatcher'),
    path('lab/<str:lab_type>/<str:mode>/', views.lab_view, name='lab_view'),

    # Ingredient and Category management
    path('ingredients/', views.ingredient_list, name='ingredient_list'),
    path('ingredients/add/', views.add_ingredient, name='add_ingredient'),
    path('ingredients/<uuid:uuid>/', views.ingredient_detail, name='ingredient_detail'),
    path('ingredients/<uuid:uuid>/edit/', views.edit_ingredient, name='edit_ingredient'),
    path('ingredients/<uuid:uuid>/delete/', views.delete_ingredient, name='delete_ingredient'),
    path('categories/<uuid:uuid>/delete/', views.delete_category, name='delete_category'),

    # Recipe management
    path('recipes/', views.recipe_list, name='recipe_list'),
    path('recipes/create/', views.create_recipe, name='create_recipe'),
    path('recipes/<uuid:uuid>/', views.recipe_detail, name='recipe_detail'),
    path('recipes/<uuid:uuid>/edit/', views.edit_recipe, name='edit_recipe'),
    path('recipes/<uuid:uuid>/delete/', views.delete_recipe, name='delete_recipe'),

    # Mix History
    path('history/', views.mix_history_list, name='mix_history_list'),

    # API endpoints
    path('api/recommendations/', views.get_recommendations_api, name='get_recommendations_api'),
    path('api/recipes/', views.add_recipe_api, name='add_recipe_api'),
    path('api/ingredients/<uuid:uuid>/toggle_inventory/', views.toggle_inventory_api, name='toggle_inventory_api'),
    path('api/recipes/<uuid:uuid>/rate/', views.rate_recipe_api, name='rate_recipe_api'),
    path('api/recipes/<uuid:uuid>/categories/', views.update_recipe_categories_api, name='update_recipe_categories_api'),
    path('api/history/save/', views.save_mix_to_history_api, name='save_mix_to_history_api'),
    path('api/history/<uuid:uuid>/promote/', views.promote_mix_to_recipe_api, name='promote_mix_to_recipe_api'),
    path('api/generate-name/', views.generate_name_api, name='generate_name_api'),
    path('api/history/<uuid:uuid>/delete/', views.delete_history_api, name='delete_history_api'),
    path('api/category-suggestions/', views.get_category_suggestions_api, name='get_category_suggestions_api'),
    path('api/categories/create/', views.create_category_api, name='create_category_api'),
    path('api/categories/<uuid:uuid>/delete/', views.delete_recipe_category_api, name='delete_recipe_category_api'),
    path('api/ingredient-profiles/delete/', views.delete_ingredient_profile_api, name='delete_ingredient_profile_api'),
    path('api/recipes/<uuid:uuid>/export/', views.export_recipe_to_mealie_api, name='export_recipe_to_mealie_api'),
    path('api/tasks/<uuid:uuid>/', views.task_status_api, name='task_status_api'),

    # AI Assistant endpoints
    path('api/ai/chat/', views.ai_chat_api, name='ai_chat_api'),
    path('api/ai/quick-recommendations/', views.ai_quick_recommendations_api, name='ai_quick_recommendations_api'),
    path('api/ai/vibe-creation/', views.ai_vibe_creation_api, name='ai_vibe_creation_api'),
    path('api/ai/provider/save/', views.save_llm_provider_api, name='save_llm_provider_api'),
    path('api/ai/provider/<int:pk>/delete/', views.delete_llm_provider_api, name='delete_llm_provider_api'),
    path('api/ai/provider/<int:pk>/models/', views.fetch_provider_models_api, name='fetch_provider_models_api'),
    path('api/ai/provider/discover/', views.discover_provider_models_api, name='discover_provider_models_api'),
    path('api/ai/suggest/', views.ai_suggest_api, name='ai_suggest_api'),
    path('api/ai/synthesize/', views.ai_synthesize_api, name='ai_synthesize_api'),
    path('api/ai/analyze-ingredient/', views.ai_analyze_ingredient_api, name='ai_analyze_ingredient_api'),
    path('api/ai/bulk-analyze/', views.ai_bulk_analyze_api, name='ai_bulk_analyze_api'),
    path('api/random-pairing/', views.random_pairing_api, name='random_pairing_api'),
    path('api/coffee/chemistry/', views.coffee_chemistry_api, name='coffee_chemistry_api'),
    path('api/soda/chemistry/', views.soda_chemistry_api, name='soda_chemistry_api'),
    path('api/cryo/chemistry/', views.cryo_chemistry_api, name='cryo_chemistry_api'),
    
    # Auth
    path('login/', views.login_view, name='login'),
    path('api/auth/login/', views.login_api, name='login_api'),
    path('api/auth/logout/', views.logout_api, name='logout_api'),

    # Settings and Data management
    path('settings/', views.settings_view, name='settings'),
    path('settings/save/', views.save_settings_api, name='save_settings_api'),
    path('settings/export/', views.export_data, name='export_data'),
    path('settings/import/', views.import_data, name='import_data'),
]