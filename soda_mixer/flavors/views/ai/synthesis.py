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
from .helpers import *

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
                return f"event: progress\ndata: {json.dumps({'status': 'progress', 'message': msg})}\n\n"

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
            
            import time
            from django.template.loader import render_to_string
            inventory_items = list(Ingredient.objects.filter(is_in_inventory=True))
            multibrand_names = get_multibrand_names_in_inventory()
            enriched = []
            final_data = None
            sanitized_rebalancing = {}
            
            for attempt in range(3):
                retry_note = None
                if attempt == 2:
                     retry_note = "CRITICAL DATA MISMATCH: STOP all prose. Provide ONLY the JSON array of ingredients from the registry. [RAW JSON ONLY]"
                
                try:
                    stream = AIAssistant.suggest_autonomous_stream(
                        ingredients, mode, 
                        drink_type=drink_type,
                        inventory=inventory_context, 
                        exclude=actual_exclude,
                        retry_note=retry_note,
                        force_type=force_type
                    )
                    
                    for chunk in stream:
                        if chunk['type'] == 'suggestion':
                            item = chunk['data']
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
                                for ing_name_active in ingredients:
                                    if ing_name_active and ing_name_active != "NONE - Initial Synthesis":
                                        ing_clean = ing_name_active.strip().lower()
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
                                
                                amount = item.get('amount')
                                if drink_type == 'COFFEE':
                                    amount = sanitize_coffee_amount(target_obj, amount)

                                enriched_item = {
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
                                    'reason': item.get('reason', 'Molecular Affinity Match'),
                                    'amount': amount,
                                    'profile': item.get('profile', None)
                                }
                                enriched.append(enriched_item)
                                
                                card_class = 'border-success border-opacity-25'
                                text_class = 'text-gradient-lab'
                                icon_html = ''
                                if enriched_item['favorite']:
                                    card_class = 'border-favorite glow-favorite'
                                    text_class = 'text-warning'
                                    icon_html = '<i class="bi bi-star-fill text-warning me-1" style="filter: drop-shadow(0 0 5px var(--fizz-amber));"></i>'
                                elif mode == 'experimental':
                                    card_class = 'border-experimental glow-experimental'
                                    text_class = 'text-experimental'
                                    icon_html = '<i class="bi bi-flask me-1"></i>'
                                else:
                                    card_class = 'border-neural glow-neural'
                                    text_class = 'text-neural'
                                    icon_html = '<i class="bi bi-cpu me-1"></i>'

                                html_str = render_to_string('flavors/_recommendation_card.html', {
                                    'card_type': 'ingredient',
                                    'rec': enriched_item,
                                    'card_class': card_class,
                                    'text_class': text_class,
                                    'icon_html': icon_html,
                                    'profile_json': json.dumps(enriched_item.get('profile') or {})
                                })
                                html_str = html_str.replace('\n', '')
                                yield f"event: message\ndata: {html_str}\n\n"
                                
                        elif chunk['type'] == 'complete':
                            final_data = chunk['data']
                            rebalancing_raw = final_data.get('rebalancing', {})
                            
                            if isinstance(rebalancing_raw, list):
                                rebalancing = {item.get('name'): item.get('amount') for item in rebalancing_raw if item.get('name') is not None}
                            else:
                                rebalancing = rebalancing_raw
                            
                            if drink_type == 'COFFEE' and rebalancing:
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
                                            
                                if beans_in_rebal:
                                    total_bean_val = sum(beans_in_rebal.values())
                                    if total_bean_val > 0:
                                        for key, val in beans_in_rebal.items():
                                            sanitized_rebalancing[key] = round((val / total_bean_val) * 18.0, 1)
                                    else:
                                        num_beans = len(beans_in_rebal)
                                        for key in beans_in_rebal:
                                            sanitized_rebalancing[key] = round(18.0 / num_beans, 1)
                                            
                                if dairy_in_rebal:
                                    total_dairy_val = sum(dairy_in_rebal.values())
                                    if total_dairy_val > 0:
                                        for key, val in dairy_in_rebal.items():
                                            sanitized_rebalancing[key] = round((val / total_dairy_val) * 50.0, 1)
                                    else:
                                        num_dairy = len(dairy_in_rebal)
                                        for key in dairy_in_rebal:
                                            sanitized_rebalancing[key] = round(50.0 / num_dairy, 1)
                                            
                                for key, val in other_in_rebal.items():
                                    sanitized_rebalancing[key] = round(val, 1)
                            else:
                                sanitized_rebalancing = rebalancing
                                
                            rebalancing = sanitized_rebalancing
                            
                            if enriched:
                                logger.info(f"AISuggestion - Info - Successfully fetched {len(enriched)} suggestions on attempt {attempt+1}")
                                yield f"event: remove_spinner\ndata: \n\n"
                                yield f"event: json\ndata: {json.dumps({'status': 'success', 'suggestions': enriched, 'rebalancing': rebalancing, 'seal_recommended': final_data.get('seal_recommended', False), 'reasoning': final_data.get('reasoning', '')})}\n\n"
                                return
                            
                            break # Exit chunk loop
                    
                except Exception as e:
                    logger.error(f"AISuggestion - Error - Stream attempt {attempt+1} failed: {e}", exc_info=True)
                    if attempt == 2:
                        raise e

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
            
            enriched = []
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
                    'reason': f"Algorithmic: {item['reason']}",
                    'amount': amount,
                    'profile': None
                })
            
            yield f"event: remove_spinner\ndata: \n\n"
            yield f"event: json\ndata: {json.dumps({'status': 'success', 'suggestions': enriched, 'rebalancing': {}, 'seal_recommended': False,  'reasoning': 'AI suggestions fallback.'})}\n\n"

        response = StreamingHttpResponse(generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    except Exception as e:
        logger.error(f"AISuggestion - Error - Autonomous Suggestion Failed: {e}", exc_info=True)
        def error_generator():
            yield f"event: remove_spinner\ndata: \n\n"
            yield f"event: json\ndata: {json.dumps({'status': 'error', 'message': f'Autonomous Suggestion Failed: {str(e)}'})}\n\n"
        response = StreamingHttpResponse(error_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

def ai_synthesize_api(request: HttpRequest) -> HttpResponse:
    """Generate a flavor synthesis report for a finalized compound (supports streaming)."""
    try:
        if request.method == "POST":
            data = json.loads(request.body)
            ingredients = data.get('ingredients', [])
            drink_type = data.get('drink_type', 'SODA').upper()
            barista_notes = data.get('barista_notes', '')
        else:
            ingredients_str = request.GET.get('ingredients', '[]')
            try:
                ingredients = json.loads(ingredients_str)
            except Exception:
                ingredients = []
            drink_type = request.GET.get('drink_type', 'SODA').upper()
            barista_notes = request.GET.get('barista_notes', '')
        
        if not ingredients:
            return JsonResponse({'error': 'No ingredients provided.'}, status=400)
        
        def sse_generator():
            import time
            stream = AIAssistant.synthesize_flavor_summary_stream(ingredients, drink_type, barista_notes=barista_notes)
            current_event = 'mixologist_notes'
            buffer = ""
            for chunk_json in stream:
                if chunk_json.startswith('data: '):
                    try:
                        data_str = chunk_json[6:].strip()
                        if not data_str or data_str == '[DONE]': continue
                        parsed = json.loads(data_str)
                        if 'chunk' in parsed:
                            chunk_text = parsed['chunk']
                            buffer += chunk_text
                            
                            # Clean up start marker
                            if '[MIXOLOGIST_NOTES]' in buffer:
                                buffer = buffer.replace('[MIXOLOGIST_NOTES]', '')
                                if buffer.startswith('\n'):
                                    buffer = buffer.lstrip('\n')
                                    
                            if '[PROFILE_DESCRIPTION]' in buffer:
                                parts = buffer.split('[PROFILE_DESCRIPTION]')
                                if parts[0]:
                                    c = parts[0].strip('\n').replace('\n', '<br>')
                                    if c:
                                        yield f"event: mixologist_notes\ndata: {c}\n\n"
                                
                                current_event = 'message'
                                buffer = parts[1]
                                if buffer.startswith('\n'):
                                    buffer = buffer.lstrip('\n')
                                
                                if buffer:
                                    c = buffer.replace('\n', '<br>')
                                    yield f"event: {current_event}\ndata: {c}\n\n"
                                    buffer = ""
                            else:
                                last_bracket = buffer.rfind('[')
                                if last_bracket != -1 and current_event == 'mixologist_notes':
                                    safe_part = buffer[:last_bracket]
                                    buffer = buffer[last_bracket:]
                                else:
                                    safe_part = buffer
                                    buffer = ""
                                
                                if safe_part:
                                    c = safe_part.replace('\n', '<br>')
                                    if c:
                                        yield f"event: {current_event}\ndata: {c}\n\n"
                    except:
                        pass
            
            if buffer:
                c = buffer.replace('[MIXOLOGIST_NOTES]', '').replace('\n', '<br>')
                if c:
                    yield f"event: {current_event}\ndata: {c}\n\n"
                    
            yield "event: remove_spinner\ndata: \n\n"
            
        response = StreamingHttpResponse(sse_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
    except Exception as e:
        logger.error(f"SynthesisAPI - Error: {e}", exc_info=True)
        def error_generator():
            yield f"event: message\ndata: <span class='text-danger'>Error: {str(e)}</span>\n\n"
        response = StreamingHttpResponse(error_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response