"""AI Assistant integration views."""

import json
import logging
import random
from typing import Dict, Any, List, Set, Union, Optional, Callable

from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.db.models import Q

from ..models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, SystemConfiguration, LLMProvider
from ..tasks_registry import submit_task
from ..recommendations import (
    get_recommendation, get_tiered_recommendation,
    generate_recipe_name, suggest_categories
)
from ..ai_service import AIAssistant

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




@csrf_exempt
@require_http_methods(["POST"])
def get_recommendations_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for tiered ingredient recommendations."""
    try:
        data = json.loads(request.body)
        ingredient_ids = data.get('ingredient_ids', [])
        ingredient_ids = [0 if i == 'virtual_water' else int(i) for i in ingredient_ids if str(i).isdigit() or i == 'virtual_water']
        experimental = data.get('mode') == 'experimental' or data.get('experimental', False)
        force_type = data.get('force_type') # e.g. 'ADDITIVE'
        drink_type = data.get('drink_type', 'SODA').upper()
        exclude_ids = data.get('exclude_ids', [])
        exclude_ids = [int(i) for i in exclude_ids if str(i).isdigit()]

        # Merge all selected ingredients into the exclude pool to prevent duplicate recommendations!
        for ing_id in ingredient_ids:
            if ing_id > 0 and ing_id not in exclude_ids:
                exclude_ids.append(ing_id)

        serialized_recs: List[Dict[str, Any]] = []
        multibrand_names = get_multibrand_names_in_inventory()

        if len(ingredient_ids) == 0:
            result = get_recommendation([], drink_type=drink_type, experimental=experimental, force_type=force_type, exclude_ids=exclude_ids)
            serialized_recs = [
                {
                    'id': r['ingredient'].id,
                    'name': get_display_name(r['ingredient'], multibrand_names),
                    'category': r['ingredient'].category,
                    'type': r['ingredient'].ingredient_type,
                    'physical_state': r['ingredient'].physical_state,
                    'mixology_function': r['ingredient'].mixology_function,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
                    'base_suitability': r['ingredient'].base_suitability,
                    'accent_suitability': r['ingredient'].accent_suitability,
                    'is_ready_to_drink': r['ingredient'].is_ready_to_drink,
                    'is_dry': r['ingredient'].is_dry,
                    'favorite': r['ingredient'].favorite,
                    'score': r['score'],
                    'resonance': round(min(r['score'] * 15.0, 99.8), 1),
                    'reason': r['reason'],
                    'tier': 'suggestions'
                } for r in result.get('recommended', [])
            ]
        elif len(ingredient_ids) == 1:
            result = get_recommendation(ingredient_ids, drink_type=drink_type, experimental=experimental, force_type=force_type, exclude_ids=exclude_ids)
            serialized_recs = [
                {
                    'id': r['ingredient'].id,
                    'name': get_display_name(r['ingredient'], multibrand_names),
                    'category': r['ingredient'].category,
                    'type': r['ingredient'].ingredient_type,
                    'physical_state': r['ingredient'].physical_state,
                    'mixology_function': r['ingredient'].mixology_function,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
                    'base_suitability': r['ingredient'].base_suitability,
                    'accent_suitability': r['ingredient'].accent_suitability,
                    'is_ready_to_drink': r['ingredient'].is_ready_to_drink,
                    'is_dry': r['ingredient'].is_dry,
                    'favorite': r['ingredient'].favorite,
                    'score': r['score'],
                    'resonance': round(min(r['score'] * 15.0, 99.8), 1),
                    'reason': r['reason'],
                    'tier': 'secondary'
                } for r in result.get('recommended', [])
            ]
        else:
            result = get_recommendation(ingredient_ids, drink_type=drink_type, experimental=experimental, force_type=force_type, exclude_ids=exclude_ids)
            scale_factor = 15.0 / len(ingredient_ids)
            serialized_recs = [
                {
                    'id': r['ingredient'].id,
                    'name': get_display_name(r['ingredient'], multibrand_names),
                    'category': r['ingredient'].category,
                    'type': r['ingredient'].ingredient_type,
                    'physical_state': r['ingredient'].physical_state,
                    'mixology_function': r['ingredient'].mixology_function,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
                    'base_suitability': r['ingredient'].base_suitability,
                    'accent_suitability': r['ingredient'].accent_suitability,
                    'is_ready_to_drink': r['ingredient'].is_ready_to_drink,
                    'is_dry': r['ingredient'].is_dry,
                    'favorite': r['ingredient'].favorite,
                    'score': r['score'],
                    'resonance': round(min(r['score'] * scale_factor, 99.8), 1),
                    'reason': r['reason'],
                    'tier': 'tertiary'
                } for r in result.get('recommended', [])
            ]

        serialized = {'recommended': serialized_recs, 'recipes': []}
        return JsonResponse(serialized)
    except json.JSONDecodeError as e:
        logger.warning(f"RecommendationsAPI - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def generate_name_api(request: HttpRequest) -> JsonResponse:
    """Return a suggested recipe name for a list of ingredient IDs."""
    try:
        data = json.loads(request.body)
        ingredient_ids = data.get('ingredient_ids', [])
        ingredient_ids = [0 if i == 'virtual_water' else int(i) for i in ingredient_ids if str(i).isdigit() or i == 'virtual_water']
        name = generate_recipe_name(ingredient_ids)
        return JsonResponse({'name': name})
    except json.JSONDecodeError as e:
        logger.warning(f"GenerateNameAPI - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
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


@csrf_exempt
@require_http_methods(["POST"])
def ai_chat_api(request: HttpRequest) -> HttpResponse:
    """Bridge the user to the Creative Mixologist AI Assistant."""
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        history = data.get('history', [])
        current_ingredients = data.get('current_ingredients', []) # List of names
        
        if not user_message and not current_ingredients:
            return JsonResponse({'error': 'No input provided'}, status=400)
            
        # Enrich prompt with laboratory context
        lab_context = ""
        if current_ingredients:
            lab_context = f"\n\n[Laboratory Context: Current Compound Contains: {', '.join(current_ingredients)}]"
        
        # Get active system/drink type to filter inventory context
        drink_type = data.get('drink_type')
        if not drink_type and current_ingredients:
            first_ing = Ingredient.objects.filter(Q(name__iexact=current_ingredients[0]) | Q(brand__iexact=current_ingredients[0])).first()
            if first_ing and first_ing.compatible_systems:
                systems = [s.strip().upper() for s in first_ing.compatible_systems.split(',')]
                if systems:
                    drink_type = systems[0]
        if not drink_type:
            drink_type = 'SODA'

        inventory_context = AIAssistant.get_static_ingredients_context(drink_type=drink_type)
        prompt = user_message + lab_context
        
        # Bridge to the streaming generator
        response_generator = AIAssistant.chat_stream(prompt, history=history, context=inventory_context, drink_type=drink_type)
        return StreamingHttpResponse(response_generator, content_type='text/event-stream')
        
    except Exception as e:
        logger.error(f"AIChat - Error - Laboratory Communication Failure: {e}", exc_info=True)
        return JsonResponse({'error': f"Laboratory Communication Failure: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_llm_provider_api(request: HttpRequest) -> JsonResponse:
    """Manage multiple LLM providers (Cloud and Local)."""
    if not request.user.is_staff:
        logger.warning(f"LLMProviderManagement - Warning - Unauthorized API attempt to save LLM provider by {request.user}")
        return JsonResponse({'error': 'Staff authentication required.'}, status=403)
        
    try:
        data = json.loads(request.body)
        pk = data.get('id')
        
        if pk:
            provider = get_object_or_404(LLMProvider, pk=pk)
        else:
            provider = LLMProvider()
            
        provider.name = data.get('name', 'New Provider').strip()
        provider.provider_type = data.get('provider_type', 'OPENAI')
        provider.api_key = data.get('api_key', '').strip()
        provider.base_url = data.get('base_url', '').strip()
        provider.default_model = data.get('default_model', '').strip()
        provider.is_enabled = bool(data.get('is_enabled', False))
        
        enable_thinking = data.get('enable_thinking')
        provider.enable_thinking = bool(enable_thinking) if enable_thinking is not None else False
        
        thinking_effort = data.get('thinking_effort')
        provider.thinking_effort = 'medium' if not thinking_effort else str(thinking_effort).strip().lower()
        
        provider.enable_keep_warm = bool(data.get('enable_keep_warm', False))
        
        provider.save()
        
        # If this is set as default
        if data.get('set_default', False):
            config = SystemConfiguration.get_config()
            config.default_llm_provider = provider
            config.save()
            
        logger.info(f"LLMProviderManagement - Info - Saved LLM Provider '{provider.name}' (ID: {provider.id})")
        return JsonResponse({'status': 'success', 'id': provider.id})
    except Exception as e:
        logger.error(f"LLMProviderManagement - Error - Failed to save provider: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def delete_llm_provider_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Remove an LLM provider configuration."""
    if not request.user.is_staff:
        logger.warning(f"LLMProviderManagement - Warning - Unauthorized API attempt to delete LLM provider {pk} by {request.user}")
        return JsonResponse({'error': 'Forbidden'}, status=403)
    provider = get_object_or_404(LLMProvider, pk=pk)
    name = provider.name
    provider.delete()
    logger.info(f"LLMProviderManagement - Info - Deleted LLM Provider '{name}' (ID: {pk})")
    return JsonResponse({'status': 'success'})


@csrf_exempt
@require_http_methods(["POST"])
def fetch_provider_models_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Fetch available models for a specific AI provider."""
    provider = get_object_or_404(LLMProvider, pk=pk)
    models = AIAssistant.list_models(provider)
    if models:
        logger.info(f"LLMModelDiscovery - Info - Fetched {len(models)} models for provider '{provider.name}'")
        return JsonResponse({'status': 'success', 'models': models})
    else:
        logger.warning(f"LLMModelDiscovery - Warning - Could not fetch models for provider '{provider.name}'")
        return JsonResponse({'status': 'error', 'message': 'Could not fetch models. Check API keys and base URL.'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def discover_provider_models_api(request: HttpRequest) -> JsonResponse:
    """Fetch models for unsaved provider credentials."""
    if not request.user.is_staff:
        logger.warning(f"LLMModelDiscovery - Warning - Unauthorized API attempt to discover models by {request.user}")
        return JsonResponse({'error': 'Staff credentials required.'}, status=403)
        
    try:
        data = json.loads(request.body)
        provider_type = data.get('provider_type')
        api_key = data.get('api_key', '')
        base_url = data.get('base_url', '')
        
        if not provider_type:
            return JsonResponse({'error': 'Provider technology stack required.'}, status=400)
            
        # Create a temporary, unsaved object for the model list call
        temp_provider = LLMProvider(
            provider_type=provider_type,
            api_key=api_key,
            base_url=base_url
        )
        
        models = AIAssistant.list_models(temp_provider)
        if models:
            logger.info(f"LLMModelDiscovery - Info - Discovered {len(models)} models for temporary provider {provider_type}")
            return JsonResponse({'status': 'success', 'models': models})
        else:
            logger.warning(f"LLMModelDiscovery - Warning - Model discovery returned no models or credentials rejected for {provider_type}")
            return JsonResponse({'status': 'error', 'message': 'Discovery Protocol: No models found or credentials rejected.'}, status=400)
    except Exception as e:
        logger.error(f"LLMModelDiscovery - Error - Molecular Sync Failed: {e}")
        return JsonResponse({'error': f"Molecular Sync Failed: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ai_suggest_api(request: HttpRequest) -> HttpResponse:
    """Get proactive, structured multi-suggestions from the assistant, streaming progress first."""
    try:
        data = json.loads(request.body)
        ingredients = data.get('ingredients', [])
        mode = data.get('mode', 'standard')
        exclude = data.get('exclude', [])
        drink_type = data.get('drink_type', 'SODA').upper()
        force_type = data.get('force_type')
        
        logger.warning(f"AISuggestion - Info - Suggestion request. Ingredients: {ingredients}, drink_type: {drink_type}, force_type: {force_type}")
        
        if not ingredients:
            ingredients = ["NONE - Initial Synthesis"]
            
        def generator():
            def send_progress(msg: str):
                return f"data: {json.dumps({'status': 'progress', 'message': msg})}\n\n"

            yield send_progress("Scanning current compound registry...")
            
            # Get full static inventory context
            inventory_context = AIAssistant.get_static_ingredients_context(drink_type=drink_type)

            # Filter the candidate pool for this step
            all_ingredients = Ingredient.objects.filter(is_in_inventory=True)
            candidate_pool = all_ingredients
            if force_type:
                ft = force_type.upper()
                if ft == 'COFFEE_BEAN':
                    candidate_pool = candidate_pool.filter(physical_state='SOLID_EXTRACTABLE')
                elif ft == 'DAIRY':
                    candidate_pool = candidate_pool.filter(mixology_function='VOLUME_BASE', physical_state='LIQUID')
                elif ft == 'SODA_SYRUP':
                    candidate_pool = candidate_pool.filter(physical_state='SYRUP', mixology_function='FLAVORING')
                elif ft == 'ADDITIVE':
                    candidate_pool = candidate_pool.filter(mixology_function__in=['FLAVORING', 'SWEETENER', 'TEXTURIZER', 'GARNISH'])
                else:
                    candidate_pool = candidate_pool.filter(ingredient_type=force_type)
            if mode != 'experimental':
                candidate_pool = candidate_pool.filter(compatible_systems__icontains=drink_type)

            # Merge active ingredients into exclusions to prevent duplicate suggestions
            active_names = [name.strip().lower() for name in ingredients if name and name != "NONE - Initial Synthesis"]
            exclude_names = [name.strip().lower() for name in exclude]
            
            # Determine actual exclusion based on candidate pool availability
            remaining = []
            for ing in candidate_pool:
                display_name = f"{ing.brand} {ing.name}" if ing.brand else ing.name
                if ing.name.strip().lower() in exclude_names or display_name.strip().lower() in exclude_names or ing.name.strip().lower() in active_names or display_name.strip().lower() in active_names:
                    continue
                remaining.append(ing)
                
            # Create a combined exclude list for context prompts
            combined_exclude = list(exclude)
            for act_n in ingredients:
                if act_n and act_n != "NONE - Initial Synthesis" and act_n not in combined_exclude:
                    combined_exclude.append(act_n)
                    
            if remaining:
                actual_exclude = combined_exclude
            else:
                actual_exclude = []
            yield send_progress("Locating matching flavor affinity groups...")
            yield send_progress("Querying Mixology Oracle...")

            raw_suggestion = ""
            retry_note = None
            
            for attempt in range(3):
                # On the final attempt, strip persona for brute-force compliance
                if attempt == 2 and not retry_note:
                     retry_note = "CRITICAL DATA MISMATCH: STOP all prose. Provide ONLY the JSON array of ingredients from the registry. [RAW JSON ONLY]"
                
                raw_suggestion = AIAssistant.suggest_autonomous(
                    ingredients, mode, 
                    drink_type=drink_type,
                    inventory=inventory_context, 
                    exclude=actual_exclude,
                    retry_note=retry_note,
                    force_type=force_type
                )
                logger.warning(f"AISuggestion - Info - Raw suggestion from LLM: {raw_suggestion}")
                
                suggested_data = raw_suggestion
                
                if suggested_data:
                    yield send_progress("Sanitizing extraction volumes & balancing ratios...")
                    if isinstance(suggested_data, str):
                        try:
                            suggested_data = json.loads(suggested_data)
                        except Exception:
                            pass

                    suggestions_list = []
                    rebalancing = {}
                    seal_recommended = False
                    seal_resonance = 0
                    reasoning = ''

                    if isinstance(suggested_data, dict):
                        suggestions_list = suggested_data.get('suggestions', [])
                        rebalancing = suggested_data.get('rebalancing', {})
                        seal_recommended = suggested_data.get('seal_recommended', False)
                        seal_resonance = suggested_data.get('seal_resonance', 0)
                        reasoning = suggested_data.get('reasoning', '')
                    elif isinstance(suggested_data, list):
                        suggestions_list = suggested_data

                    enriched: List[Dict[str, Any]] = []
                    inventory_items = list(Ingredient.objects.filter(is_in_inventory=True))
                    
                    for item in suggestions_list:
                        ing_name = item.get('name', '')
                        target_obj = find_ingredient_by_name(ing_name, inventory_items)
                                    
                        if target_obj:
                            is_match = True
                            if force_type:
                                ft = force_type.upper()
                                if ft == 'COFFEE_BEAN':
                                    is_match = (target_obj.physical_state == 'SOLID_EXTRACTABLE')
                                elif ft == 'DAIRY':
                                    is_match = (target_obj.mixology_function == 'VOLUME_BASE' and target_obj.physical_state == 'LIQUID')
                                elif ft == 'SODA_SYRUP':
                                    is_match = (target_obj.physical_state == 'SYRUP' and target_obj.mixology_function == 'FLAVORING')
                                elif ft == 'ADDITIVE':
                                    is_match = (target_obj.mixology_function in ['FLAVORING', 'SWEETENER', 'TEXTURIZER', 'GARNISH'])
                                else:
                                    is_match = (target_obj.ingredient_type == force_type)
                            if not is_match:
                                logger.warning(f"AISuggestion - Warning - LLM suggested '{target_obj.name}' which does not match force_type '{force_type}'")
                                continue
                            intensity_delta = 0
                            active_ingredients = []
                            for ing_name in ingredients:
                                if ing_name and ing_name != "NONE - Initial Synthesis":
                                    ing_clean = ing_name.strip().lower()
                                    ing_obj = next((inv for inv in inventory_items if inv.name.lower() == ing_clean), None)
                                    if not ing_obj:
                                        ing_obj = Ingredient.objects.filter(Q(name__iexact=ing_clean) | Q(brand__iexact=ing_clean)).first()
                                    if ing_obj:
                                        active_ingredients.append(ing_obj)
                            
                            if active_ingredients:
                                avg_intensity = sum(ing.intensity for ing in active_ingredients) / len(active_ingredients)
                                intensity_delta = abs(target_obj.intensity - avg_intensity)
                            else:
                                intensity_delta = 3
                            
                            resonance = 85 + (max(0, 3 - intensity_delta) * 4) + random.uniform(0.1, 2.5)
                            
                            amount = item.get('amount')
                            if drink_type == 'COFFEE':
                                amount = sanitize_coffee_amount(target_obj, amount)

                            multibrand_names = get_multibrand_names_in_inventory()
                            enriched.append({
                                'id': target_obj.id,
                                'name': get_display_name(target_obj, multibrand_names),
                                'category': target_obj.category,
                                'type': target_obj.ingredient_type,
                                'intensity': target_obj.intensity,
                                'sweetness': target_obj.sweetness,
                                'acidity': target_obj.acidity,
                                'bitterness': target_obj.bitterness,
                                'complexity': target_obj.complexity,
                                'base_suitability': target_obj.base_suitability,
                                'accent_suitability': target_obj.accent_suitability,
                                'physical_state': target_obj.physical_state,
                                'mixology_function': target_obj.mixology_function,
                                'is_ready_to_drink': target_obj.is_ready_to_drink,
                                'is_dry': target_obj.is_dry,
                                'favorite': target_obj.favorite,
                                'resonance': round(min(resonance, 99.8), 1),
                                'reason': item.get('reason', 'Molecular Affinity Match'),
                                'amount': amount,
                                'profile': item.get('profile', None)
                            })
                    
                    if drink_type == 'COFFEE' and rebalancing:
                        logger.warning(f"AISuggestion - Info - Raw AI rebalancing before sanitization: {rebalancing}")
                        sanitized_rebalancing = {}
                        
                        beans_in_rebal = {}
                        dairy_in_rebal = {}
                        other_in_rebal = {}
                        
                        for key, val in rebalancing.items():
                            target_obj = find_ingredient_by_name(key, inventory_items)
                            if target_obj:
                                val_float = float(val) if val is not None else 0.0
                                if target_obj.physical_state == 'SOLID_EXTRACTABLE':
                                    beans_in_rebal[key] = val_float
                                elif target_obj.mixology_function == 'VOLUME_BASE' and target_obj.physical_state == 'LIQUID':
                                    dairy_in_rebal[key] = val_float
                                else:
                                    other_in_rebal[key] = val_float
                            else:
                                logger.warning(f"AISuggestion - Warning - Rebalancing key '{key}' not found in inventory, skipping raw value {val}")
                                
                        # Sanitize coffee beans (sum to 18.0g)
                        if beans_in_rebal:
                            total_bean_val = sum(beans_in_rebal.values())
                            if total_bean_val > 0:
                                for key, val in beans_in_rebal.items():
                                    sanitized_rebalancing[key] = round((val / total_bean_val) * 18.0, 1)
                            else:
                                num_beans = len(beans_in_rebal)
                                for key in beans_in_rebal:
                                    sanitized_rebalancing[key] = round(18.0 / num_beans, 1)
                                    
                        # Sanitize dairy (sum to 50.0ml)
                        if dairy_in_rebal:
                            total_dairy_val = sum(dairy_in_rebal.values())
                            if total_dairy_val > 0:
                                for key, val in dairy_in_rebal.items():
                                    sanitized_rebalancing[key] = round((val / total_dairy_val) * 50.0, 1)
                            else:
                                num_dairy = len(dairy_in_rebal)
                                for key in dairy_in_rebal:
                                    sanitized_rebalancing[key] = round(50.0 / num_dairy, 1)
                                    
                        # Sanitize additives/others (15.0ml each)
                        for key in other_in_rebal:
                            sanitized_rebalancing[key] = 15.0
                            
                        rebalancing = sanitized_rebalancing
                        logger.warning(f"AISuggestion - Info - Sanitized rebalancing: {rebalancing}")

                    if enriched:
                        logger.info(f"AISuggestion - Info - Successfully fetched {len(enriched)} suggestions on attempt {attempt+1}")
                        yield f"data: {json.dumps({'status': 'success', 'suggestions': enriched, 'rebalancing': rebalancing, 'seal_recommended': seal_recommended, 'seal_resonance': seal_resonance, 'reasoning': reasoning})}\n\n"
                        return
                
                retry_note = "Your last synthesis signal was unparseable. Adhere strictly to the JSON array format using the Inventory Registry's exact names. [NO MARKDOWN]"

            # Fallback to standard/algorithmic recommendations if AI returned nothing
            logger.warning("AISuggestion - Warning - AI returned no matches. Falling back to algorithmic recommendations.")
            
            # Map name strings back to database IDs
            ing_ids = []
            for name in ingredients:
                if name == "NONE - Initial Synthesis" or name == "virtual_water" or name == "Carbonated Water" or name == "Ice":
                    continue
                ing_obj = Ingredient.objects.filter(name__iexact=name).first()
                if ing_obj:
                    ing_ids.append(ing_obj.id)
            
            # Map exclude names back to database IDs
            excl_ids = []
            for name in exclude:
                ing_obj = Ingredient.objects.filter(name__iexact=name).first()
                if ing_obj:
                    excl_ids.append(ing_obj.id)
            
            from soda_mixer.flavors.recommendations import get_recommendation
            experimental = (mode == 'experimental')
            
            recs_data = get_recommendation(ing_ids, drink_type=drink_type, experimental=experimental, force_type=force_type, exclude_ids=excl_ids)
            scale_factor = 15.0
            if len(ing_ids) >= 2:
                scale_factor = 15.0 / len(ing_ids)
            
            for item in recs_data.get('recommended', []):
                target_obj = item['ingredient']
                amount = None
                if drink_type == 'COFFEE':
                    amount = sanitize_coffee_amount(target_obj, None)
                
                multibrand_names = get_multibrand_names_in_inventory()
                enriched.append({
                    'id': target_obj.id,
                    'name': get_display_name(target_obj, multibrand_names),
                    'category': target_obj.category,
                    'type': target_obj.ingredient_type,
                    'intensity': target_obj.intensity,
                    'sweetness': target_obj.sweetness,
                    'acidity': target_obj.acidity,
                    'bitterness': target_obj.bitterness,
                    'complexity': target_obj.complexity,
                    'base_suitability': target_obj.base_suitability,
                    'accent_suitability': target_obj.accent_suitability,
                    'is_ready_to_drink': target_obj.is_ready_to_drink,
                    'is_dry': target_obj.is_dry,
                    'resonance': round(min(item['score'] * scale_factor, 99.8), 1),  # Map score to 0-100 scale dynamically
                    'reason': f"Algorithmic: {item['reason']}",
                    'amount': amount,
                    'profile': None
                })
            
            yield f"data: {json.dumps({'status': 'success', 'suggestions': enriched, 'rebalancing': {}, 'seal_recommended': False, 'seal_resonance': 0, 'reasoning': 'AI suggestions fallback.'})}\n\n"

        return StreamingHttpResponse(generator(), content_type='text/event-stream')

    except Exception as e:
        logger.error(f"AISuggestion - Error - Autonomous Suggestion Failed: {e}", exc_info=True)
        def error_generator():
            yield f"data: {json.dumps({'status': 'error', 'message': f'Autonomous Suggestion Failed: {str(e)}'})}\n\n"
        return StreamingHttpResponse(error_generator(), content_type='text/event-stream')


@csrf_exempt
@require_http_methods(["POST"])
def ai_synthesize_api(request: HttpRequest) -> JsonResponse:
    """Generate a flavor synthesis report for a finalized compound."""
    try:
        data = json.loads(request.body)
        ingredients = data.get('ingredients', [])
        drink_type = data.get('drink_type', 'SODA').upper()
        
        if not ingredients:
            return JsonResponse({'error': 'No ingredients provided.'}, status=400)
        
        summary = AIAssistant.synthesize_flavor_summary(ingredients, drink_type)
        logger.info(f"AISynthesis - Info - Generated flavor report for {len(ingredients)} ingredients")
        return JsonResponse({'status': 'success', 'summary': summary})
    except Exception as e:
        logger.error(f"AISynthesis - Error - Surprise mix synthesis report failed: {e}", exc_info=True)
        return JsonResponse({'error': f"Synthesis Report Failed: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ai_analyze_ingredient_api(request: HttpRequest) -> JsonResponse:
    """Use the LLM to synthesize a chemical flavor profile for a new ingredient."""
    try:
        data = json.loads(request.body)
        name = data.get('name')
        brand = data.get('brand', '')
        description = data.get('description', '')
        
        if not name:
            return JsonResponse({'error': 'Ingredient name required for analysis.'}, status=400)
            
        full_name = f"{brand} {name}" if brand else name
        profile = AIAssistant.analyze_flavor_profile(full_name, description)
        if profile:
            logger.info(f"AIIngredientAnalysis - Info - Analyzed profile for reagent '{name}'")
            return JsonResponse({'status': 'success', 'profile': profile})
        else:
            logger.warning(f"AIIngredientAnalysis - Warning - Chemical analysis failed to yield structured data for '{name}'")
            return JsonResponse({'error': 'Chemical analysis failed to yield structured data.'}, status=500)
    except Exception as e:
        logger.error(f"AIIngredientAnalysis - Error - Failed to analyze ingredient: {e}")
        return JsonResponse({'error': str(e)}, status=500)


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


from typing import Callable

@csrf_exempt
@require_http_methods(["POST"])
def ai_bulk_analyze_api(request: HttpRequest) -> JsonResponse:
    """Perform a batch synthesis of flavor profiles for all reagents in inventory."""
    if not request.user.is_staff:
        logger.warning(f"AIBulkAnalysis - Warning - Unauthorized API attempt to bulk analyze by {request.user}")
        return JsonResponse({'error': 'Staff authentication required.'}, status=403)
        
    task = submit_task("Bulk AI Flavor Analysis", ai_bulk_analyze_task)
    return JsonResponse({'status': 'accepted', 'task_id': str(task.uuid)}, status=202)


@csrf_exempt
@require_http_methods(["POST"])
def random_pairing_api(request: HttpRequest) -> JsonResponse:
    """Generate a 3-ingredient combination, prioritizing AI-driven autonomous synthesis."""
    try:
        data = json.loads(request.body)
        drink_type = data.get('drink_type', 'SODA').upper()
        mode = data.get('mode', 'standard')
        
        all_compatible = Ingredient.objects.filter(
            is_in_inventory=True,
            compatible_systems__contains=drink_type
        )
        
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
