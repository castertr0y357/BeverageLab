"""Main laboratory display views."""

import json
import logging
from datetime import timedelta
from typing import Dict, Any, List, Tuple

from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg
from django.utils import timezone
from django.http import HttpRequest, HttpResponse

from ..models import Ingredient, Recipe, RecipeCategory, MixHistory
from ..recommendations import calculate_recipe_stats

logger = logging.getLogger(__name__)

def dashboard(request: HttpRequest) -> HttpResponse:
    """Dashboard page with Hall of Fame stats and entry points to the labs."""
    ingredients = list(Ingredient.objects.filter(is_in_inventory=True))

    # Calculate multibrand names in active inventory
    from django.db.models import Count
    multibrand_qs = Ingredient.objects.filter(is_in_inventory=True).values('name').annotate(
        brand_count=Count('brand', distinct=True)
    ).filter(brand_count__gt=1)
    multibrand_names = {item['name'].lower() for item in multibrand_qs}

    for ing in ingredients:
        ing.show_brand = ing.name.lower() in multibrand_names

    # Hall of Fame stats by theme
    stats_by_theme: Dict[str, Dict[str, Any]] = {}
    for theme in ['SODA', 'COFFEE', 'SLUSHIE']:
        try:
            mvp_ingredient = Ingredient.objects.filter(ingredient_usage__recipe__drink_type=theme).annotate(
                recipe_count=Count('ingredient_usage')
            ).order_by('-recipe_count').first()

            top_category = RecipeCategory.objects.filter(recipes__drink_type=theme).annotate(
                avg_rating=Avg('recipes__rating')
            ).filter(avg_rating__isnull=False).order_by('-avg_rating').first()

            signature_mix = Recipe.objects.filter(drink_type=theme).annotate(
                history_count=Count('history_entry')
            ).order_by('-history_count').first()

            stats_by_theme[theme] = {
                'mvp_ingredient': mvp_ingredient.name if mvp_ingredient else '-',
                'top_category': top_category.name if top_category else '-',
                'signature_mix_name': signature_mix.name if signature_mix else '-',
                'signature_mix_url': f'/recipes/{signature_mix.id}/' if signature_mix else None,
            }
        except Exception as e:
            logger.error(f"HallOfFameStats - Error - Failed to calculate stats for theme {theme}: {e}")
            stats_by_theme[theme] = {
                'mvp_ingredient': '-',
                'top_category': '-',
                'signature_mix_name': '-',
                'signature_mix_url': None,
            }

    last_7_days = timezone.now() - timedelta(days=7)
    kitchen_velocity = MixHistory.objects.filter(mixed_at__gte=last_7_days).count()

    return render(request, 'flavors/dashboard.html', {
        'ingredients': ingredients,
        'velocity': kitchen_velocity,
        'stats_json': json.dumps(stats_by_theme),
    })


def ingredient_list(request: HttpRequest) -> HttpResponse:
    """List all available ingredients."""
    category = request.GET.get('category')
    system = request.GET.get('system')
    ingredients = Ingredient.objects.all().order_by('name')
    
    if category:
        ingredients = ingredients.filter(category=category)
        
    if system:
        sys_val = system.upper()
        if sys_val == 'CRYO':
            sys_val = 'SLUSHIE'
        ingredients = ingredients.filter(compatible_systems__icontains=sys_val)
        
    # Calculate multibrand names in the registry
    from django.db.models import Count
    multibrand_qs = Ingredient.objects.values('name').annotate(
        brand_count=Count('brand', distinct=True)
    ).filter(brand_count__gt=1)
    multibrand_names = {item['name'].lower() for item in multibrand_qs}

    ingredients = list(ingredients)
    for ing in ingredients:
        ing.show_brand = ing.name.lower() in multibrand_names

    category_qs = Ingredient.objects.all()
    if system:
        sys_val = system.upper()
        if sys_val == 'CRYO':
            sys_val = 'SLUSHIE'
        category_qs = category_qs.filter(compatible_systems__icontains=sys_val)
    used_categories = category_qs.values_list('category', flat=True).distinct().order_by('category')
    # Deduplicate after normalization (handles existing mixed-case DB entries)
    seen: Dict[str, str] = {}
    for c in used_categories:
        key = c.strip().lower()
        if key not in seen:
            seen[key] = c.strip().title()
    categories: List[Tuple[str, str]] = sorted(seen.items(), key=lambda x: x[0])

    # Include fallback defaults if DB is totally empty
    if not categories:
        categories = [
            ('citrus', 'Citrus'), ('berry', 'Berry'), ('tropical', 'Tropical'),
            ('coffee', 'Coffee Profile')
        ]

    return render(request, 'flavors/ingredient_list.html', {
        'ingredients': ingredients,
        'categories': categories,
        'all_categories': RecipeCategory.objects.all().order_by('name'),
        'current_category': category,
        'current_system': system,
    })



def _get_compatible_categories(category: str) -> List[str]:
    """Get list of categories that pair well with given category."""
    compatibility_map: Dict[str, List[str]] = {
        'citrus': ['berry', 'tropical', 'herbal', 'sweet'],
        'berry': ['citrus', 'tropical', 'herbal', 'sweet'],
        'tropical': ['citrus', 'berry', 'spice', 'herbal'],
        'herbal': ['citrus', 'berry', 'tropical', 'sour'],
        'spice': ['citrus', 'tropical', 'berry'],
        'sweet': ['citrus', 'berry', 'sour', 'herbal'],
        'sour': ['sweet', 'herbal', 'citrus'],
        'artificial': ['citrus', 'berry', 'sweet', 'tropical'],
        'coffee': ['spice', 'sweet', 'herbal'],
    }
    return compatibility_map.get(category, [])


def ingredient_detail(request: HttpRequest, uuid: str) -> HttpResponse:
    """Show a single ingredient's details."""
    ingredient = get_object_or_404(Ingredient, uuid=uuid)

    compatible_cats = _get_compatible_categories(ingredient.category)
    compatible_ingredients = Ingredient.objects.filter(
        category__in=compatible_cats
    ).exclude(id=ingredient.id)[:5]

    return render(request, 'flavors/ingredient_detail.html', {
        'ingredient': ingredient,
        'compatible': compatible_ingredients
    })


def recipe_list(request: HttpRequest) -> HttpResponse:
    """List all saved recipes, optionally filtered and sorted."""
    category_id = request.GET.get('category')
    drink_type = request.GET.get('drink_type')
    sort_by = request.GET.get('sort', '-created_at')

    all_categories = RecipeCategory.objects.all().order_by('name')

    # Optimized Archive Fetch with prefetching
    recipes = Recipe.objects.prefetch_related('categories', 'recipe_ingredients__ingredient').all()
    
    # Filter by category
    if category_id:
        recipes = recipes.filter(categories__id=category_id)
        
    # Filter by drink type
    if drink_type:
        recipes = recipes.filter(drink_type=drink_type)

    # Apply sorting
    valid_sorts = {
        'name': 'name',
        '-name': '-name',
        'created_at': 'created_at',
        '-created_at': '-created_at',
        'updated_at': 'updated_at',
        '-updated_at': '-updated_at',
    }
    sort_field = valid_sorts.get(sort_by, '-created_at')
    recipes = recipes.order_by(sort_field)

    active_cat_id = None
    if category_id:
        try:
            active_cat_id = int(category_id)
        except ValueError:
            pass

    return render(request, 'flavors/recipe_list.html', {
        'recipes': recipes,
        'all_categories': all_categories,
        'active_category_id': active_cat_id,
        'active_drink_type': drink_type,
        'active_sort': sort_by,
    })


def recipe_detail(request: HttpRequest, uuid: str) -> HttpResponse:
    """Show a single recipe's details rendered in the unified synopsis view."""
    recipe = get_object_or_404(Recipe, uuid=uuid)
    
    # Parse description into profile_description and mixologist_notes if present
    full_desc = recipe.description or ""
    profile_desc = full_desc
    mix_notes = ""
    if "AI Mixologist Notes:" in full_desc:
        parts = full_desc.split("AI Mixologist Notes:", 1)
        profile_desc = parts[0].strip()
        mix_notes = parts[1].strip()

    ingredients_payload = []
    for ring in recipe.recipe_ingredients.select_related('ingredient').all():
        if not ring.ingredient:
            continue
        ing = ring.ingredient
        ingredients_payload.append({
            'id': ing.id,
            'name': ing.name,
            'amount': float(ring.amount),
            'unit': 'oz' if recipe.drink_type == 'SLUSHIE' else ('g' if (recipe.drink_type == 'COFFEE' and getattr(ing, 'ingredient_type', None) == 'COFFEE_BEAN') else 'ml'),
            'category': ing.category,
            'type': ing.ingredient_type,
            'ingredient_type': ing.ingredient_type,
            'physical_state': ing.physical_state,
            'mixology_function': ing.mixology_function,
            'is_primary': ring.is_primary,
            'intensity': ring.intensity,
            'sweetness': ring.sweetness,
            'acidity': ring.acidity,
            'bitterness': ring.bitterness,
        })

    prefill_data = {
        'is_saved_recipe': True,
        'skip_ai': True,
        'recipe_uuid': str(recipe.uuid),
        'name': recipe.name,
        'drink_type': recipe.drink_type,
        'coffee_style': recipe.coffee_style.upper() if recipe.coffee_style else 'HOT',
        'coffee_base_type': recipe.coffee_base_type.upper() if recipe.coffee_base_type else 'ESPRESSO',
        'drink_size_oz': recipe.drink_size_oz or 12.0,
        'sweetness_style': getattr(recipe, 'sweetness_style', 'CRAFT') or 'CRAFT',
        'bottle_scale': getattr(recipe, 'bottle_scale', 1.0) or 1.0,
        'profile_description': profile_desc,
        'mixologist_notes': mix_notes,
        'ingredients': ingredients_payload,
    }

    lab_mode = 'coffee' if recipe.drink_type == 'COFFEE' else ('cryo' if recipe.drink_type == 'SLUSHIE' else 'soda')

    return render(request, 'flavors/synopsis.html', {
        'recipe': recipe,
        'is_saved_recipe': True,
        'lab_mode': lab_mode,
        'drink_type': recipe.drink_type,
        'coffee_style': recipe.coffee_style,
        'coffee_base_type': recipe.coffee_base_type,
        'drink_size_oz': recipe.drink_size_oz,
        'prefill_json': json.dumps(prefill_data),
    })


def mix_history_list(request: HttpRequest) -> HttpResponse:
    """Show mix history with option to promote entries to recipes."""
    history = MixHistory.objects.filter(promoted_recipe__isnull=True).prefetch_related('mix_ingredients__ingredient').order_by('-mixed_at')
    all_categories = RecipeCategory.objects.all().order_by('name')
    return render(request, 'flavors/mix_history.html', {
        'history': history,
        'all_categories': all_categories,
    })
