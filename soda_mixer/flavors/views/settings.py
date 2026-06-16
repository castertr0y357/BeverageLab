"""Settings and data management views."""

import json
import logging
from typing import Dict, Any

from django.shortcuts import render
from django.core import serializers
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse, JsonResponse

from ..models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, SystemConfiguration, LLMProvider, MixHistory, MixHistoryIngredient

logger = logging.getLogger(__name__)


def settings_view(request: HttpRequest) -> HttpResponse:
    """Settings page for backups and system management."""
    config = SystemConfiguration.get_config()
    providers = LLMProvider.objects.all().order_by('name')
    return render(request, 'flavors/settings.html', {
        'config': config,
        'providers': providers,
        'provider_types': LLMProvider.PROVIDER_CHOICES
    })


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


def export_data(request: HttpRequest) -> HttpResponse:
    """Export all laboratory data to a JSON dossier."""
    try:
        data = {
            'ingredients': serializers.serialize('json', Ingredient.objects.all()),
            'categories': serializers.serialize('json', RecipeCategory.objects.all()),
            'recipes': serializers.serialize('json', Recipe.objects.all()),
            'recipe_ingredients': serializers.serialize('json', RecipeIngredient.objects.all()),
            'mix_history': serializers.serialize('json', MixHistory.objects.all()),
            'mix_history_ingredients': serializers.serialize('json', MixHistoryIngredient.objects.all()),
        }
        
        response = HttpResponse(json.dumps(data), content_type='application/json')
        filename = f"beveragelab_dossier_{timezone.now().strftime('%Y%m%d_%H%M')}.json"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        logger.info(f"DatabaseBackup - Info - Successfully generated laboratory data dossier: {filename}")
        return response
    except Exception as e:
        logger.error(f"DatabaseBackup - Error - Failed to export data dossier: {e}")
        return HttpResponse(f"Backup Export Failed: {str(e)}", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def import_data(request: HttpRequest) -> JsonResponse:
    """Restore laboratory data from a JSON dossier (Merge by Name)."""
    if 'backup_file' not in request.FILES:
        logger.warning("DatabaseRestore - Warning - Import requested but no file was provided.")
        return JsonResponse({'error': 'No file provided'}, status=400)

    try:
        raw_data = json.load(request.FILES['backup_file'])
        
        # 1. Restore Ingredients (Merge by Name)
        ingredient_map: Dict[int, Ingredient] = {} # old_id -> new_object
        for i_data in serializers.deserialize('json', raw_data['ingredients']):
            i = i_data.object
            old_id = i.id
            existing = Ingredient.objects.filter(name=i.name, brand=getattr(i, 'brand', '')).first()
            if existing:
                ingredient_map[old_id] = existing
            else:
                i.id = None # Force new record
                i.save()
                ingredient_map[old_id] = i

        # 2. Restore Categories (Merge by Name)
        category_map: Dict[int, RecipeCategory] = {}
        for c_data in serializers.deserialize('json', raw_data['categories']):
            c = c_data.object
            old_id = c.id
            existing = RecipeCategory.objects.filter(name=c.name).first()
            if existing:
                category_map[old_id] = existing
            else:
                c.id = None
                c.save()
                category_map[old_id] = c

        # 3. Restore Recipes
        recipe_map: Dict[int, Recipe] = {}
        for r_data in serializers.deserialize('json', raw_data['recipes']):
            r = r_data.object
            old_id = r.id
            r.id = None
            r.save()
            recipe_map[old_id] = r

        # 4. Restore Recipe Ingredients
        for ri_data in serializers.deserialize('json', raw_data['recipe_ingredients']):
            ri = ri_data.object
            if ri.recipe_id in recipe_map and ri.ingredient_id in ingredient_map:
                ri.id = None
                ri.recipe = recipe_map[ri.recipe_id]
                ri.ingredient = ingredient_map[ri.ingredient_id]
                ri.save()

        # 5. Restore Mix History
        mix_map: Dict[int, MixHistory] = {}
        for m_data in serializers.deserialize('json', raw_data['mix_history']):
            m = m_data.object
            old_id = m.id
            m.id = None
            if m.promoted_recipe_id and m.promoted_recipe_id in recipe_map:
                m.promoted_recipe = recipe_map[m.promoted_recipe_id]
            m.save()
            mix_map[old_id] = m

        # 6. Restore Mix History Ingredients
        for mhi_data in serializers.deserialize('json', raw_data['mix_history_ingredients']):
            mhi = mhi_data.object
            if mhi.mix_id in mix_map and mhi.ingredient_id in ingredient_map:
                mhi.id = None
                mhi.mix = mix_map[mhi.mix_id]
                mhi.ingredient = ingredient_map[mhi.ingredient_id]
                mhi.save()

        logger.info("DatabaseRestore - Info - Successfully integrated laboratory data dossier.")
        return JsonResponse({'status': 'success', 'message': 'Laboratory dossier integrated successfully'})

    except Exception as e:
        logger.error(f"DatabaseRestore - Error - Failed to restore database from backup file: {e}")
        return JsonResponse({'error': str(e)}, status=500)
