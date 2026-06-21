"""Ingredient and Category management views."""

import json
import logging
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.db import IntegrityError
from django.contrib import messages

from ..models import Ingredient, RecipeCategory

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def add_ingredient(request: HttpRequest) -> HttpResponse:
    """Add a new ingredient from the frontend modal."""
    name = request.POST.get('name', '').strip()
    brand = request.POST.get('brand', '').strip()
    ingredient_type = request.POST.get('ingredient_type', 'SODA_SYRUP')
    category = request.POST.get('category', 'citrus').strip().lower()
    description = request.POST.get('description', '')
    ai_notes = request.POST.get('ai_notes', '').strip()
    
    intensity = request.POST.get('intensity', 3)
    sweetness = request.POST.get('sweetness', 3)
    acidity = request.POST.get('acidity', 3)
    bitterness = request.POST.get('bitterness', 1)
    complexity = request.POST.get('complexity', 3)
    base_suitability = request.POST.get('base_suitability', 3.0)
    accent_suitability = request.POST.get('accent_suitability', 3.0)
    is_ready_to_drink = request.POST.get('is_ready_to_drink') == 'on'
    is_dry = request.POST.get('is_dry') == 'on'
    
    # Coffee fields
    roast_level = request.POST.get('roast_level', 'MEDIUM')
    is_decaf = request.POST.get('is_decaf') == 'on'
    origin = request.POST.get('origin', '').strip() or None
    roaster = request.POST.get('roaster', '').strip() or None
    process = request.POST.get('process', '').strip() or None
    try:
        body_intensity = int(request.POST.get('body_intensity', 3))
        acidity_score = int(request.POST.get('acidity_score', 3))
        bitterness_score = int(request.POST.get('bitterness_score', 3))
    except ValueError:
        body_intensity = 3
        acidity_score = 3
        bitterness_score = 3
    flavor_notes = request.POST.get('flavor_notes', '').strip()
    
    systems = request.POST.getlist('compatible_systems')
    compatible_systems = ",".join(systems) if systems else "SODA,COFFEE,SLUSHIE"

    if name:
        try:
            Ingredient.objects.create(
                name=name,
                brand=brand,
                ingredient_type=ingredient_type,
                category=category,
                description=description,
                ai_notes=ai_notes,
                intensity=intensity,
                sweetness=sweetness,
                acidity=acidity,
                bitterness=bitterness,
                complexity=complexity,
                base_suitability=base_suitability,
                accent_suitability=accent_suitability,
                compatible_systems=compatible_systems,
                is_ready_to_drink=is_ready_to_drink,
                is_dry=is_dry,
                is_in_inventory=True,
                roast_level=roast_level,
                is_decaf=is_decaf,
                body_intensity=body_intensity,
                acidity_score=acidity_score,
                bitterness_score=bitterness_score,
                flavor_notes=flavor_notes,
                origin=origin,
                roaster=roaster,
                process=process
            )
            logger.info(f"IngredientRegistry - Info - Successfully registered ingredient: {name} ({brand})")
        except IntegrityError:
            logger.warning(f"IngredientRegistry - Warning - Registry Conflict: Reagent '{name}' with brand '{brand}' is already indexed.")
            messages.error(request, f"Registry Conflict: The reagent '{name}' with brand '{brand}' is already indexed in the Laboratory repository.")
    return redirect('ingredient_list')


@require_http_methods(["POST"])
def edit_ingredient(request: HttpRequest, pk: int) -> HttpResponse:
    """Modify an existing ingredient."""
    if not request.user.is_staff:
        logger.warning(f"IngredientRegistry - Warning - Unauthorized attempt to edit ingredient {pk} by {request.user}")
        return redirect('ingredient_list')
        
    ingredient = get_object_or_404(Ingredient, pk=pk)
    ingredient.name = request.POST.get('name', ingredient.name).strip()
    ingredient.brand = request.POST.get('brand', ingredient.brand).strip()
    ingredient.ingredient_type = request.POST.get('ingredient_type', ingredient.ingredient_type)
    
    category = request.POST.get('category', '').strip().lower()
    if category:
        ingredient.category = category
        
    ingredient.description = request.POST.get('description', ingredient.description)
    ingredient.ai_notes = request.POST.get('ai_notes', ingredient.ai_notes)
    ingredient.is_ready_to_drink = request.POST.get('is_ready_to_drink') == 'on'
    ingredient.is_dry = request.POST.get('is_dry') == 'on'
    
    # Coffee fields
    ingredient.roast_level = request.POST.get('roast_level', ingredient.roast_level)
    ingredient.is_decaf = request.POST.get('is_decaf') == 'on'
    if 'origin' in request.POST:
        ingredient.origin = request.POST.get('origin', '').strip() or None
    if 'roaster' in request.POST:
        ingredient.roaster = request.POST.get('roaster', '').strip() or None
    if 'process' in request.POST:
        ingredient.process = request.POST.get('process', '').strip() or None
    try:
        ingredient.body_intensity = int(request.POST.get('body_intensity', ingredient.body_intensity))
        ingredient.acidity_score = int(request.POST.get('acidity_score', ingredient.acidity_score))
        ingredient.bitterness_score = int(request.POST.get('bitterness_score', ingredient.bitterness_score))
    except ValueError:
        pass
    ingredient.flavor_notes = request.POST.get('flavor_notes', ingredient.flavor_notes).strip()
    
    systems = request.POST.getlist('compatible_systems')
    if systems:
        ingredient.compatible_systems = ",".join(systems)
    
    try:
        ingredient.intensity = int(request.POST.get('intensity', ingredient.intensity))
        ingredient.sweetness = int(request.POST.get('sweetness', ingredient.sweetness))
        ingredient.acidity = int(request.POST.get('acidity', ingredient.acidity))
        ingredient.bitterness = int(request.POST.get('bitterness', ingredient.bitterness))
        ingredient.complexity = int(request.POST.get('complexity', ingredient.complexity))
        ingredient.base_suitability = float(request.POST.get('base_suitability', ingredient.base_suitability))
        ingredient.accent_suitability = float(request.POST.get('accent_suitability', ingredient.accent_suitability))
    except ValueError as e:
        logger.warning(f"IngredientRegistry - Warning - Non-numeric stats provided for ingredient {pk}: {e}")
        
    try:
        ingredient.save()
        logger.info(f"IngredientRegistry - Info - Successfully updated ingredient: {ingredient.name} ({ingredient.brand})")
    except IntegrityError:
        logger.warning(f"IngredientRegistry - Warning - Registry Conflict: Name '{ingredient.name}' with brand '{ingredient.brand}' already assigned.")
        messages.error(request, f"Registry Conflict: The name '{ingredient.name}' with brand '{ingredient.brand}' is already assigned to another reagent.")
        return redirect('ingredient_list')
        
    return redirect('ingredient_list')


@user_passes_test(lambda u: u.is_staff)
@require_http_methods(["POST"])
def delete_ingredient(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an ingredient, restricted to staff."""
    ingredient = get_object_or_404(Ingredient, pk=pk)
    name = ingredient.name
    ingredient.delete()
    logger.info(f"IngredientRegistry - Info - Successfully deleted ingredient: {name}")
    return redirect('ingredient_list')


@user_passes_test(lambda u: u.is_staff)
@require_http_methods(["POST"])
def delete_category(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a recipe category, restricted to staff."""
    category = get_object_or_404(RecipeCategory, pk=pk)
    name = category.name
    category.delete()
    logger.info(f"CategoryRegistry - Info - Successfully deleted category: {name}")
    return redirect('ingredient_list')


@csrf_exempt
@require_http_methods(["POST"])
def create_category_api(request: HttpRequest) -> JsonResponse:
    """Create a new RecipeCategory via AJAX."""
    if not request.user.is_staff:
        logger.warning(f"CategoryRegistry - Warning - Unauthorized API attempt to create category by {request.user}")
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        color = data.get('color', 'bg-secondary')
        if not name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        cat, created = RecipeCategory.objects.get_or_create(name=name, defaults={'color': color})
        logger.info(f"CategoryRegistry - Info - API Category created: {name} (created={created})")
        return JsonResponse({'status': 'success', 'id': cat.id, 'name': cat.name, 'color': cat.color, 'created': created})
    except Exception as e:
        logger.error(f"CategoryRegistry - Error - Failed to create category: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def delete_recipe_category_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Delete a RecipeCategory via AJAX."""
    if not request.user.is_staff:
        logger.warning(f"CategoryRegistry - Warning - Unauthorized API attempt to delete category {pk} by {request.user}")
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        cat = get_object_or_404(RecipeCategory, pk=pk)
        name = cat.name
        cat.delete()
        logger.info(f"CategoryRegistry - Info - API Category deleted: {name}")
        return JsonResponse({'status': 'success'})
    except Exception as e:
        logger.error(f"CategoryRegistry - Error - Failed to delete category {pk}: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def delete_ingredient_profile_api(request: HttpRequest) -> JsonResponse:
    """Delete an ingredient base profile (category slug) via AJAX.
    Reassigns all ingredients with that profile to 'other'."""
    if not request.user.is_staff:
        logger.warning(f"IngredientRegistry - Warning - Unauthorized API attempt to delete profile by {request.user}")
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        profile = data.get('profile', '').strip().lower()
        if not profile:
            return JsonResponse({'error': 'Profile name required.'}, status=400)
        count = Ingredient.objects.filter(category=profile).update(category='other')
        logger.info(f"IngredientRegistry - Info - API Reassigned {count} ingredients with profile '{profile}' to 'other'")
        return JsonResponse({'status': 'success', 'reassigned': count})
    except Exception as e:
        logger.error(f"IngredientRegistry - Error - Failed to delete profile: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def toggle_inventory_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Toggle the ingredient inventory status via AJAX."""
    ingredient = get_object_or_404(Ingredient, pk=pk)
    try:
        data = json.loads(request.body)
        ingredient.is_in_inventory = data.get('is_in_inventory', True)
        ingredient.save()
        logger.info(f"InventoryToggle - Info - Toggled inventory for {ingredient.name} to {ingredient.is_in_inventory}")
        return JsonResponse({'status': 'success', 'is_in_inventory': ingredient.is_in_inventory})
    except json.JSONDecodeError as e:
        logger.warning(f"InventoryToggle - Warning - Invalid JSON payload received for {ingredient.name}: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
