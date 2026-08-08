"""Recipe and formula management views."""

import json
import logging
import requests
import uuid
from typing import Dict, Any, List, Callable

from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse, JsonResponse

from ..models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, SystemConfiguration, MixHistory, MixHistoryIngredient
from ..tasks_registry import submit_task

logger = logging.getLogger(__name__)


def create_recipe(request: HttpRequest) -> HttpResponse:
    """Create a new recipe."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        category_ids = request.POST.getlist('categories')
        drink_type = request.POST.get('drink_type', 'SODA').upper()

        ingredient_ids: List[str] = []
        for key, value in request.POST.items():
            if key.startswith('amount_'):
                ingredient_id = key.replace('amount_', '')
                ingredient_ids.append(ingredient_id)
            elif key == 'ingredients':
                ingredient_ids.extend(request.POST.getlist('ingredients'))
            elif key.startswith('ingredient_'):
                ingredient_id = key.replace('ingredient_', '')
                ingredient_ids.append(ingredient_id)

        if not name:
            logger.warning("RecipeCreation - Warning - Name field is empty during recipe creation.")
            return render(request, 'flavors/create_recipe.html', {
                'error': 'Recipe name is required',
                'all_categories': RecipeCategory.objects.all(),
            })

        recipe = Recipe.objects.create(
            name=name, 
            description=description,
            drink_type=drink_type,
            brew_method=request.POST.get('brew_method'),
            grind_size=request.POST.get('grind_size'),
            water_temp_c=request.POST.get('water_temp_c') or None,
            brew_time_sec=request.POST.get('brew_time_sec') or None,
            total_water_g=request.POST.get('total_water_g') or None,
            # Coffee drink format fields (only meaningful when drink_type == 'COFFEE')
            coffee_style=request.POST.get('coffee_style') or None,
            coffee_base_type=request.POST.get('coffee_base_type') or None,
            drink_size_oz=float(request.POST.get('drink_size_oz')) if request.POST.get('drink_size_oz') else None,
        )

        if category_ids:
            recipe.categories.set(RecipeCategory.objects.filter(id__in=category_ids))

        for ingredient_id in set(ingredient_ids):
            try:
                amount = float(request.POST.get(f'amount_{ingredient_id}', 1.0))
                notes = request.POST.get(f'notes_{ingredient_id}', '')
                is_primary = request.POST.get(f'is_primary_{ingredient_id}') == 'true'
                RecipeIngredient.objects.create(
                    recipe=recipe,
                    ingredient_id=int(ingredient_id),
                    amount=amount,
                    notes=notes,
                    is_primary=is_primary
                )
            except (ValueError, ValidationError, IntegrityError) as e:
                logger.error(f"RecipeCreation - Error - Failed to attach ingredient {ingredient_id} to recipe {recipe.id}: {e}")

        source_mix_id = request.POST.get('source_mix_id')
        if source_mix_id:
            try:
                mix = MixHistory.objects.get(uuid=source_mix_id)
                mix.delete()
                logger.info(f"RecipeCreation - Info - Deleted source mix {source_mix_id} from archives")
            except MixHistory.DoesNotExist:
                pass

        logger.info(f"RecipeCreation - Info - Successfully created recipe {recipe.name} (ID: {recipe.id})")
        return redirect('recipe_detail', uuid=recipe.uuid)

    ingredients = Ingredient.objects.all()
    return render(request, 'flavors/create_recipe.html', {
        'ingredients': ingredients,
        'all_categories': RecipeCategory.objects.all(),
    })


def edit_recipe(request: HttpRequest, uuid: str) -> HttpResponse:
    """Edit an existing recipe."""
    recipe = get_object_or_404(Recipe, uuid=uuid)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        category_ids = request.POST.getlist('categories')

        recipe.name = name
        recipe.description = description
        drink_type = request.POST.get('drink_type', recipe.drink_type)
        recipe.drink_type = drink_type
        recipe.brew_method = request.POST.get('brew_method', recipe.brew_method)
        recipe.grind_size = request.POST.get('grind_size', recipe.grind_size)
        
        # Numeric coffee fields
        for field in ['water_temp_c', 'brew_time_sec', 'total_water_g']:
            val = request.POST.get(field)
            if val is not None and val.strip() != '':
                try:
                    setattr(recipe, field, float(val))
                except (ValueError, TypeError) as e:
                    logger.warning(f"RecipeEdit - Warning - Non-numeric value for field '{field}' in recipe {uuid}: {e}")
                    setattr(recipe, field, None)
            else:
                setattr(recipe, field, None)
        
        recipe.save()
        recipe.categories.set(RecipeCategory.objects.filter(id__in=category_ids))

        # Handle ingredients - clear and re-add
        recipe.recipe_ingredients.all().delete()
        
        for key, value in request.POST.items():
            if key.startswith('amount_'):
                try:
                    ingredient_id = int(key.replace('amount_', ''))
                    amount = float(value)
                    notes = request.POST.get(f'notes_{ingredient_id}', '')
                    is_primary = request.POST.get(f'is_primary_{ingredient_id}') == 'true'
                    
                    # Capture synthesized profile overrides
                    profile_overrides: Dict[str, int] = {}
                    for field in ['intensity', 'sweetness', 'acidity', 'bitterness']:
                        val = request.POST.get(f'{field}_{ingredient_id}')
                        if val and val.strip().isdigit():
                            profile_overrides[field] = int(val)
                    
                    RecipeIngredient.objects.create(
                        recipe=recipe,
                        ingredient_id=ingredient_id,
                        amount=amount,
                        notes=notes,
                        is_primary=is_primary,
                        **profile_overrides
                    )
                except (ValueError, TypeError, Ingredient.DoesNotExist, IntegrityError) as e:
                    logger.error(f"RecipeEdit - Error - Failed to re-associate ingredient {key} for recipe {uuid}: {e}")
                    continue

        logger.info(f"RecipeEdit - Info - Successfully updated recipe {recipe.name} (ID: {recipe.id})")
        return redirect('recipe_detail', uuid=recipe.uuid)

    ingredients = Ingredient.objects.all()
    return render(request, 'flavors/edit_recipe.html', {
        'recipe': recipe,
        'ingredients': ingredients,
        'all_categories': RecipeCategory.objects.all(),
    })


def delete_recipe(request: HttpRequest, uuid: str) -> HttpResponse:
    """Delete a recipe."""
    recipe = get_object_or_404(Recipe, uuid=uuid)
    if request.method == 'POST':
        name = recipe.name
        force = request.POST.get('force') == 'true' or request.GET.get('force') == 'true'
        recipe.delete(force=force)
        logger.info(f"RecipeDeletion - Info - Successfully deleted recipe (force={force}): {name} (UUID: {uuid})")
        return redirect('recipe_list')

    return render(request, 'flavors/delete_recipe.html', {'recipe': recipe})


@csrf_exempt
@require_http_methods(["POST"])
def add_recipe_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for creating a recipe."""
    try:
        data = json.loads(request.body)

        name = data.get('name', '').strip()
        description = data.get('description', '')
        ingredients = data.get('ingredients', [])
        drink_type = data.get('drink_type', 'SODA').upper()

        if not name:
            logger.warning("RecipeCreationAPI - Warning - Name field is empty during API recipe creation.")
            return JsonResponse({'error': 'Recipe name is required'}, status=400)

        recipe = Recipe.objects.create(
            name=name, 
            description=description,
            drink_type=drink_type,
            brew_method=data.get('brew_method'),
            grind_size=data.get('grind_size'),
            water_temp_c=data.get('water_temp_c'),
            brew_time_sec=data.get('brew_time_sec'),
            total_water_g=data.get('total_water_g'),
        )

        for ingredient_data in ingredients:
            ingredient_id = ingredient_data.get('ingredient_id')
            amount = ingredient_data.get('amount', 1.0)
            notes = ingredient_data.get('notes', '')

            if ingredient_id:
                try:
                    RecipeIngredient.objects.create(
                        recipe=recipe,
                        ingredient_id=int(ingredient_id),
                        amount=float(amount),
                        notes=notes,
                        intensity=ingredient_data.get('intensity'),
                        sweetness=ingredient_data.get('sweetness'),
                        acidity=ingredient_data.get('acidity'),
                        bitterness=ingredient_data.get('bitterness')
                    )
                except (ValueError, TypeError, IntegrityError) as e:
                    logger.error(f"RecipeCreationAPI - Error - Failed to attach ingredient {ingredient_id}: {e}")

        logger.info(f"RecipeCreationAPI - Info - API recipe created: {recipe.name} (ID: {recipe.id})")
        return JsonResponse({
            'id': recipe.id,
            'uuid': str(recipe.uuid),
            'name': recipe.name,
            'message': 'Recipe created successfully'
        }, status=201)

    except json.JSONDecodeError as e:
        logger.warning(f"RecipeCreationAPI - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def rate_recipe_api(request: HttpRequest, uuid: str) -> JsonResponse:
    """Rate a recipe via AJAX."""
    recipe = get_object_or_404(Recipe, uuid=uuid)
    try:
        data = json.loads(request.body)
        rating = data.get('rating', 0)
        if 0 <= rating <= 5:
            recipe.rating = rating
            recipe.save()
            logger.info(f"RecipeRating - Info - Rated recipe '{recipe.name}' (ID: {recipe.id}) with {rating} stars")
            return JsonResponse({'status': 'success', 'rating': recipe.rating})
        logger.warning(f"RecipeRating - Warning - Invalid rating value {rating} for recipe {recipe.id}")
        return JsonResponse({'error': 'Invalid rating value'}, status=400)
    except json.JSONDecodeError as e:
        logger.warning(f"RecipeRating - Warning - Invalid JSON payload for recipe {recipe.id}: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def update_recipe_categories_api(request: HttpRequest, uuid: str) -> JsonResponse:
    """Set category list for a recipe."""
    recipe = get_object_or_404(Recipe, uuid=uuid)
    try:
        data = json.loads(request.body)
        category_ids = data.get('category_ids', [])
        recipe.categories.set(RecipeCategory.objects.filter(id__in=category_ids))
        logger.info(f"RecipeCategoryUpdate - Info - Updated categories for recipe '{recipe.name}' (ID: {recipe.id})")
        return JsonResponse({'status': 'updated'})
    except json.JSONDecodeError as e:
        logger.warning(f"RecipeCategoryUpdate - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def save_mix_to_history_api(request: HttpRequest) -> JsonResponse:
    """Save an ad-hoc mix to history. Returns the history ID."""
    try:
        data = json.loads(request.body)
        ingredients = data.get('ingredients', [])  # [{id, amount}, ...]
        drink_type = data.get('drink_type', 'SODA').upper()
        if drink_type == 'CRYO':
            drink_type = 'SLUSHIE'

        if not ingredients:
            logger.warning("HistoryMixSave - Warning - No ingredients provided for mixing history.")
            return JsonResponse({'error': 'No ingredients provided'}, status=400)

        mix = MixHistory.objects.create(drink_type=drink_type)
        for item in ingredients:
            try:
                raw_id = item.get('id')
                if not raw_id:
                    continue
                
                ingredient_id = int(raw_id)
                amount = float(item.get('amount', 1.0))
                
                # Extract synthesized profile overrides if provided
                profile = item.get('profile', {})
                intensity = profile.get('intensity') if profile else item.get('intensity')
                sweetness = profile.get('sweetness') if profile else item.get('sweetness')
                acidity = profile.get('acidity') if profile else item.get('acidity')
                bitterness = profile.get('bitterness') if profile else item.get('bitterness')
                
                # Verify ingredient existence to prevent broken relations
                target_ing = Ingredient.objects.filter(id=ingredient_id).first()
                if target_ing:
                    MixHistoryIngredient.objects.create(
                        mix=mix,
                        ingredient=target_ing,
                        amount=amount,
                        intensity=intensity,
                        sweetness=sweetness,
                        acidity=acidity,
                        bitterness=bitterness
                    )
            except (ValueError, TypeError) as e:
                logger.error(f"HistoryMixSave - Error - Failed to attach ingredient {item} to history mix: {e}")
                continue

        logger.info(f"HistoryMixSave - Info - Successfully saved history mix UUID: {mix.uuid}")
        return JsonResponse({'status': 'saved', 'mix_id': str(mix.uuid)})
    except json.JSONDecodeError as e:
        logger.warning(f"HistoryMixSave - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def promote_mix_to_recipe_api(request: HttpRequest, uuid: str) -> JsonResponse:
    """Promote a MixHistory entry to a saved Recipe."""
    mix = get_object_or_404(MixHistory, uuid=uuid)
    if mix.promoted_recipe:
        logger.warning(f"HistoryMixPromotion - Warning - Mix history UUID {uuid} has already been promoted to recipe {mix.promoted_recipe.uuid}")
        return JsonResponse({'error': 'Already promoted', 'recipe_id': mix.promoted_recipe.id}, status=400)

    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        description = data.get('description', '')
        category_ids = data.get('category_ids', [])

        if not name:
            logger.warning(f"HistoryMixPromotion - Warning - Name field is empty during promotion of mix ID {pk}")
            return JsonResponse({'error': 'Recipe name is required'}, status=400)

        recipe = Recipe.objects.create(
            name=name, 
            description=description,
            drink_type=mix.drink_type
        )

        for mi in mix.mix_ingredients.all():
            if mi.ingredient:
                RecipeIngredient.objects.create(
                    recipe=recipe,
                    ingredient=mi.ingredient,
                    amount=mi.amount,
                    # Carry over synthesized profile overrides
                    intensity=mi.intensity,
                    sweetness=mi.sweetness,
                    acidity=mi.acidity,
                    bitterness=mi.bitterness
                )
        
        if category_ids:
            try:
                recipe.categories.set(RecipeCategory.objects.filter(id__in=[int(cid) for cid in category_ids if str(cid).isdigit()]))
            except (ValueError, TypeError) as e:
                logger.error(f"HistoryMixPromotion - Error - Failed to apply categories {category_ids} to promoted recipe: {e}")
                pass

        mix.promoted_recipe = recipe
        mix.save()

        logger.info(f"HistoryMixPromotion - Info - Promoted mix UUID {uuid} to recipe '{recipe.name}' (UUID: {recipe.uuid})")
        return JsonResponse({'status': 'promoted', 'recipe_id': str(recipe.uuid)})
    except json.JSONDecodeError as e:
        logger.warning(f"HistoryMixPromotion - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def delete_history_api(request: HttpRequest, uuid: str) -> JsonResponse:
    """Decommission a MixHistory entry."""
    mix = get_object_or_404(MixHistory, uuid=uuid)
    try:
        mix_uuid = mix.uuid
        force = False
        try:
            data = json.loads(request.body)
            force = data.get('force') is True
        except Exception:
            pass
        mix.delete(force=force)
        logger.info(f"HistoryMixDeletion - Info - Successfully decommissioned MixHistory UUID: {mix_uuid} (force={force})")
        return JsonResponse({'status': 'success', 'message': 'Archival protocol decommissioned.'})
    except Exception as e:
        logger.error(f"HistoryMixDeletion - Error - Failed to decommission MixHistory UUID {uuid}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def export_to_mealie_task(update_progress: Callable[..., None], recipe_uuid: uuid.UUID) -> None:
    update_progress(10, status='RUNNING')
    try:
        recipe = Recipe.objects.get(uuid=recipe_uuid)
    except Recipe.DoesNotExist:
        update_progress(100, status='FAILURE', error_msg="Recipe not found.")
        return

    config = SystemConfiguration.get_config()
    if not config.mealie_url or not config.mealie_api_key:
        update_progress(100, status='FAILURE', error_msg="Mealie configuration is incomplete. Update settings in System Protocols.")
        return

    mealie_url = config.mealie_url.rstrip('/')
    from urllib.parse import urlparse
    import socket
    try:
        parsed = urlparse(mealie_url)
        hostname = parsed.hostname
        if hostname:
            ip = socket.gethostbyname(hostname)
            if ip == "169.254.169.254" or ip.startswith("169.254."):
                update_progress(100, status='FAILURE', error_msg="SSRF Block: Link-local and metadata IPs are banned.")
                return
    except Exception as e:
        update_progress(100, status='FAILURE', error_msg=f"Invalid Mealie URL format: {e}")
        return

    url = mealie_url + '/api/recipes'
    headers = {
        'Authorization': f'Bearer {config.mealie_api_key}',
        'Content-Type': 'application/json'
    }

    lab_description = recipe.description or ""
    lab_description += "\n\n### Beverage Laboratory Telemetry\n"
    lab_description += f"- **Synthesis Type**: {recipe.get_drink_type_display()}\n"
    if recipe.brew_method:
        lab_description += f"- **Method**: {recipe.get_brew_method_display()}\n"
    
    mealie_ingredients = []
    for ring in recipe.recipe_ingredients.all():
        is_coffee_bean = (ring.ingredient.physical_state == 'SOLID_EXTRACTABLE') if (ring.ingredient and ring.ingredient.physical_state) else (ring.ingredient and ring.ingredient.ingredient_type == 'COFFEE_BEAN')
        unit = "oz" if recipe.drink_type == "SLUSHIE" else ("g" if recipe.drink_type == "COFFEE" and is_coffee_bean else "ml")
        ing_full_name = ring.ingredient.name
        amount = float(ring.amount)
        
        display_text = f"{amount} {unit} {ing_full_name}"
        if ring.notes:
            display_text += f" ({ring.notes})"
        
        mealie_ingredients.append({
            "referenceId": str(uuid.uuid4()),
            "note": display_text,
            "title": ing_full_name,
            "display": display_text
        })

    instructions = [
        {
            "id": str(uuid.uuid4()), 
            "title": "Preparation", 
            "text": f"Initiate Laboratory Extract protocol for {recipe.get_drink_type_display()}.",
            "ingredientReferences": []
        },
        {
            "id": str(uuid.uuid4()), 
            "title": "Synthesis", 
            "text": "Assemble molecular components according to synthesis specifications.",
            "ingredientReferences": []
        }
    ]

    payload = {
        "name": recipe.name,
        "description": lab_description,
        "recipeYield": "1 serving",
        "recipeIngredient": mealie_ingredients,
        "recipeInstructions": instructions,
    }

    try:
        init_payload = {"name": payload['name']}
        logger.info(f"MealieExport - Info - Phase 1: Initializing Shell at {url}")
        
        response = requests.post(url, json=init_payload, headers=headers, timeout=15, allow_redirects=False)
        
        if response.status_code in [301, 302, 307, 308]:
            new_url = response.headers.get('Location')
            if new_url:
                url = new_url
                response = requests.post(url, json=init_payload, headers=headers, timeout=15, allow_redirects=False)

        if response.status_code not in [200, 201]:
            logger.warning(f"MealieExport - Warning - Mealie Initialization Failed! Response: {response.text}")
            update_progress(100, status='FAILURE', error_msg=f"Mealie rejected initialization (HTTP {response.status_code}): {response.text}")
            return

        recipe_data = response.json()
        slug = None
        if isinstance(recipe_data, dict):
            slug = recipe_data.get('slug') or recipe_data.get('id')
        elif isinstance(recipe_data, str):
            slug = recipe_data

        if not slug:
            update_progress(100, status='FAILURE', error_msg="Mealie successfully initialized but failed to return a valid slug/id.")
            return

        update_progress(50, status='RUNNING')

        patch_url = f"{url.rstrip('/')}/{slug}"
        logger.info(f"MealieExport - Info - Phase 2: Injecting data into {patch_url}")
        
        patch_response = requests.patch(patch_url, json=payload, headers=headers, timeout=15)
        
        if patch_response.status_code in [200, 201]:
            logger.info(f"MealieExport - Info - Mealie Response HTTP {patch_response.status_code} - Data Synchronized!")
            update_progress(100, status='SUCCESS', result_data={'slug': slug, 'mealie_url': f"{mealie_url.rstrip('/')}/recipe/{slug}"})
        else:
            logger.warning(f"MealieExport - Warning - Mealie Data Injection Failed! Response: {patch_response.text}")
            update_progress(100, status='FAILURE', error_msg=f"Mealie rejected the data injection (HTTP {patch_response.status_code}): {patch_response.text}")

    except requests.exceptions.RequestException as e:
        logger.error(f"MealieExport - Error - Mealie Connection Error: {e}")
        update_progress(100, status='FAILURE', error_msg=f"Failed to contact Mealie: {str(e)}")


from typing import Callable

@csrf_exempt
@require_http_methods(["POST"])
def export_recipe_to_mealie_api(request: HttpRequest, uuid: str) -> JsonResponse:
    """Push a local recipe to a configured Mealie instance (asynchronously)."""
    recipe = get_object_or_404(Recipe, uuid=uuid)
    
    import os
    if os.environ.get('MOCK_MODE', 'False').lower() in ('true', '1', 't'):
        logger.info("MealieExport - Info - MOCK_MODE active. Returning mock success response.")
        return JsonResponse({'status': 'success', 'message': 'Recipe successfully pushed and enriched in Mealie! (MOCK_MODE)'})

    task = submit_task("Mealie Recipe Export", export_to_mealie_task, recipe_uuid=recipe.uuid)
    return JsonResponse({'status': 'accepted', 'task_id': str(task.uuid)}, status=202)
