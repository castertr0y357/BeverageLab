import json
import logging
import random
from typing import Dict, Any, List, Set, Union, Optional, Callable
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.db.models import Q
from ...models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, SystemConfiguration, LLMProvider, BackgroundExecutionTask
from ...tasks_registry import submit_task
from ...recommendations import (
    suggest_categories, calculate_recipe_stats
)
from ...ai_service import AIAssistant
from .helpers import *

def get_recommendations_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for tiered ingredient recommendations (Deprecated, now returns empty)."""
    try:
        serialized = {'recommended': [], 'recipes': []}
        return JsonResponse(serialized)
    except Exception as e:
        logger.warning(f"RecommendationsAPI - Warning - {e}")
        return JsonResponse({'error': str(e)}, status=400)

def get_category_suggestions_api(request: HttpRequest) -> JsonResponse:
    """Return suggested category names and all existing categories."""
    try:
        data = json.loads(request.body)
        ingredient_ids = data.get('ingredient_ids', [])
        ingredient_ids = [0 if i == 'virtual_water' else int(i) for i in ingredient_ids if str(i).isdigit() or i == 'virtual_water']
        suggested_names = suggest_categories(ingredient_ids)
        existing = list(RecipeCategory.objects.all().values('id', 'name', 'color'))
        return JsonResponse({'suggested': suggested_names, 'existing': existing})
    except json.JSONDecodeError as e:
        logger.warning(f"CategorySuggestionsAPI - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

def random_pairing_api(request: HttpRequest) -> JsonResponse:
    """Generate a 3-ingredient combination, prioritizing AI-driven autonomous synthesis."""
    try:
        data = json.loads(request.body)
        drink_type = data.get('drink_type', 'SODA').upper()
        mode = data.get('mode', 'standard')
        
        all_compatible = AIAssistant.get_filtered_inventory(drink_type=drink_type)
        
        if all_compatible.count() < 3:
             return JsonResponse({'error': 'Insufficient reagents in inventory for a random synthesis.'}, status=400)

        selection: List[Dict[str, Any]] = []
        design_intent = ""
        
        status = AIAssistant.check_status()
        if status == 'synchronized':
            inventory_context = AIAssistant.get_static_ingredients_context(drink_type=drink_type)
            
            ai_result = AIAssistant.synthesize_surprise_mix(
                inventory=inventory_context,
                mode=mode,
                drink_type=drink_type
            )
            
            if ai_result and 'selection' in ai_result:
                design_intent = ai_result.get('design_intent', '')
                for item in ai_result['selection']:
                    name = item.get('name', '').lower()
                    match = next((i for i in all_compatible if i.name.lower() == name), None)
                    if not match:
                        match = next((i for i in all_compatible if f"{i.brand} {i.name}".lower() == name), None)
                    if not match:
                        match = next((i for i in all_compatible if name in i.name.lower() or i.name.lower() in name), None)
                    
                    if match and match not in [s['obj'] for s in selection]:
                        selection.append({
                            'obj': match,
                            'amount': item.get('amount')
                        })
        
        target_count = random.randint(2, 4) if drink_type != 'COFFEE' else random.randint(3, 5)
        
        if len(selection) < target_count:
            selection = [] # Clear any partial AI selection
            design_intent = "" 
            
            if drink_type == 'COFFEE':
                potential_bases = all_compatible.filter(physical_state='SOLID_EXTRACTABLE')
            else:
                potential_bases = all_compatible.filter(physical_state='SYRUP', mixology_function='FLAVORING')
            
            if potential_bases.exists():
                selection.append({'obj': random.choice(list(potential_bases)), 'amount': None})
            
            if drink_type == 'COFFEE' and target_count >= 3:
                # Prioritize VOLUME_BASE / LIQUID (milks) as secondary ingredient, fallback to others
                additives = all_compatible.filter(mixology_function='VOLUME_BASE', physical_state='LIQUID').exclude(id__in=[i['obj'].id for i in selection])
                if not additives.exists():
                    additives = all_compatible.exclude(physical_state='SOLID_EXTRACTABLE').exclude(id__in=[i['obj'].id for i in selection])
                
                if additives.exists():
                    target_additive = random.choice(list(additives))
                    
                    remaining_reagents = list(all_compatible.exclude(id__in=[i['obj'].id for i in selection]).exclude(id=target_additive.id))
                    random.shuffle(remaining_reagents)
                    
                    while len(selection) < (target_count - 1) and remaining_reagents:
                        selection.append({'obj': remaining_reagents.pop(), 'amount': None})
                    
                    selection.insert(1, {'obj': target_additive, 'amount': None})
                else:
                    remaining_reagents = list(all_compatible.exclude(id__in=[i['obj'].id for i in selection]))
                    random.shuffle(remaining_reagents)
                    while len(selection) < target_count and remaining_reagents:
                        selection.append({'obj': remaining_reagents.pop(), 'amount': None})
            else:
                remaining_reagents = list(all_compatible.exclude(id__in=[i['obj'].id for i in selection]))
                random.shuffle(remaining_reagents)
                
                while len(selection) < target_count and remaining_reagents:
                    selection.append({'obj': remaining_reagents.pop(), 'amount': None})

            ratio_profile = random.choice(['parity', 'tiered', 'nuanced'])
            for idx, item in enumerate(selection):
                if item['amount'] is not None: continue
                
                if ratio_profile == 'parity':
                    item['amount'] = 100.0 if drink_type != 'COFFEE' else 15.0
                elif ratio_profile == 'tiered':
                    item['amount'] = [100.0, 50.0, 25.0, 15.0][min(idx, 3)] if drink_type != 'COFFEE' else [18.0, 5.0, 2.0, 2.0, 2.0][min(idx, 4)]
                else:
                    item['amount'] = random.choice([100.0, 75.0, 50.0, 25.0, 10.0]) if drink_type != 'COFFEE' else random.choice([18.0, 10.0, 5.0, 2.0])
            
        if drink_type == 'COFFEE':
            for item in selection:
                item['amount'] = sanitize_coffee_amount(item['obj'], item['amount'])

        multibrand_names = get_multibrand_names_in_inventory()
        result = []
        for item in selection:
            ing = item['obj']
            result.append({
                'id': ing.id,
                'name': get_display_name(ing, multibrand_names),
                'category': ing.category,
                'type': ing.ingredient_type,
                'physical_state': ing.physical_state,
                'mixology_function': ing.mixology_function,
                'intensity': ing.intensity,
                'sweetness': ing.sweetness,
                'acidity': ing.acidity,
                'bitterness': ing.bitterness,
                'complexity': ing.complexity,
                'base_suitability': ing.base_suitability,
                'accent_suitability': ing.accent_suitability,
                'is_ready_to_drink': ing.is_ready_to_drink,
                'is_dry': ing.is_dry,
                'amount': item['amount']
            })
            
        logger.info(f"RandomPairing - Info - Successfully generated surprise pairing with {len(result)} items (AI used: {status == 'synchronized'})")
        return JsonResponse({
            'status': 'success', 
            'ingredients': result,
            'reasoning': design_intent
        })
    except Exception as e:
        logger.error(f"RandomPairing - Error - Failed to generate random pairing: {e}")
        return JsonResponse({'error': str(e)}, status=500)