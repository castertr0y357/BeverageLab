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
    get_recommendation, get_tiered_recommendation,
    generate_recipe_name, suggest_categories, calculate_recipe_stats
)
from ...ai_service import AIAssistant

logger = logging.getLogger(__name__)

def get_display_name(ing: Ingredient, multibrand_names: Set[str]) -> str:
    """Return name with brand if there are multiple brands of this flavor in inventory."""
    if ing.brand and ing.name.lower() in multibrand_names:
        return f"{ing.name} ({ing.brand})"
    return ing.name

def get_multibrand_names_in_inventory() -> Set[str]:
    """Get lowercase names of ingredients that have multiple brands in active inventory."""
    from django.db.models import Count
    qs = Ingredient.objects.filter(is_in_inventory=True).values('name').annotate(
        brand_count=Count('brand', distinct=True)
    ).filter(brand_count__gt=1)
    return {item['name'].lower() for item in qs}

def sanitize_coffee_amount(ingredient: Ingredient, amount: Optional[Union[float, int]] = None) -> float:
    """Ensure coffee ingredients have proper gram/volume amounts based on their role/type."""
    is_coffee = (ingredient.physical_state == 'SOLID_EXTRACTABLE') if ingredient.physical_state else (ingredient.ingredient_type == 'COFFEE_BEAN')
    is_dairy = (ingredient.mixology_function == 'VOLUME_BASE' and ingredient.physical_state == 'LIQUID') if ingredient.mixology_function else (ingredient.ingredient_type == 'DAIRY')
    if is_coffee:
        return 18.0
    elif is_dairy:
        return 50.0
    else:
        return 15.0

def find_ingredient_by_name(name_str: str, inventory_items: List[Ingredient]) -> Optional[Ingredient]:
    """Resiliently lookup an ingredient in active inventory by various name formats."""
    name_clean = name_str.strip().lower()
    if not name_clean:
        return None
    
    # Tier 1: Exact matches or exact display matches
    for inv in inventory_items:
        inv_name = inv.name.lower()
        inv_full = f"{inv.brand} {inv.name}".lower() if inv.brand else inv_name
        inv_display = f"{inv.name} ({inv.brand})".lower() if inv.brand else inv_name
        
        if name_clean in (inv_name, inv_full, inv_display):
            return inv
            
    # Tier 2: Partial matches
    for inv in inventory_items:
        inv_name = inv.name.lower()
        inv_full = f"{inv.brand} {inv.name}".lower() if inv.brand else inv_name
        inv_display = f"{inv.name} ({inv.brand})".lower() if inv.brand else inv_name
        
        if (name_clean in inv_name or inv_name in name_clean or
            name_clean in inv_full or inv_full in name_clean or
            name_clean in inv_display or inv_display in name_clean):
            return inv
            
    return None

def ai_bulk_analyze_task(update_progress: Callable[..., None]) -> None:
    update_progress(5, status='RUNNING')
    try:
        targets = Ingredient.objects.filter(is_in_inventory=True)
        if not targets.exists():
            update_progress(100, status='SUCCESS', result_data={'message': 'No inventory reagents found to synthesize.'})
            return
            
        target_list = list(targets)
        batch_size = 15
        total_analyzed = 0
        total_targets = len(target_list)
        
        for i in range(0, total_targets, batch_size):
            batch = target_list[i : i + batch_size]
            batch_data = [{'name': f"{t.brand} {t.name}" if t.brand else t.name, 'description': t.description or ''} for t in batch]
            
            pct = int((i / total_targets) * 90) + 5
            update_progress(pct, status='RUNNING')
            
            results = AIAssistant.bulk_analyze_flavor_profiles(batch_data)
            
            if results and isinstance(results, list):
                for res in results:
                    ing_name = res.get('name', '').lower()
                    match = next((t for t in batch if t.name.lower() == ing_name), None)
                    if not match:
                        match = next((t for t in batch if ing_name in t.name.lower() or t.name.lower() in ing_name), None)
                        
                    if match:
                        match.intensity = max(1, min(5, round(res.get('intensity', match.intensity))))
                        match.sweetness = max(1, min(5, round(res.get('sweetness', match.sweetness))))
                        match.acidity = max(1, min(5, round(res.get('acidity', match.acidity))))
                        match.bitterness = max(1, min(5, round(res.get('bitterness', match.bitterness))))
                        match.complexity = max(1, min(5, round(res.get('complexity', match.complexity))))
                        match.base_suitability = max(1.0, min(5.0, round(res.get('base_suitability', match.base_suitability), 1)))
                        match.accent_suitability = max(1.0, min(5.0, round(res.get('accent_suitability', match.accent_suitability), 1)))
                        
                        category_res = res.get('category', '').strip().lower()
                        if category_res in ['citrus', 'berry', 'tropical', 'herbal', 'spice', 'sweet', 'sour', 'artificial', 'coffee']:
                            match.category = category_res
                            
                        physical_state_res = res.get('physical_state', '').strip().upper()
                        if physical_state_res in ['LIQUID', 'SYRUP', 'SAUCE', 'POWDER', 'SOLID_EXTRACTABLE']:
                            match.physical_state = physical_state_res
                            
                        mixology_function_res = res.get('mixology_function', '').strip().upper()
                        if mixology_function_res in ['VOLUME_BASE', 'FLAVORING', 'SWEETENER', 'TEXTURIZER', 'GARNISH']:
                            match.mixology_function = mixology_function_res
                            
                        type_res = res.get('ingredient_type', '').strip().upper()
                        if type_res in ['SODA_SYRUP', 'COFFEE_BEAN', 'DAIRY', 'ADDITIVE', 'OTHER']:
                            match.ingredient_type = type_res
                            
                        systems_res = res.get('compatible_systems')
                        if systems_res:
                            if isinstance(systems_res, list):
                                systems_list = [s.strip().upper() for s in systems_res if s.strip().upper() in ['SODA', 'COFFEE', 'SLUSHIE']]
                            else:
                                systems_list = [s.strip().upper() for s in str(systems_res).split(',') if s.strip().upper() in ['SODA', 'COFFEE', 'SLUSHIE']]
                            if systems_list:
                                match.compatible_systems = ",".join(systems_list)
                                
                        if 'is_ready_to_drink' in res:
                            match.is_ready_to_drink = bool(res.get('is_ready_to_drink'))
                        if 'is_dry' in res:
                            match.is_dry = bool(res.get('is_dry'))
                            
                        if 'roast_level' in res and res.get('roast_level'):
                            match.roast_level = str(res.get('roast_level')).upper()
                        if 'is_decaf' in res:
                            match.is_decaf = bool(res.get('is_decaf'))
                        if 'body_intensity' in res:
                            try:
                                match.body_intensity = int(res.get('body_intensity'))
                            except (ValueError, TypeError):
                                pass
                        if 'acidity_score' in res:
                            try:
                                match.acidity_score = int(res.get('acidity_score'))
                            except (ValueError, TypeError):
                                pass
                        if 'bitterness_score' in res:
                            try:
                                match.bitterness_score = int(res.get('bitterness_score'))
                            except (ValueError, TypeError):
                                pass
                        if 'flavor_notes' in res:
                            notes_val = res.get('flavor_notes')
                            if isinstance(notes_val, list):
                                match.flavor_notes = ", ".join(notes_val)
                            else:
                                match.flavor_notes = str(notes_val or '')

                        match.ai_notes = res.get('ai_notes', match.ai_notes)
                        match.save()
                        total_analyzed += 1
                        
        logger.info(f"AIBulkAnalysisTask - Info - Bulk analysis complete. {total_analyzed} reagents synchronized.")
        update_progress(100, status='SUCCESS', result_data={'message': f'Bulk analysis complete. {total_analyzed} reagents synchronized.', 'total_analyzed': total_analyzed})
    except Exception as e:
        logger.error(f"AIBulkAnalysisTask - Error - Bulk Synthesis Failure: {e}", exc_info=True)
        update_progress(100, status='FAILURE', error_msg=str(e))

