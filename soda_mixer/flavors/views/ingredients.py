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
    ingredient_type = request.POST.get('ingredient_type', 'SODA_SYRUP')
    category = request.POST.get('category', 'citrus').strip().lower()
    description = request.POST.get('description', '')
    
    intensity = request.POST.get('intensity', 3)
    sweetness = request.POST.get('sweetness', 3)
    acidity = request.POST.get('acidity', 3)
    bitterness = request.POST.get('bitterness', 1)
    complexity = request.POST.get('complexity', 3)
    
    systems = request.POST.getlist('compatible_systems')
    compatible_systems = ",".join(systems) if systems else "SODA,COFFEE,SLUSHIE"

    if name:
        try:
            Ingredient.objects.create(
                name=name,
                ingredient_type=ingredient_type,
                category=category,
                description=description,
                intensity=intensity,
                sweetness=sweetness,
                acidity=acidity,
                bitterness=bitterness,
                complexity=complexity,
                compatible_systems=compatible_systems,
                is_in_inventory=True
            )
            logger.info(f"IngredientRegistry - Info - Successfully registered ingredient: {name}")
        except IntegrityError:
            logger.warning(f"IngredientRegistry - Warning - Registry Conflict: Reagent '{name}' is already indexed.")
            messages.error(request, f"Registry Conflict: The reagent '{name}' is already indexed in the Laboratory repository.")
    return redirect('ingredient_list')


@require_http_methods(["POST"])
def edit_ingredient(request: HttpRequest, pk: int) -> HttpResponse:
    """Modify an existing ingredient."""
    if not request.user.is_staff:
        logger.warning(f"IngredientRegistry - Warning - Unauthorized attempt to edit ingredient {pk} by {request.user}")
        return redirect('ingredient_list')
        
    ingredient = get_object_or_404(Ingredient, pk=pk)
    ingredient.name = request.POST.get('name', ingredient.name).strip()
    ingredient.ingredient_type = request.POST.get('ingredient_type', ingredient.ingredient_type)
    
    category = request.POST.get('category', '').strip().lower()
    if category:
        ingredient.category = category
        
    ingredient.description = request.POST.get('description', ingredient.description)
    
    systems = request.POST.getlist('compatible_systems')
    if systems:
        ingredient.compatible_systems = ",".join(systems)
    
    try:
        ingredient.intensity = int(request.POST.get('intensity', ingredient.intensity))
        ingredient.sweetness = int(request.POST.get('sweetness', ingredient.sweetness))
        ingredient.acidity = int(request.POST.get('acidity', ingredient.acidity))
        ingredient.bitterness = int(request.POST.get('bitterness', ingredient.bitterness))
        ingredient.complexity = int(request.POST.get('complexity', ingredient.complexity))
    except ValueError as e:
        logger.warning(f"IngredientRegistry - Warning - Non-numeric stats provided for ingredient {pk}: {e}")
        
    try:
        ingredient.save()
        logger.info(f"IngredientRegistry - Info - Successfully updated ingredient: {ingredient.name}")
    except IntegrityError:
        logger.warning(f"IngredientRegistry - Warning - Registry Conflict: Name '{ingredient.name}' already assigned.")
        messages.error(request, f"Registry Conflict: The name '{ingredient.name}' is already assigned to another reagent.")
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
