"""Views for Soda Mixer flavors and recipes."""

from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta
from django.core import serializers
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import user_passes_test
import json
import requests
import traceback
import random
from django.contrib.auth import login, logout, authenticate
from django.db import IntegrityError
from django.contrib import messages

from .models import Ingredient, Recipe, RecipeIngredient, MixHistory, MixHistoryIngredient, RecipeCategory, SystemConfiguration, LLMProvider
from .recommendations import (
    get_recommendation, get_tiered_recommendation, calculate_recipe_stats,
    generate_recipe_name, suggest_categories
)
from .ai_service import AIAssistant


def home(request):
    """Home page with ingredient mixer and Hall of Fame stats."""
    ingredients = Ingredient.objects.filter(is_in_inventory=True)

    # Hall of Fame stats by theme
    stats_by_theme = {}
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


def ingredient_list(request):
    """List all available ingredients."""
    category = request.GET.get('category')
    ingredients = Ingredient.objects.all().order_by('category', 'name')
    
    if category:
        ingredients = ingredients.filter(category=category)
        
    used_categories = Ingredient.objects.values_list('category', flat=True).distinct().order_by('category')
    # Deduplicate after normalization (handles existing mixed-case DB entries)
    seen = {}
    for c in used_categories:
        key = c.strip().lower()
        if key not in seen:
            seen[key] = c.strip().title()
    categories = sorted(seen.items(), key=lambda x: x[0])

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


@require_http_methods(["POST"])
def add_ingredient(request):
    """Add a new ingredient from the frontend modal."""
    # We allow any logged-in user or just staff? The user requested staff check for *delete*. 
    # For *add*, standard user/local should be fine, or we can just allow it.
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
        except IntegrityError:
            messages.error(request, f"Registry Conflict: The reagent '{name}' is already indexed in the Laboratory repository.")
    return redirect('ingredient_list')


@require_http_methods(["POST"])
def edit_ingredient(request, pk):
    """Modify an existing ingredient."""
    if not request.user.is_staff:
        # Simplistic authorization fallback matching delete mechanism
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
    except ValueError:
        pass
        
    try:
        ingredient.save()
    except IntegrityError:
        messages.error(request, f"Registry Conflict: The name '{ingredient.name}' is already assigned to another reagent.")
        return redirect('ingredient_list')
        
    return redirect('ingredient_list')


@user_passes_test(lambda u: u.is_staff)
@require_http_methods(["POST"])
def delete_ingredient(request, pk):
    """Delete an ingredient, restricted to staff."""
    ingredient = get_object_or_404(Ingredient, pk=pk)
    ingredient.delete()
    return redirect('ingredient_list')


@user_passes_test(lambda u: u.is_staff)
@require_http_methods(["POST"])
def delete_category(request, pk):
    """Delete a recipe category, restricted to staff."""
    category = get_object_or_404(RecipeCategory, pk=pk)
    category.delete()
    return redirect('ingredient_list')


@csrf_exempt
@require_http_methods(["POST"])
def create_category_api(request):
    """Create a new RecipeCategory via AJAX."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        color = data.get('color', 'bg-secondary')
        if not name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        cat, created = RecipeCategory.objects.get_or_create(name=name, defaults={'color': color})
        return JsonResponse({'status': 'success', 'id': cat.id, 'name': cat.name, 'color': cat.color, 'created': created})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def delete_recipe_category_api(request, pk):
    """Delete a RecipeCategory via AJAX."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        cat = get_object_or_404(RecipeCategory, pk=pk)
        cat.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def delete_ingredient_profile_api(request):
    """Delete an ingredient base profile (category slug) via AJAX.
    Reassigns all ingredients with that profile to 'other'."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        profile = data.get('profile', '').strip().lower()
        if not profile:
            return JsonResponse({'error': 'Profile name required.'}, status=400)
        count = Ingredient.objects.filter(category=profile).update(category='other')
        return JsonResponse({'status': 'success', 'reassigned': count})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def ingredient_detail(request, pk):
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



def recipe_list(request):
    """List all saved recipes, optionally filtered by category."""
    category_id = request.GET.get('category')
    all_categories = RecipeCategory.objects.all().order_by('name')

    # Optimized Archive Fetch with prefetching
    recipes = Recipe.objects.prefetch_related('categories', 'recipe_ingredients__ingredient').all().order_by('-updated_at')
    if category_id:
        recipes = recipes.filter(categories__id=category_id)

    return render(request, 'flavors/recipe_list.html', {
        'recipes': recipes,
        'all_categories': all_categories,
        'active_category_id': int(category_id) if category_id else None,
    })


def recipe_detail(request, pk):
    """Show a single recipe's details."""
    recipe = get_object_or_404(Recipe, pk=pk)
    stats = calculate_recipe_stats(recipe.recipe_ingredients.all())
    all_categories = RecipeCategory.objects.all().order_by('name')

    return render(request, 'flavors/recipe_detail.html', {
        'recipe': recipe,
        'stats': stats,
        'all_categories': all_categories,
    })


def create_recipe(request):
    """Create a new recipe."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        category_ids = request.POST.getlist('categories')
        drink_type = request.POST.get('drink_type', 'SODA')

        ingredient_ids = []
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
        )

        if category_ids:
            recipe.categories.set(RecipeCategory.objects.filter(id__in=category_ids))

        for ingredient_id in set(ingredient_ids):
            try:
                amount = float(request.POST.get(f'amount_{ingredient_id}', 1.0))
                notes = request.POST.get(f'notes_{ingredient_id}', '')
                RecipeIngredient.objects.create(
                    recipe=recipe,
                    ingredient_id=ingredient_id,
                    amount=amount,
                    notes=notes
                )
            except (ValueError, ValidationError, IntegrityError):
                pass

        return redirect('recipe_detail', pk=recipe.pk)

    ingredients = Ingredient.objects.all()
    return render(request, 'flavors/create_recipe.html', {
        'ingredients': ingredients,
        'all_categories': RecipeCategory.objects.all(),
    })


@csrf_exempt
@require_http_methods(["POST"])
def delete_history_api(request, pk):
    """Decommission a MixHistory entry."""
    mix = get_object_or_404(MixHistory, pk=pk)
    try:
        mix.delete()
        return JsonResponse({'status': 'success', 'message': 'Archival protocol decommissioned.'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def edit_recipe(request, pk):
    """Edit an existing recipe."""
    recipe = get_object_or_404(Recipe, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        category_ids = request.POST.getlist('categories')

        recipe.name = name
        recipe.description = description
        recipe.drink_type = request.POST.get('drink_type', recipe.drink_type)
        recipe.brew_method = request.POST.get('brew_method', recipe.brew_method)
        recipe.grind_size = request.POST.get('grind_size', recipe.grind_size)
        
        # Numeric coffee fields
        for field in ['water_temp_c', 'brew_time_sec', 'total_water_g']:
            val = request.POST.get(field)
            if val is not None and val.strip() != '':
                try:
                    setattr(recipe, field, float(val))
                except (ValueError, TypeError):
                    setattr(recipe, field, None)
            else:
                setattr(recipe, field, None)
        
        recipe.save()
        recipe.categories.set(RecipeCategory.objects.filter(id__in=category_ids))

        # Handle ingredients - simplified approach for now: clear and re-add 
        # based on 'amount_ID' keys which we'll send from the template.
        recipe.recipe_ingredients.all().delete()
        
        for key, value in request.POST.items():
            if key.startswith('amount_'):
                try:
                    ingredient_id = int(key.replace('amount_', ''))
                    amount = float(value)
                    notes = request.POST.get(f'notes_{ingredient_id}', '')
                    
                    # Capture synthesized profile overrides
                    profile_overrides = {}
                    for field in ['intensity', 'sweetness', 'acidity', 'bitterness']:
                        val = request.POST.get(f'{field}_{ingredient_id}')
                        if val and val.strip().isdigit():
                            profile_overrides[field] = int(val)
                    
                    RecipeIngredient.objects.create(
                        recipe=recipe,
                        ingredient_id=ingredient_id,
                        amount=amount,
                        notes=notes,
                        **profile_overrides
                    )
                except (ValueError, TypeError, Ingredient.DoesNotExist, IntegrityError):
                    continue

        return redirect('recipe_detail', pk=recipe.pk)

    ingredients = Ingredient.objects.all()
    return render(request, 'flavors/edit_recipe.html', {
        'recipe': recipe,
        'ingredients': ingredients,
        'all_categories': RecipeCategory.objects.all(),
    })



def delete_recipe(request, pk):
    """Delete a recipe."""
    if request.method == 'POST':
        recipe = get_object_or_404(Recipe, pk=pk)
        recipe.delete()
        return redirect('recipe_list')

    recipe = get_object_or_404(Recipe, pk=pk)
    return render(request, 'flavors/delete_recipe.html', {'recipe': recipe})


def settings_view(request):
    """Settings page for backups and system management."""
    config = SystemConfiguration.get_config()
    providers = LLMProvider.objects.all().order_by('name')
    return render(request, 'flavors/settings.html', {
        'config': config,
        'providers': providers,
        'provider_types': LLMProvider.PROVIDER_CHOICES
    })


def export_data(request):
    """Export all laboratory data to a JSON dossier."""
    data = {
        'ingredients': serializers.serialize('json', Ingredient.objects.all()),
        'categories': serializers.serialize('json', RecipeCategory.objects.all()),
        'recipes': serializers.serialize('json', Recipe.objects.all()),
        'recipe_ingredients': serializers.serialize('json', RecipeIngredient.objects.all()),
        'mix_history': serializers.serialize('json', MixHistory.objects.all()),
        'mix_history_ingredients': serializers.serialize('json', MixHistoryIngredient.objects.all()),
    }
    
    response = HttpResponse(json.dumps(data), content_type='application/json')
    filename = f"beveragelab_dossier_{timezone.now().strftime('%Y%m%d_%H%M')}.json"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@csrf_exempt
@require_http_methods(["POST"])
def import_data(request):
    """Restore laboratory data from a JSON dossier (Merge by Name)."""
    if 'backup_file' not in request.FILES:
        return JsonResponse({'error': 'No file provided'}, status=400)

    try:
        raw_data = json.load(request.FILES['backup_file'])
        
        # 1. Restore Ingredients (Merge by Name)
        ingredient_map = {} # old_id -> new_object
        for i_data in serializers.deserialize('json', raw_data['ingredients']):
            i = i_data.object
            old_id = i.id
            existing = Ingredient.objects.filter(name=i.name).first()
            if existing:
                ingredient_map[old_id] = existing
            else:
                i.id = None # Force new record
                i.save()
                ingredient_map[old_id] = i

        # 2. Restore Categories (Merge by Name)
        category_map = {}
        for c_data in serializers.deserialize('json', raw_data['categories']):
            c = c_data.object
            old_id = c.id
            existing = RecipeCategory.objects.filter(name=c.name).first()
            if existing:
                category_map[old_id] = existing
            else:
                c.id = None
                c.save()
                category_map[old_id] = c

        # 3. Restore Recipes
        recipe_map = {}
        for r_data in serializers.deserialize('json', raw_data['recipes']):
            r = r_data.object
            old_id = r.id
            r.id = None
            r.save()
            recipe_map[old_id] = r

        # 4. Restore Recipe Ingredients
        for ri_data in serializers.deserialize('json', raw_data['recipe_ingredients']):
            ri = ri_data.object
            if ri.recipe_id in recipe_map and ri.ingredient_id in ingredient_map:
                ri.id = None
                ri.recipe = recipe_map[ri.recipe_id]
                ri.ingredient = ingredient_map[ri.ingredient_id]
                ri.save()

        # 5. Restore Mix History
        mix_map = {}
        for m_data in serializers.deserialize('json', raw_data['mix_history']):
            m = m_data.object
            old_id = m.id
            m.id = None
            if m.promoted_recipe_id and m.promoted_recipe_id in recipe_map:
                m.promoted_recipe = recipe_map[m.promoted_recipe_id]
            m.save()
            mix_map[old_id] = m

        # 6. Restore Mix History Ingredients
        for mhi_data in serializers.deserialize('json', raw_data['mix_history_ingredients']):
            mhi = mhi_data.object
            if mhi.mix_id in mix_map and mhi.ingredient_id in ingredient_map:
                mhi.id = None
                mhi.mix = mix_map[mhi.mix_id]
                mhi.ingredient = ingredient_map[mhi.ingredient_id]
                mhi.save()

        return JsonResponse({'status': 'success', 'message': 'Laboratory dossier integrated successfully'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_settings_api(request):
    """Update global system configuration."""
    try:
        data = json.loads(request.body)
        config = SystemConfiguration.get_config()
        config.mealie_url = data.get('mealie_url', '').strip()
        config.mealie_api_key = data.get('mealie_api_key', '').strip()
        config.save()
        return JsonResponse({'status': 'success', 'message': 'Configuration saved successfully.'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def mix_history_list(request):
    """Show mix history with option to promote entries to recipes."""
    history = MixHistory.objects.prefetch_related('mix_ingredients__ingredient').order_by('-mixed_at')
    all_categories = RecipeCategory.objects.all().order_by('name')
    return render(request, 'flavors/mix_history.html', {
        'history': history,
        'all_categories': all_categories,
    })


# ── API endpoints ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def get_recommendations_api(request):
    """API endpoint for tiered ingredient recommendations."""
    try:
        data = json.loads(request.body)
        ingredient_ids = data.get('ingredient_ids', [])
        experimental = data.get('mode') == 'experimental' or data.get('experimental', False)
        force_type = data.get('force_type') # e.g. 'ADDITIVE'
        drink_type = data.get('drink_type', 'SODA')

        if len(ingredient_ids) == 0:
            result = get_recommendation([], drink_type=drink_type, experimental=experimental, force_type=force_type)
            serialized_recs = [
                {
                    'id': r['ingredient'].id,
                    'name': r['ingredient'].name,
                    'category': r['ingredient'].category,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
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
                    'name': r['ingredient'].name,
                    'category': r['ingredient'].category,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
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
                    'name': r['ingredient'].name,
                    'category': r['ingredient'].category,
                    'intensity': r['ingredient'].intensity,
                    'sweetness': r['ingredient'].sweetness,
                    'acidity': r['ingredient'].acidity,
                    'bitterness': r['ingredient'].bitterness,
                    'complexity': r['ingredient'].complexity,
                    'score': r['score'],
                    'reason': r['reason'],
                    'tier': r.get('tier', 'tertiary')
                } for r in result.get('recommended', [])
            ]

        serialized = {'recommended': serialized_recs, 'recipes': []}
        return JsonResponse(serialized)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def add_recipe_api(request):
    """API endpoint for creating a recipe."""
    try:
        data = json.loads(request.body)

        name = data.get('name', '').strip()
        description = data.get('description', '')
        ingredients = data.get('ingredients', [])
        drink_type = data.get('drink_type', 'SODA')

        if not name:
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

        return JsonResponse({
            'id': recipe.id,
            'name': recipe.name,
            'message': 'Recipe created successfully'
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def toggle_inventory_api(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    try:
        data = json.loads(request.body)
        ingredient.is_in_inventory = data.get('is_in_inventory', True)
        ingredient.save()
        return JsonResponse({'status': 'success', 'is_in_inventory': ingredient.is_in_inventory})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def rate_recipe_api(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    try:
        data = json.loads(request.body)
        rating = data.get('rating', 0)
        if 0 <= rating <= 5:
            recipe.rating = rating
            recipe.save()
            return JsonResponse({'status': 'success', 'rating': recipe.rating})
        return JsonResponse({'error': 'Invalid rating value'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def save_mix_to_history_api(request):
    """Save an ad-hoc mix to history. Returns the history ID."""
    try:
        data = json.loads(request.body)
        ingredients = data.get('ingredients', [])  # [{id, amount}, ...]
        drink_type = data.get('drink_type', 'SODA')

        if not ingredients:
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
            except (ValueError, TypeError):
                continue

        return JsonResponse({'status': 'saved', 'mix_id': mix.id})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def promote_mix_to_recipe_api(request, pk):
    """Promote a MixHistory entry to a saved Recipe."""
    mix = get_object_or_404(MixHistory, pk=pk)
    if mix.promoted_recipe:
        return JsonResponse({'error': 'Already promoted', 'recipe_id': mix.promoted_recipe.id}, status=400)

    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        description = data.get('description', '')
        category_ids = data.get('category_ids', [])

        if not name:
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
            except (ValueError, TypeError):
                pass

        mix.promoted_recipe = recipe
        mix.save()

        return JsonResponse({'status': 'promoted', 'recipe_id': recipe.id})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def generate_name_api(request):
    """Return a suggested recipe name for a list of ingredient IDs."""
    try:
        data = json.loads(request.body)
        ingredient_ids = data.get('ingredient_ids', [])
        name = generate_recipe_name(ingredient_ids)
        return JsonResponse({'name': name})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def get_category_suggestions_api(request):
    """Return suggested category names and all existing categories."""
    try:
        data = json.loads(request.body)
        ingredient_ids = data.get('ingredient_ids', [])
        suggested_names = suggest_categories(ingredient_ids)
        existing = list(RecipeCategory.objects.all().values('id', 'name', 'color'))
        return JsonResponse({'suggested': suggested_names, 'existing': existing})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def create_category_api(request):
    """Create a new RecipeCategory."""
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        color = data.get('color', 'bg-secondary')

        if not name:
            return JsonResponse({'error': 'Name required'}, status=400)

        cat, created = RecipeCategory.objects.get_or_create(
            name=name,
            defaults={'color': color}
        )
        return JsonResponse({
            'id': cat.id,
            'name': cat.name,
            'color': cat.color,
            'created': created
        }, status=201 if created else 200)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def update_recipe_categories_api(request, pk):
    """Set category list for a recipe."""
    recipe = get_object_or_404(Recipe, pk=pk)
    try:
        data = json.loads(request.body)
        category_ids = data.get('category_ids', [])
        recipe.categories.set(RecipeCategory.objects.filter(id__in=category_ids))
        return JsonResponse({'status': 'updated'})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def export_recipe_to_mealie_api(request, pk):
    """Push a local recipe to a configured Mealie instance."""
    recipe = get_object_or_404(Recipe, pk=pk)
    config = SystemConfiguration.get_config()

    if not config.mealie_url or not config.mealie_api_key:
        return JsonResponse({'error': 'Mealie configuration is incomplete. Update settings in System Protocols.'}, status=400)

    url = config.mealie_url.rstrip('/') + '/api/recipes'
    headers = {
        'Authorization': f'Bearer {config.mealie_api_key}',
        'Content-Type': 'application/json'
    }

    # Construct description including Lab data
    lab_description = recipe.description or ""
    lab_description += "\n\n### Beverage Laboratory Telemetry\n"
    lab_description += f"- **Synthesis Type**: {recipe.get_drink_type_display()}\n"
    if recipe.brew_method:
        lab_description += f"- **Method**: {recipe.get_brew_method_display()}\n"
    
    import uuid
    mealie_ingredients = []
    for ring in recipe.recipe_ingredients.all():
        unit = "oz" if recipe.drink_type == "SLUSHIE" else ("g" if recipe.drink_type == "COFFEE" else "ml")
        ing_full_name = ring.ingredient.name
        amount = float(ring.amount)
        
        display_text = f"{amount} {unit} {ing_full_name}"
        if ring.notes:
            display_text += f" ({ring.notes})"
        
        # Absolute minimum viable payload for Mealie v1.x
        # OMITTING `unit`, `food`, `quantity`, etc. prevents Pydantic TypeErrors on their backend.
        # However, `title` MUST be present for the ingredient to actually appear in the UI cards!
        mealie_ingredients.append({
            "referenceId": str(uuid.uuid4()),
            "note": display_text,
            "title": ing_full_name,
            "display": display_text
        })

    # Mealie creation often requires at least one instruction step to render successfully
    # Injecting unique 'id' UUIDs to satisfy strict Mealie parsing requirements
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
        # Phase 1: Initialize Recipe Shell
        init_payload = {"name": payload['name']}
        print(f"📦 MEALIE EXPORT (Phase 1): Initializing Shell at {url}")
        
        response = requests.post(url, json=init_payload, headers=headers, timeout=15, allow_redirects=False)
        
        # Hack to preserve POST during HTTP -> HTTPS 301/302 proxy redirects
        if response.status_code in [301, 302, 307, 308]:
            new_url = response.headers.get('Location')
            if new_url:
                print(f"🔄 MEALIE EXPORT: Intercepted proxy redirect. Following POST to: {new_url}")
                url = new_url # update base url for Phase 2
                response = requests.post(url, json=init_payload, headers=headers, timeout=15, allow_redirects=False)

        if response.status_code not in [200, 201]:
             print(f"⚠️  WARNING: Mealie Initialization Failed! Response: {response.text}")
             return JsonResponse({'error': f'Mealie rejected the initialization (HTTP {response.status_code}): {response.text}'}, status=502)

        # Extract Slug
        recipe_data = response.json()
        
        slug = None
        if isinstance(recipe_data, dict):
            slug = recipe_data.get('slug') or recipe_data.get('id')
        elif isinstance(recipe_data, str):
            slug = recipe_data

        if not slug:
             print(f"⚠️  WARNING: Mealie returned success without a slug. Response: {recipe_data}")
             return JsonResponse({'error': 'Mealie successfully initialized but failed to return a valid slug/id.'}, status=502)

        # Phase 2: Inject Molecular Data
        patch_url = f"{url.rstrip('/')}/{slug}"
        print(f"📦 MEALIE EXPORT (Phase 2): Injecting data into {patch_url}")
        
        patch_response = requests.patch(patch_url, json=payload, headers=headers, timeout=15)
        
        if patch_response.status_code in [200, 201]:
             print(f"📡 MEALIE RESPONSE: HTTP {patch_response.status_code} - Data Synchronized!")
             return JsonResponse({'status': 'success', 'message': 'Recipe successfully pushed and enriched in Mealie!'})
        else:
             print(f"⚠️  WARNING: Mealie Data Injection Failed! Response: {patch_response.text}")
             return JsonResponse({'error': f'Mealie rejected the data injection (HTTP {patch_response.status_code}): {patch_response.text}'}, status=502)

    except requests.exceptions.RequestException as e:
        print(f"❌ MEALIE CONNECTION ERROR: {str(e)}")
        return JsonResponse({'error': f'Failed to contact Mealie: {str(e)}'}, status=502)



def _get_compatible_categories(category):
    """Get list of categories that pair well with given category."""
    compatibility_map = {
        'citrus': ['berry', 'tropical', 'herbal', 'sweet'],
        'berry': ['citrus', 'tropical', 'herbal', 'sweet'],
        'tropical': ['citrus', 'berry', 'spice', 'herbal'],
        'herbal': ['citrus', 'berry', 'tropical', 'sour'],
        'spice': ['citrus', 'tropical', 'berry'],
        'sweet': ['citrus', 'berry', 'sour', 'herbal'],
        'sour': ['sweet', 'herbal', 'citrus'],
        'artificial': ['citrus', 'berry', 'sweet', 'tropical'],
        'coffee': ['spice', 'sweet', 'herbal'], # Added coffee compatibility
    }
    return compatibility_map.get(category, [])


@csrf_exempt
@require_http_methods(["POST"])
def ai_chat_api(request):
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
        registry = []
        for ing in all_ingredients:
            registry.append(f"{ing.name} ({ing.get_ingredient_type_display()}, {ing.category.title() if ing.category else 'Misc'}, Intensity: {ing.intensity}/5)")
        inventory_context = "\n".join(registry)

        prompt = user_message + lab_context
        
        # Bridge to the streaming generator
        response_generator = AIAssistant.chat_stream(prompt, history=history, context=inventory_context)
        return StreamingHttpResponse(response_generator, content_type='text/event-stream')
        
    except Exception as e:
        print(f"DEBUG: Laboratory Communication Failure: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': f"Laboratory Communication Failure: {str(e)}"}, status=500)




@csrf_exempt
@require_http_methods(["POST"])
def save_llm_provider_api(request):
    """Manage multiple LLM providers (Cloud and Local)."""
    if not request.user.is_staff:
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
        provider.is_enabled = data.get('is_enabled', False)
        provider.save()
        
        # If this is set as default
        if data.get('set_default', False):
            config = SystemConfiguration.get_config()
            config.default_llm_provider = provider
            config.save()
            
            
        return JsonResponse({'status': 'success', 'id': provider.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def delete_llm_provider_api(request, pk):
    """Remove an LLM provider configuration."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    provider = get_object_or_404(LLMProvider, pk=pk)
    provider.delete()
    return JsonResponse({'status': 'success'})


@csrf_exempt
@require_http_methods(["POST"])
def fetch_provider_models_api(request, pk):
    """Fetch available models for a specific AI provider."""
    provider = get_object_or_404(LLMProvider, pk=pk)
    models = AIAssistant.list_models(provider)
    if models:
        return JsonResponse({'status': 'success', 'models': models})
    else:
        return JsonResponse({'status': 'error', 'message': 'Could not fetch models. Check API keys and base URL.'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def discover_provider_models_api(request):
    """Fetch models for unsaved provider credentials."""
    if not request.user.is_staff:
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
            return JsonResponse({'status': 'success', 'models': models})
        else:
            return JsonResponse({'status': 'error', 'message': 'Discovery Protocol: No models found or credentials rejected.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f"Molecular Sync Failed: {str(e)}"}, status=500)


def login_view(request):
    """Render the dedicated laboratory access gate."""
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'flavors/login.html')


@csrf_exempt
@require_http_methods(["POST"])
def login_api(request):
    """AJAX login endpoint for the laboratory."""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({'status': 'success', 'user': user.username})
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid laboratory credentials.'}, status=401)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def logout_api(request):
    """AJAX logout endpoint."""
    logout(request)
    return JsonResponse({'status': 'success'})


@csrf_exempt
@require_http_methods(["POST"])
def ai_suggest_api(request):
    """Get proactive, structured multi-suggestions from the assistant."""
    try:
        data = json.loads(request.body)
        ingredients = data.get('ingredients', [])
        mode = data.get('mode', 'standard')
        exclude = data.get('exclude', []) # For more options
        
        if not ingredients:
            ingredients = ["NONE - Initial Synthesis"]
            
        # Get full inventory registry for AI context
        all_ingredients = Ingredient.objects.filter(is_in_inventory=True)
        registry = [f"{ing.name} ({ing.get_ingredient_type_display()}, {ing.category.title() if ing.category else 'Misc'}, Intensity: {ing.intensity}/5)" for ing in all_ingredients]
        inventory_context = "\n".join(registry)

        # Implementation of 🧪 AI Protocol: Automated Retry & Verification
        # Up to 3 attempts to get structured data (Signal Hardening)
        raw_suggestion = ""
        retry_note = None
        
        for attempt in range(3):
            # On the final attempt, strip persona for brute-force compliance
            if attempt == 2 and not retry_note:
                 retry_note = "CRITICAL DATA MISMATCH: STOP all prose. Provide ONLY the JSON array of ingredients from the registry. [RAW JSON ONLY]"
            
            raw_suggestion = AIAssistant.suggest_autonomous(
                ingredients, mode, 
                inventory=inventory_context, 
                exclude=exclude,
                retry_note=retry_note
            )
            
            # The autonomous engine now returns pre-extracted JSON data
            suggested_data = raw_suggestion
            
            if suggested_data:
                # Extract suggestions array or root object
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

                # Molecular Resonance: Multi-tier fuzzy lookup
                enriched = []
                inventory_items = list(Ingredient.objects.filter(is_in_inventory=True))
                
                for item in suggestions_list:
                    ing_name = item.get('name', '').strip().lower()
                    if not ing_name: continue
                    
                    target_obj = None
                    # Tier 1: Exact Match
                    for inv in inventory_items:
                        if inv.name.lower() == ing_name:
                            target_obj = inv
                            break
                    
                    # Tier 2: Partial Match
                    if not target_obj:
                        for inv in inventory_items:
                            if ing_name in inv.name.lower() or inv.name.lower() in ing_name:
                                target_obj = inv
                                break
                                
                    if target_obj:
                        intensity_delta = 0
                        if ingredients:
                            baseline_name = ingredients[0].strip().lower()
                            first_ing = next((inv for inv in inventory_items if inv.name.lower() == baseline_name), None)
                            if not first_ing:
                                first_ing = Ingredient.objects.filter(name__iexact=ingredients[0]).first()
                            
                            base_intensity = first_ing.intensity if first_ing else 3
                            intensity_delta = abs(target_obj.intensity - base_intensity)
                        
                        resonance = 85 + (max(0, 3 - intensity_delta) * 4) + random.uniform(0.1, 2.5)
                        
                        enriched.append({
                            'id': target_obj.id,
                            'name': target_obj.name,
                            'category': target_obj.category,
                            'intensity': target_obj.intensity,
                            'sweetness': target_obj.sweetness,
                            'acidity': target_obj.acidity,
                            'bitterness': target_obj.bitterness,
                            'complexity': target_obj.complexity,
                            'resonance': round(min(resonance, 99.8), 1),
                            'reason': item.get('reason', 'Molecular Affinity Match'),
                            'amount': item.get('amount'), # Carry over AI-suggested amount
                            'profile': item.get('profile', None)  # Pass synthesized overrides if present
                        })
                
                if enriched:
                    # SUCCESS: Resonance established
                    return JsonResponse({
                        'status': 'success', 
                        'suggestions': enriched,
                        'rebalancing': rebalancing,
                        'seal_recommended': seal_recommended,
                        'seal_resonance': seal_resonance,
                        'reasoning': reasoning
                    })
            
            # Incrementally improve prompt if we failed
            retry_note = "Your last synthesis signal was unparseable. Adhere strictly to the JSON array format using the Inventory Registry's exact names. [NO MARKDOWN]"

        # Final Fallback: If all attempts failed to produce cards
        if not raw_suggestion or not raw_suggestion.strip():
            raw_suggestion = "System Failure: The Laboratory substrate returned an empty synthesis signal. Please try again."
            
        return JsonResponse({'status': 'success', 'suggestion': raw_suggestion})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': f"Autonomous Suggestion Failed: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ai_synthesize_api(request):
    """Generate a flavor synthesis report for a finalized compound."""
    try:
        data = json.loads(request.body)
        ingredients = data.get('ingredients', [])  # list of {name, intensity, category}
        drink_type = data.get('drink_type', 'SODA')
        
        if not ingredients:
            return JsonResponse({'error': 'No ingredients provided.'}, status=400)
        
        summary = AIAssistant.synthesize_flavor_summary(ingredients, drink_type)
        return JsonResponse({'status': 'success', 'summary': summary})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': f"Synthesis Report Failed: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ai_analyze_ingredient_api(request):
    """Use the LLM to synthesize a chemical flavor profile for a new ingredient."""
    try:
        data = json.loads(request.body)
        name = data.get('name')
        description = data.get('description', '')
        
        if not name:
            return JsonResponse({'error': 'Ingredient name required for analysis.'}, status=400)
            
        profile = AIAssistant.analyze_flavor_profile(name, description)
        if profile:
            return JsonResponse({'status': 'success', 'profile': profile})
        else:
            return JsonResponse({'error': 'Chemical analysis failed to yield structured data.'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ai_bulk_analyze_api(request):
    """Perform a batch synthesis of flavor profiles for all reagents in inventory."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Staff authentication required.'}, status=403)
        
    try:
        # 1. Identify reagents needing analysis
        # Analysis targets: Ingredients in inventory currently at total default stats (3,3,3,1,3)
        targets = Ingredient.objects.filter(
            is_in_inventory=True,
            intensity=3, sweetness=3, acidity=3, bitterness=1, complexity=3
        )
        
        if not targets.exists():
            return JsonResponse({'status': 'complete', 'message': 'All inventory reagents are already synthesized.'})
            
        target_list = list(targets)
        batch_size = 15
        total_analyzed = 0
        
        # 2. Process in batches to respect token/latency limits
        for i in range(0, len(target_list), batch_size):
            batch = target_list[i : i + batch_size]
            batch_data = [{'name': t.name, 'description': t.description or ''} for t in batch]
            
            results = AIAssistant.bulk_analyze_flavor_profiles(batch_data)
            
            if results and isinstance(results, list):
                for res in results:
                    ing_name = res.get('name', '').lower()
                    # Fuzzy match to link AI response back to model
                    match = next((t for t in batch if t.name.lower() == ing_name), None)
                    if not match:
                        # Secondary attempt: check if name is contained
                        match = next((t for t in batch if ing_name in t.name.lower() or t.name.lower() in ing_name), None)
                        
                    if match:
                        match.intensity = max(1, min(5, round(res.get('intensity', match.intensity))))
                        match.sweetness = max(1, min(5, round(res.get('sweetness', match.sweetness))))
                        match.acidity = max(1, min(5, round(res.get('acidity', match.acidity))))
                        match.bitterness = max(1, min(5, round(res.get('bitterness', match.bitterness))))
                        match.complexity = max(1, min(5, round(res.get('complexity', match.complexity))))
                        match.save()
                        total_analyzed += 1
                        
        return JsonResponse({
            'status': 'success', 
            'message': f'Bulk analysis complete. {total_analyzed} reagents synchronized.'
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': f"Bulk Synthesis Failure: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def random_pairing_api(request):
    """Generate a 3-ingredient combination, prioritizing AI-driven autonomous synthesis."""
    try:
        data = json.loads(request.body)
        drink_type = data.get('drink_type', 'SODA')
        mode = data.get('mode', 'standard')
        
        # 1. Get compatible ingredients in inventory
        all_compatible = Ingredient.objects.filter(
            is_in_inventory=True,
            compatible_systems__contains=drink_type
        )
        
        if all_compatible.count() < 3:
             return JsonResponse({'error': 'Insufficient reagents in inventory for a random synthesis.'}, status=400)

        selection = []
        design_intent = ""
        
        # 2. Attempt AI Autonomous Synthesis
        status = AIAssistant.check_status()
        if status == 'synchronized':
            # Collect inventory context
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
                    # Try to find the exact or fuzzy match in our compatible list
                    match = next((i for i in all_compatible if i.name.lower() == name), None)
                    if not match:
                        # Fuzzy check
                        match = next((i for i in all_compatible if name in i.name.lower() or i.name.lower() in name), None)
                    
                    if match and match not in [s['obj'] for s in selection]:
                        selection.append({
                            'obj': match,
                            'amount': item.get('amount')
                        })
        
        # 3. Fallback to Programmatic Randomizer if AI failed or provided fewer than required valid items
        target_count = random.randint(2, 4) if drink_type != 'COFFEE' else random.randint(3, 5)
        
        if len(selection) < target_count:
            selection = [] # Clear any partial AI selection
            design_intent = "" 
            
            # Try to pick a base (Soda Syrup or Coffee Bean)
            base_types = ['SODA_SYRUP', 'COFFEE_BEAN']
            potential_bases = all_compatible.filter(ingredient_type__in=base_types)
            
            if potential_bases.exists():
                selection.append({'obj': random.choice(list(potential_bases)), 'amount': None})
            
            # For Coffee, we want to ensure an additive is included if we are doing a longer mix
            if drink_type == 'COFFEE' and target_count >= 3:
                # Reserve the last slot for an ADDITIVE if possible
                additives = all_compatible.filter(ingredient_type='ADDITIVE').exclude(id__in=[i['obj'].id for i in selection])
                if additives.exists():
                    target_additive = random.choice(list(additives))
                    # We'll add this at the end, so we fill up to (target_count - 1) first
                    
                    remaining_reagents = list(all_compatible.exclude(id__in=[i['obj'].id for i in selection]).exclude(id=target_additive.id))
                    random.shuffle(remaining_reagents)
                    
                    while len(selection) < (target_count - 1) and remaining_reagents:
                        selection.append({'obj': remaining_reagents.pop(), 'amount': None})
                    
                    selection.append({'obj': target_additive, 'amount': None})
                else:
                    # No additives, just fill normally
                    remaining_reagents = list(all_compatible.exclude(id__in=[i['obj'].id for i in selection]))
                    random.shuffle(remaining_reagents)
                    while len(selection) < target_count and remaining_reagents:
                        selection.append({'obj': remaining_reagents.pop(), 'amount': None})
            else:
                remaining_reagents = list(all_compatible.exclude(id__in=[i['obj'].id for i in selection]))
                random.shuffle(remaining_reagents)
                
                while len(selection) < target_count and remaining_reagents:
                    selection.append({'obj': remaining_reagents.pop(), 'amount': None})

            # Apply Randomized Ratio Profile for programmatic fallback
            ratio_profile = random.choice(['parity', 'tiered', 'nuanced'])
            for idx, item in enumerate(selection):
                if item['amount'] is not None: continue # Keep AI amount if present
                
                if ratio_profile == 'parity':
                    # 1:1 ratio (roughly, normalized later in frontend or here)
                    item['amount'] = 100.0 if drink_type != 'COFFEE' else 15.0
                elif ratio_profile == 'tiered':
                    # Standard tiered 100/50/25
                    item['amount'] = [100.0, 50.0, 25.0, 15.0][min(idx, 3)] if drink_type != 'COFFEE' else [18.0, 5.0, 2.0, 2.0, 2.0][min(idx, 4)]
                else:
                    # Nuanced: Randomly weighted
                    item['amount'] = random.choice([100.0, 75.0, 50.0, 25.0, 10.0]) if drink_type != 'COFFEE' else random.choice([18.0, 10.0, 5.0, 2.0])
            
        result = []
        for item in selection:
            ing = item['obj']
            result.append({
                'id': ing.id,
                'name': ing.name,
                'category': ing.category,
                'intensity': ing.intensity,
                'sweetness': ing.sweetness,
                'acidity': ing.acidity,
                'bitterness': ing.bitterness,
                'complexity': ing.complexity,
                'amount': item['amount']
            })
            
        return JsonResponse({
            'status': 'success', 
            'ingredients': result,
            'reasoning': design_intent
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
