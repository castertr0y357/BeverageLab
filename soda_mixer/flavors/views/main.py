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

def home(request: HttpRequest) -> HttpResponse:
    """Home page with ingredient mixer and Hall of Fame stats."""
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

    return render(request, 'flavors/home.html', {
        'ingredients': ingredients,
        'velocity': kitchen_velocity,
        'stats_json': json.dumps(stats_by_theme),
    })


def ingredient_list(request: HttpRequest) -> HttpResponse:
    """List all available ingredients."""
    category = request.GET.get('category')
    ingredients = Ingredient.objects.all().order_by('name')
    
    if category:
        ingredients = ingredients.filter(category=category)
        
    # Calculate multibrand names in the registry
    from django.db.models import Count
    multibrand_qs = Ingredient.objects.values('name').annotate(
        brand_count=Count('brand', distinct=True)
    ).filter(brand_count__gt=1)
    multibrand_names = {item['name'].lower() for item in multibrand_qs}

    ingredients = list(ingredients)
    for ing in ingredients:
        ing.show_brand = ing.name.lower() in multibrand_names

    used_categories = Ingredient.objects.values_list('category', flat=True).distinct().order_by('category')
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
        'all_categories': RecipeCategory.objects.all().order_by('name')
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


def ingredient_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show a single ingredient's details."""
    ingredient = get_object_or_404(Ingredient, pk=pk)

    compatible_cats = _get_compatible_categories(ingredient.category)
    compatible_ingredients = Ingredient.objects.filter(
        category__in=compatible_cats
    ).exclude(pk=ingredient.pk)[:5]

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


def recipe_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show a single recipe's details."""
    recipe = get_object_or_404(Recipe, pk=pk)
    stats = calculate_recipe_stats(recipe.recipe_ingredients.all())
    all_categories = RecipeCategory.objects.all().order_by('name')

    return render(request, 'flavors/recipe_detail.html', {
        'recipe': recipe,
        'stats': stats,
        'all_categories': all_categories,
    })


def mix_history_list(request: HttpRequest) -> HttpResponse:
    """Show mix history with option to promote entries to recipes."""
    history = MixHistory.objects.prefetch_related('mix_ingredients__ingredient').order_by('-mixed_at')
    all_categories = RecipeCategory.objects.all().order_by('name')
    return render(request, 'flavors/mix_history.html', {
        'history': history,
        'all_categories': all_categories,
    })
