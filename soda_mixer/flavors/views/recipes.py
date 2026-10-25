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
    """Save or update an ad-hoc mix in history. Returns the history UUID."""
    try:
        data = json.loads(request.body)
        mix_id = data.get('mix_id')
        ingredients = data.get('ingredients', [])  # [{id, amount, is_primary}, ...]
        drink_type = data.get('drink_type', 'SODA').upper()
        if drink_type == 'CRYO':
            drink_type = 'SLUSHIE'

        mix = None
        if mix_id:
            try:
                mix = MixHistory.objects.filter(uuid=mix_id).first()
            except Exception:
                mix = None

        if not mix:
            if not ingredients:
                logger.warning("HistoryMixSave - Warning - No ingredients provided for mixing history.")
                return JsonResponse({'error': 'No ingredients provided'}, status=400)
            mix = MixHistory.objects.create(drink_type=drink_type)

        # Update metadata if present in payload
        if 'name' in data:
            mix.name = str(data.get('name') or '').strip()
        if 'description' in data:
            mix.description = str(data.get('description') or '')
        if 'mixologist_notes' in data:
            mix.mixologist_notes = str(data.get('mixologist_notes') or '')
        if 'profile_description' in data:
            mix.profile_description = str(data.get('profile_description') or '')
        if 'coffee_style' in data:
            mix.coffee_style = data.get('coffee_style')
        if 'coffee_base_type' in data:
            mix.coffee_base_type = data.get('coffee_base_type')
        if 'drink_size_oz' in data and data.get('drink_size_oz') is not None:
            try:
                mix.drink_size_oz = float(data.get('drink_size_oz'))
            except (ValueError, TypeError):
                pass
        if 'sweetness_style' in data:
            mix.sweetness_style = data.get('sweetness_style')
        if 'bottle_scale' in data and data.get('bottle_scale') is not None:
            try:
                mix.bottle_scale = float(data.get('bottle_scale'))
            except (ValueError, TypeError):
                pass
        mix.save()

        # If ingredients were passed, synchronize them
        if ingredients:
            # Clear existing mix ingredients on update
            mix.mix_ingredients.all().delete()
            for item in ingredients:
                try:
                    raw_id = item.get('id')
                    if not raw_id:
                        continue
                    
                    ingredient_id = int(raw_id)
                    amount = float(item.get('amount', 1.0))
                    is_primary = bool(item.get('is_primary', False))
                    
                    # Extract synthesized profile overrides if provided
                    profile = item.get('profile', {})
                    intensity = profile.get('intensity') if profile else item.get('intensity')
                    sweetness = profile.get('sweetness') if profile else item.get('sweetness')
                    acidity = profile.get('acidity') if profile else item.get('acidity')
                    bitterness = profile.get('bitterness') if profile else item.get('bitterness')
                    
                    target_ing = Ingredient.objects.filter(id=ingredient_id).first()
                    if target_ing:
                        MixHistoryIngredient.objects.create(
                            mix=mix,
                            ingredient=target_ing,
                            amount=amount,
                            is_primary=is_primary,
                            intensity=intensity,
                            sweetness=sweetness,
                            acidity=acidity,
                            bitterness=bitterness
                        )
                except (ValueError, TypeError) as e:
                    logger.error(f"HistoryMixSave - Error - Failed to attach ingredient {item} to history mix: {e}")
                    continue

        logger.info(f"HistoryMixSave - Info - Successfully saved/updated history mix UUID: {mix.uuid}")
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

        recipe_uuid = str(recipe.uuid)
        mix_uuid = mix.uuid
        mix.delete(force=True)

        logger.info(f"HistoryMixPromotion - Info - Promoted mix UUID {mix_uuid} to recipe '{recipe.name}' (UUID: {recipe_uuid}) and scrubbed from history")
        return JsonResponse({'status': 'promoted', 'recipe_id': recipe_uuid})
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
