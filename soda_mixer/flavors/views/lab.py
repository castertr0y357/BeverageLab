"""Views for the laboratory environments (MPA)."""

import json
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from ..models import Ingredient

def lab_dispatcher(request: HttpRequest, lab_type: str) -> HttpResponse:
    """Renders the lab with no mode selected, prompting the user to choose one."""
    return lab_view(request, lab_type, mode='select')

def lab_view(request: HttpRequest, lab_type: str, mode: str) -> HttpResponse:
    """Renders the specific lab mode."""
    # Ensure lab_type and mode are valid
    valid_labs = ['soda', 'coffee', 'cryo']
    valid_modes = ['manual', 'quick', 'vibe', 'select']
    
    if lab_type.lower() not in valid_labs or mode.lower() not in valid_modes:
        return redirect('dashboard')
        
    # Get all active ingredients
    ingredients = list(Ingredient.objects.filter(is_in_inventory=True))
    
    # Calculate multibrand names in active inventory
    from django.db.models import Count
    multibrand_qs = Ingredient.objects.filter(is_in_inventory=True).values('name').annotate(
        brand_count=Count('brand', distinct=True)
    ).filter(brand_count__gt=1)
    multibrand_names = {item['name'].lower() for item in multibrand_qs}

    for ing in ingredients:
        ing.show_brand = ing.name.lower() in multibrand_names
        
    ingredient_dicts = [{
        'id': ing.id, 
        'name': ing.name, 
        'category': ing.category,
        'ingredient_type': ing.ingredient_type,
        'physical_state': ing.physical_state,
        'mixology_function': ing.mixology_function,
        'intensity': ing.intensity,
        'sweetness': ing.sweetness,
        'acidity': ing.acidity,
        'bitterness': ing.bitterness
    } for ing in ingredients]
    
    context = {
        'lab_type': lab_type.upper(),
        'mode': mode.lower(),
        'ingredients': ingredients,
        'ingredients_json': json.dumps(ingredient_dicts),
    }
    
    # Render the specific lab mode template
    template_name = f'flavors/lab_{mode}.html'
    return render(request, template_name, context)

import logging
logger = logging.getLogger(__name__)

def synopsis_view(request: HttpRequest) -> HttpResponse:
    """Renders the generic synopsis review page."""
    prefill_data = None
    if request.method == 'POST':
        # When coming from manual or AI builder, frontend posts the selected setup here
        recipe_data_str = request.POST.get('recipe_data')
        if recipe_data_str:
            try:
                prefill_data = json.loads(recipe_data_str)
            except json.JSONDecodeError:
                pass
        else:
            try:
                body = request.body.decode('utf-8')
                if body:
                    prefill_data = json.loads(body)
            except json.JSONDecodeError:
                pass

    context = {
        'prefill_json': json.dumps(prefill_data) if prefill_data else 'null',
    }
    return render(request, 'flavors/synopsis.html', context)
