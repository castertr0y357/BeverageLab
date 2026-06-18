"""AI Assistant integration views."""

import json
import logging
import random
from typing import Dict, Any, List, Set, Union, Optional

from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.db.models import Q

from ..models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, SystemConfiguration, LLMProvider
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



@csrf_exempt
@require_http_methods(["POST"])
def get_recommendations_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for tiered ingredient recommendations."""
    try:
        data = json.loads(request.body)
        ingredient_ids = data.get('ingredient_ids', [])
        experimental = data.get('mode') == 'experimental' or data.get('experimental', False)
        force_type = data.get('force_type') # e.g. 'ADDITIVE'
        drink_type = data.get('drink_type', 'SODA')

        serialized_recs: List[Dict[str, Any]] = []
        multibrand_names = get_multibrand_names_in_inventory()

        if len(ingredient_ids) == 0:
            result = get_recommendation([], drink_type=drink_type, experimental=experimental, force_type=force_type)
            serialized_recs = [
                {
                    'id': r['ingredient'].id,
                    'name': get_display_name(r['ingredient'], multibrand_names),
                    'category': r['ingredient'].category,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
                    'base_suitability': r['ingredient'].base_suitability,
                    'accent_suitability': r['ingredient'].accent_suitability,
                    'score': r['score'],
                    'reason': r['reason'],
                    'tier': 'suggestions'
                } for r in result.get('recommended', [])
            ]
        elif len(ingredient_ids) == 1:
            result = get_tiered_recommendation(ingredient_ids[0], drink_type=drink_type, experimental=experimental, force_type=force_type)
            serialized_recs = [
                {
                    'id': r['ingredient'].id,
                    'name': get_display_name(r['ingredient'], multibrand_names),
                    'category': r['ingredient'].category,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
                    'base_suitability': r['ingredient'].base_suitability,
                    'accent_suitability': r['ingredient'].accent_suitability,
                    'score': r['score'],
                    'reason': r['reason'],
                    'tier': r.get('tier', 'secondary')
                } for r in result.get('recommended', [])
            ]
        else:
            result = get_tiered_recommendation(ingredient_ids[0], ingredient_ids[1], drink_type=drink_type, experimental=experimental, force_type=force_type)
            serialized_recs = [
                {
                    'id': r['ingredient'].id,
                    'name': get_display_name(r['ingredient'], multibrand_names),
                    'category': r['ingredient'].category,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
                    'base_suitability': r['ingredient'].base_suitability,
                    'accent_suitability': r['ingredient'].accent_suitability,
                    'score': r['score'],
                    'reason': r['reason'],
                    'tier': r.get('tier', 'tertiary')
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
        
        # Get full inventory registry for AI context
        all_ingredients = Ingredient.objects.filter(is_in_inventory=True)
        registry: List[str] = []
        for ing in all_ingredients:
            ing_display = f"{ing.brand} {ing.name}" if ing.brand else ing.name
            registry.append(f"{ing_display} ({ing.get_ingredient_type_display()}, {ing.category.title() if ing.category else 'Misc'}, Intensity: {ing.intensity}/5)")
        inventory_context = "\n".join(registry)

        prompt = user_message + lab_context
        
        # Bridge to the streaming generator
        response_generator = AIAssistant.chat_stream(prompt, history=history, context=inventory_context)
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
        provider.enable_thinking = True if enable_thinking is None else bool(enable_thinking)
        
        thinking_effort = data.get('thinking_effort')
        provider.thinking_effort = 'medium' if not thinking_effort else str(thinking_effort).strip().lower()
        
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
def ai_suggest_api(request: HttpRequest) -> JsonResponse:
    """Get proactive, structured multi-suggestions from the assistant."""
    try:
        data = json.loads(request.body)
        ingredients = data.get('ingredients', [])
        mode = data.get('mode', 'standard')
        exclude = data.get('exclude', [])
        drink_type = data.get('drink_type', 'SODA')
        
        if not ingredients:
            ingredients = ["NONE - Initial Synthesis"]
            
        # Get full inventory registry for AI context
        all_ingredients = Ingredient.objects.filter(is_in_inventory=True)
        registry = []
        for ing in all_ingredients:
            ing_display = f"{ing.brand} {ing.name}" if ing.brand else ing.name
            registry.append(f"{ing_display} ({ing.get_ingredient_type_display()}, {ing.category.title() if ing.category else 'Misc'}, Intensity: {ing.intensity}/5)")
        inventory_context = "\n".join(registry)

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
                exclude=exclude,
                retry_note=retry_note
            )
            
            suggested_data = raw_suggestion
            
            if suggested_data:
                if isinstance(suggested_data, dict):
                    suggestions_list = suggested_data.get('suggestions', [])
                    rebalancing = suggested_data.get('rebalancing', {})
                    seal_recommended = suggested_data.get('seal_recommended', False)
                    seal_resonance = suggested_data.get('seal_resonance', 0)
                    reasoning = suggested_data.get('reasoning', '')
                else:
                    suggestions_list = suggested_data
                    rebalancing = {}
                    seal_recommended = False
                    seal_resonance = 0
                    reasoning = ''

                enriched: List[Dict[str, Any]] = []
                inventory_items = list(Ingredient.objects.filter(is_in_inventory=True))
                
                for item in suggestions_list:
                    ing_name = item.get('name', '').strip().lower()
                    if not ing_name: continue
                    
                    target_obj = None
                    # Tier 1: Exact Match
                    for inv in inventory_items:
                        inv_full = f"{inv.brand} {inv.name}" if inv.brand else inv.name
                        if inv_full.lower() == ing_name or inv.name.lower() == ing_name:
                            target_obj = inv
                            break
                    
                    # Tier 2: Partial Match
                    if not target_obj:
                        for inv in inventory_items:
                            inv_full = f"{inv.brand} {inv.name}" if inv.brand else inv.name
                            if ing_name in inv_full.lower() or inv_full.lower() in ing_name or ing_name in inv.name.lower() or inv.name.lower() in ing_name:
                                target_obj = inv
                                break
                                
                    if target_obj:
                        intensity_delta = 0
                        if ingredients and ingredients[0] != "NONE - Initial Synthesis":
                            baseline_name = ingredients[0].strip().lower()
                            first_ing = next((inv for inv in inventory_items if inv.name.lower() == baseline_name), None)
                            if not first_ing:
                                first_ing = Ingredient.objects.filter(name__iexact=ingredients[0]).first()
                            
                            base_intensity = first_ing.intensity if first_ing else 3
                            intensity_delta = abs(target_obj.intensity - base_intensity)
                        
                        resonance = 85 + (max(0, 3 - intensity_delta) * 4) + random.uniform(0.1, 2.5)
                        
                        multibrand_names = get_multibrand_names_in_inventory()
                        enriched.append({
                            'id': target_obj.id,
                            'name': get_display_name(target_obj, multibrand_names),
                            'category': target_obj.category,
                            'intensity': target_obj.intensity,
                            'sweetness': target_obj.sweetness,
                            'acidity': target_obj.acidity,
                            'bitterness': target_obj.bitterness,
                            'complexity': target_obj.complexity,
                            'base_suitability': target_obj.base_suitability,
                            'accent_suitability': target_obj.accent_suitability,
                            'resonance': round(min(resonance, 99.8), 1),
                            'reason': item.get('reason', 'Molecular Affinity Match'),
                            'amount': item.get('amount'),
                            'profile': item.get('profile', None)
                        })
                
                if enriched:
                    logger.info(f"AISuggestion - Info - Successfully fetched {len(enriched)} suggestions on attempt {attempt+1}")
                    return JsonResponse({
                        'status': 'success', 
                        'suggestions': enriched,
                        'rebalancing': rebalancing,
                        'seal_recommended': seal_recommended,
                        'seal_resonance': seal_resonance,
                        'reasoning': reasoning
                    })
            
            retry_note = "Your last synthesis signal was unparseable. Adhere strictly to the JSON array format using the Inventory Registry's exact names. [NO MARKDOWN]"

        if not raw_suggestion or not raw_suggestion.strip():
            raw_suggestion = "System Failure: The Laboratory substrate returned an empty synthesis signal. Please try again."
            
        logger.warning("AISuggestion - Warning - Failed to get structured suggestions; returning raw text fallback.")
        return JsonResponse({'status': 'success', 'suggestion': raw_suggestion})
    except Exception as e:
        logger.error(f"AISuggestion - Error - Autonomous Suggestion Failed: {e}", exc_info=True)
        return JsonResponse({'error': f"Autonomous Suggestion Failed: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ai_synthesize_api(request: HttpRequest) -> JsonResponse:
    """Generate a flavor synthesis report for a finalized compound."""
    try:
        data = json.loads(request.body)
        ingredients = data.get('ingredients', [])
        drink_type = data.get('drink_type', 'SODA')
        
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


@csrf_exempt
@require_http_methods(["POST"])
def ai_bulk_analyze_api(request: HttpRequest) -> JsonResponse:
    """Perform a batch synthesis of flavor profiles for all reagents in inventory."""
    if not request.user.is_staff:
        logger.warning(f"AIBulkAnalysis - Warning - Unauthorized API attempt to bulk analyze by {request.user}")
        return JsonResponse({'error': 'Staff authentication required.'}, status=403)
        
    try:
        targets = Ingredient.objects.filter(is_in_inventory=True)
        
        if not targets.exists():
            return JsonResponse({'status': 'complete', 'message': 'No inventory reagents found to synthesize.'})
            
        target_list = list(targets)
        batch_size = 15
        total_analyzed = 0
        
        for i in range(0, len(target_list), batch_size):
            batch = target_list[i : i + batch_size]
            batch_data = [{'name': f"{t.brand} {t.name}" if t.brand else t.name, 'description': t.description or ''} for t in batch]
            
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
                        match.ai_notes = res.get('ai_notes', match.ai_notes)
                        match.save()
                        total_analyzed += 1
                        
        logger.info(f"AIBulkAnalysis - Info - Bulk analysis complete. {total_analyzed} reagents synchronized.")
        return JsonResponse({
            'status': 'success', 
            'message': f'Bulk analysis complete. {total_analyzed} reagents synchronized.'
        })
    except Exception as e:
        logger.error(f"AIBulkAnalysis - Error - Bulk Synthesis Failure: {e}", exc_info=True)
        return JsonResponse({'error': f"Bulk Synthesis Failure: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def random_pairing_api(request: HttpRequest) -> JsonResponse:
    """Generate a 3-ingredient combination, prioritizing AI-driven autonomous synthesis."""
    try:
        data = json.loads(request.body)
        drink_type = data.get('drink_type', 'SODA')
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
            inventory_context = [
                f"{i.name} (Category: {i.category}, Type: {i.get_ingredient_type_display()})"
                for i in all_compatible
            ]
            
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
            
            base_types = ['SODA_SYRUP', 'COFFEE_BEAN']
            potential_bases = all_compatible.filter(ingredient_type__in=base_types)
            
            if potential_bases.exists():
                selection.append({'obj': random.choice(list(potential_bases)), 'amount': None})
            
            if drink_type == 'COFFEE' and target_count >= 3:
                additives = all_compatible.filter(ingredient_type='ADDITIVE').exclude(id__in=[i['obj'].id for i in selection])
                if additives.exists():
                    target_additive = random.choice(list(additives))
                    
                    remaining_reagents = list(all_compatible.exclude(id__in=[i['obj'].id for i in selection]).exclude(id=target_additive.id))
                    random.shuffle(remaining_reagents)
                    
                    while len(selection) < (target_count - 1) and remaining_reagents:
                        selection.append({'obj': remaining_reagents.pop(), 'amount': None})
                    
                    selection.append({'obj': target_additive, 'amount': None})
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
            
        multibrand_names = get_multibrand_names_in_inventory()
        result = []
        for item in selection:
            ing = item['obj']
            result.append({
                'id': ing.id,
                'name': get_display_name(ing, multibrand_names),
                'category': ing.category,
                'intensity': ing.intensity,
                'sweetness': ing.sweetness,
                'acidity': ing.acidity,
                'bitterness': ing.bitterness,
                'complexity': ing.complexity,
                'base_suitability': ing.base_suitability,
                'accent_suitability': ing.accent_suitability,
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
