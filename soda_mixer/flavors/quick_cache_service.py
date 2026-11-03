"""Quick Drinks Pre-Generation Cache Service & Unified Draw Engine."""

import logging
import random
import re
import time
from typing import Dict, Any, List, Optional, Set, Tuple, Callable
from django.utils import timezone

from .models import (
    Ingredient, Recipe, RecipeIngredient, MixHistory,
    CachedQuickDrink, QuickDrinkCacheConfiguration
)
from .ai_service import AIAssistant

logger = logging.getLogger(__name__)

# Dynamic bucket targets per (drink_type, ingredient_count)
# Designed to support 5 full cycles of 5 drinks without repeats
BUCKET_TARGETS: Dict[str, Dict[int, int]] = {
    'SODA': {2: 5, 3: 8, 4: 8, 5: 5},
    'SLUSHIE': {2: 5, 3: 8, 4: 8, 5: 5},
    'COFFEE': {3: 8, 4: 8, 5: 5},
}

# Structural terms in Coffee Lab excluded from flavor anchor calculation
COFFEE_STRUCTURAL_TERMS = (
    'bean', 'espresso', 'roast', 'whole milk', 'oat milk',
    'skim milk', 'almond milk', 'soy milk', 'coconut milk'
)


def normalize_drink_type(drink_type: str) -> str:
    dt = (drink_type or 'SODA').strip().upper()
    if dt == 'CRYO':
        return 'SLUSHIE'
    return dt


def is_coffee_structural_ingredient(ing_obj: Optional[Ingredient], raw_name: str = '') -> bool:
    """Return True if an ingredient is a structural Coffee Bean or plain Dairy/Milk base."""
    if ing_obj is not None:
        if ing_obj.physical_state == 'SOLID_EXTRACTABLE' or ing_obj.ingredient_type == 'COFFEE_BEAN':
            return True
        if ing_obj.mixology_function == 'VOLUME_BASE' and ing_obj.physical_state == 'LIQUID':
            return True
        if (ing_obj.category or '').strip().lower() in ('coffee', 'dairy'):
            return True
    name_clean = (ing_obj.name if ing_obj else raw_name).strip().lower()
    return any(term in name_clean for term in COFFEE_STRUCTURAL_TERMS)


def compute_flavor_signature(
    ingredients: List[Dict[str, Any]],
    drink_type: str = 'SODA'
) -> Tuple[str, int, Optional[str]]:
    """Compute the anchor-aware canonical flavor signature for a recipe.

    Format: "{dominant_anchor}::{sorted_remaining_flavor_ingredients}"
    - Cherry 60, Lime 20, Vanilla 10 -> "cherry::lime|vanilla"
    - Cherry 50, Vanilla 30, Lime 10 -> "cherry::lime|vanilla" (Identical! Blocked)
    - Lime 60, Vanilla 20, Cherry 10 -> "lime::cherry|vanilla" (Distinct anchor! Allowed)

    Returns (signature_str, total_ingredient_count, dominant_ingredient_name).
    """
    dt = normalize_drink_type(drink_type)
    if not ingredients:
        return "", 0, None

    cleaned_all: List[Tuple[str, float, bool]] = []
    flavor_candidates: List[Tuple[str, float, bool]] = []

    for item in ingredients:
        raw_name = str(item.get('name') or '').strip()
        # Strip optional brand suffixes like "Vanilla [Monin]" or "Vanilla (Torani)"
        clean_name = re.sub(r'\s*[\[\(].*?[\]\)]\s*', '', raw_name).strip().lower()
        if not clean_name:
            continue
        parts = float(item.get('parts', item.get('amount', 1.0)) or 1.0)
        is_pri = bool(item.get('is_primary', False))
        cleaned_all.append((clean_name, parts, is_pri))

        if dt == 'COFFEE':
            ing_id = item.get('id')
            ing_obj = Ingredient.objects.filter(id=ing_id).first() if ing_id else None
            if is_coffee_structural_ingredient(ing_obj, clean_name):
                continue
        flavor_candidates.append((clean_name, parts, is_pri))

    if not flavor_candidates:
        flavor_candidates = list(cleaned_all)

    if not flavor_candidates:
        return "", 0, None

    # Deduplicate by name, keeping max parts
    dedup: Dict[str, Tuple[float, bool]] = {}
    for nm, pts, pri in flavor_candidates:
        if nm not in dedup or pts > dedup[nm][0] or pri:
            dedup[nm] = (max(pts, dedup.get(nm, (0.0, False))[0]), pri or dedup.get(nm, (0.0, False))[1])

    # Determine dominant anchor: explicit is_primary first, otherwise highest parts (tie-break alphabetically)
    explicit_primaries = [nm for nm, (_, pri) in dedup.items() if pri]
    if explicit_primaries:
        dominant = sorted(explicit_primaries, key=lambda n: (-dedup[n][0], n))[0]
    else:
        dominant = sorted(dedup.keys(), key=lambda n: (-dedup[n][0], n))[0]

    remaining = sorted(nm for nm in dedup.keys() if nm != dominant)
    sig = f"{dominant}::{'|'.join(remaining)}"
    return sig, len(cleaned_all), dominant


def ensure_recipe_primary_ingredient(recipe: Recipe) -> Optional[RecipeIngredient]:
    """Ensure a saved Recipe has is_primary=True on its dominant flavor ingredient."""
    rings = list(recipe.recipe_ingredients.select_related('ingredient').all())
    if not rings:
        return None

    existing_primary = next((r for r in rings if r.is_primary and r.ingredient is not None), None)
    if existing_primary:
        return existing_primary

    dt = normalize_drink_type(recipe.drink_type)
    flavor_rings = [
        r for r in rings
        if r.ingredient is not None and not (dt == 'COFFEE' and is_coffee_structural_ingredient(r.ingredient))
    ]
    if not flavor_rings:
        flavor_rings = [r for r in rings if r.ingredient is not None]
    if not flavor_rings:
        return None

    dominant_ring = max(flavor_rings, key=lambda r: (float(r.amount or 0.0), r.ingredient.name.lower()))
    dominant_ring.is_primary = True
    dominant_ring.save(update_fields=['is_primary'])
    return dominant_ring


def get_recipe_primary_category(recipe: Recipe) -> Optional[str]:
    """Return the primary flavor category name (title-cased) for a saved Recipe."""
    rings = list(recipe.recipe_ingredients.select_related('ingredient').all())
    if not rings:
        return None

    dt = normalize_drink_type(recipe.drink_type)
    pri = next(
        (r for r in rings if r.is_primary and r.ingredient and not (dt == 'COFFEE' and is_coffee_structural_ingredient(r.ingredient))),
        None
    )
    if not pri:
        flavor_rings = [
            r for r in rings
            if r.ingredient and not (dt == 'COFFEE' and is_coffee_structural_ingredient(r.ingredient))
        ]
        if flavor_rings:
            pri = max(flavor_rings, key=lambda r: float(r.amount or 0.0))
        else:
            pri = next((r for r in rings if r.ingredient), None)

    if pri and pri.ingredient and pri.ingredient.category:
        return pri.ingredient.category.strip().title()
    return None


def collect_existing_signatures(drink_type: str) -> Set[str]:
    """Collect all canonical flavor signatures across Recipe, MixHistory, and CachedQuickDrink."""
    dt = normalize_drink_type(drink_type)
    db_drink_types = ['SLUSHIE', 'CRYO'] if dt == 'SLUSHIE' else [dt]
    signatures: Set[str] = set()

    # 1. Saved Recipes
    for r in Recipe.objects.filter(drink_type__in=db_drink_types).prefetch_related('recipe_ingredients__ingredient'):
        ings = [
            {
                'id': ri.ingredient.id,
                'name': ri.ingredient.name,
                'parts': float(ri.amount),
                'is_primary': ri.is_primary
            }
            for ri in r.recipe_ingredients.all() if ri.ingredient
        ]
        sig, _, _ = compute_flavor_signature(ings, dt)
        if sig:
            signatures.add(sig)

    # 2. MixHistory
    for mh in MixHistory.objects.filter(drink_type__in=db_drink_types).prefetch_related('mix_ingredients__ingredient'):
        ings = [
            {
                'id': mi.ingredient.id,
                'name': mi.ingredient.name,
                'parts': float(mi.amount),
                'is_primary': mi.is_primary
            }
            for mi in mh.mix_ingredients.all() if mi.ingredient
        ]
        sig, _, _ = compute_flavor_signature(ings, dt)
        if sig:
            signatures.add(sig)

    # 3. CachedQuickDrink
    for cqd in CachedQuickDrink.objects.filter(drink_type__in=db_drink_types):
        if cqd.flavor_signature:
            signatures.add(cqd.flavor_signature)

    return signatures


def get_available_categories_for_lab(drink_type: str, mode: str = 'experimental') -> List[str]:
    """Return sorted active category names for a given lab and mode."""
    dt = normalize_drink_type(drink_type)
    qs = Ingredient.objects.filter(is_in_inventory=True)
    if mode.lower() == 'standard':
        qs = qs.filter(compatible_systems__icontains=dt)
    excluded = {'Coffee', 'Dairy'}
    cats = sorted({
        ing.category.strip().title()
        for ing in qs
        if ing.category and ing.category.strip().title() not in excluded
    })
    return cats


def resolve_generated_ingredients(
    raw_ingredients: List[Dict[str, Any]],
    inventory_pool: List[Ingredient],
    drink_type: str
) -> List[Dict[str, Any]]:
    """Map LLM-returned ingredient names to actual Ingredient records and flag the primary anchor."""
    from .views.ai.helpers import find_ingredient_by_name
    dt = normalize_drink_type(drink_type)
    resolved: List[Dict[str, Any]] = []
    seen_ids: Set[int] = set()

    for item in raw_ingredients:
        raw_name = str(item.get('name') or '').strip()
        if not raw_name:
            continue
        matched = find_ingredient_by_name(raw_name, inventory_pool)
        if not matched or matched.id in seen_ids:
            continue
        seen_ids.add(matched.id)
        parts = float(item.get('parts', item.get('amount', 15.0)) or 15.0)
        resolved.append({
            'id': matched.id,
            'name': matched.name,
            'parts': parts,
            'amount': parts,
            'category': matched.category,
            'type': matched.ingredient_type,
            'physical_state': matched.physical_state,
            'mixology_function': matched.mixology_function,
            'intensity': matched.intensity,
            'sweetness': matched.sweetness,
            'acidity': matched.acidity,
            'bitterness': matched.bitterness,
            'is_primary': False,
        })

    # Flag the dominant flavor ingredient as is_primary=True
    flavor_candidates = [
        r for r in resolved
        if not (dt == 'COFFEE' and is_coffee_structural_ingredient(None, r['name']) or (dt == 'COFFEE' and r.get('category', '').lower() in ('coffee', 'dairy')))
    ]
    if not flavor_candidates:
        flavor_candidates = resolved
    if flavor_candidates:
        dominant = max(flavor_candidates, key=lambda x: float(x['parts']))
        dominant['is_primary'] = True

    return resolved


def format_eta(seconds: Optional[int]) -> str:
    """Format an ETA in seconds into a human-friendly duration string."""
    if seconds is None:
        return "Calculating..."
    if seconds <= 0:
        return "Finishing up..."
    if seconds < 60:
        return f"~{seconds}s"
    minutes = seconds // 60
    rem_sec = seconds % 60
    if minutes < 60:
        return f"~{minutes}m {rem_sec:02d}s"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"~{hours}h {rem_min:02d}m"


def count_in_stock_cached_drinks(
    drink_type: str,
    mode: str,
    profile: str,
    ingredient_count: int,
    in_stock_ids: Set[int]
) -> int:
    """Count how many CachedQuickDrink entries in a bucket have all ingredients currently in stock."""
    dt = normalize_drink_type(drink_type)
    qs = CachedQuickDrink.objects.filter(
        drink_type=dt,
        mode=mode.lower(),
        profile__iexact=profile,
        ingredient_count=ingredient_count
    )
    valid_count = 0
    for cqd in qs:
        ings = cqd.ingredients_json or []
        if ings and all(int(i.get('id', 0)) in in_stock_ids for i in ings if i.get('id')):
            valid_count += 1
    return valid_count


def replenish_quick_drink_cache(
    progress_callback: Optional[Callable[..., None]] = None,
    target_lab: Optional[str] = None,
    target_profile: Optional[str] = None,
    target_mode: Optional[str] = None,
    max_per_bucket: Optional[int] = None,
) -> Dict[str, Any]:
    """Replenish the Quick Drink cache across labs, categories, and complexity buckets.

    Generates 1 recipe at a time for maximum small-model quality, pre-computing
    mixologist_notes and profile_description, tracks real-time generation metrics
    (created, remaining, ETA), and stops after 2 consecutive failed/duplicate attempts
    on any saturated bucket.
    """
    config = QuickDrinkCacheConfiguration.get_config()

    if target_mode:
        modes = [target_mode.lower()]
    else:
        if config.cache_modes == 'EXPERIMENTAL':
            modes = ['experimental']
        elif config.cache_modes == 'STANDARD':
            modes = ['standard']
        else:
            modes = ['experimental', 'standard']

    labs = [normalize_drink_type(target_lab)] if target_lab else ['SODA', 'COFFEE', 'SLUSHIE']
    in_stock_all = list(Ingredient.objects.filter(is_in_inventory=True))
    in_stock_ids = {ing.id for ing in in_stock_all}

    # Build work list of buckets: (dt, mode, profile, ing_count, cap)
    work_buckets: List[Tuple[str, str, str, int, int]] = []
    for mode in modes:
        for dt in labs:
            categories = [target_profile.strip().title()] if target_profile else get_available_categories_for_lab(dt, mode)
            bucket_Spec = BUCKET_TARGETS.get(dt, BUCKET_TARGETS['SODA'])
            for cat in categories:
                for ing_count, cap in bucket_Spec.items():
                    effective_cap = min(cap, max_per_bucket) if max_per_bucket else cap
                    work_buckets.append((dt, mode, cat, ing_count, effective_cap))

    total_buckets = len(work_buckets)
    created_total = 0
    skipped_full_buckets = 0
    saturated_buckets = 0

    # Helper for telemetry notifications supporting 2-arg or 3-arg callback signatures
    def notify(pct: int, msg: str, telem: Optional[Dict[str, Any]] = None):
        if not progress_callback:
            return
        import inspect
        try:
            sig = inspect.signature(progress_callback)
            if len(sig.parameters) >= 3 or any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
                progress_callback(pct, msg, telem or {})
            else:
                progress_callback(pct, msg)
        except Exception:
            try:
                progress_callback(pct, msg, telem or {})
            except TypeError:
                progress_callback(pct, msg)

    # Pre-scan buckets to determine total recipes needed
    bucket_plan: List[Dict[str, Any]] = []
    total_recipes_needed = 0
    for dt, mode, cat, ing_count, target_cap in work_buckets:
        current_valid = count_in_stock_cached_drinks(dt, mode, cat, ing_count, in_stock_ids)
        needed = max(0, target_cap - current_valid)
        total_recipes_needed += needed
        bucket_plan.append({
            'dt': dt,
            'mode': mode,
            'cat': cat,
            'ing_count': ing_count,
            'target_cap': target_cap,
            'current_valid': current_valid,
            'needed': needed,
        })

    recipes_remaining = total_recipes_needed
    durations: List[float] = []
    start_time = time.time()

    if total_recipes_needed == 0:
        summary = f"All {total_buckets} quick drink cache buckets are already at full capacity."
        config.last_run_at = timezone.now()
        config.last_status = 'SUCCESS'
        config.last_summary = summary
        config.save()
        final_telemetry = {
            'created': 0,
            'total_needed': 0,
            'remaining': 0,
            'eta_seconds': 0,
            'eta_display': 'Cache is full',
            'current_bucket': 'All buckets complete',
            'message': summary,
        }
        notify(100, summary, final_telemetry)
        return {
            'created': 0,
            'total_needed': 0,
            'total_buckets': total_buckets,
            'skipped_full_buckets': total_buckets,
            'saturated_buckets': 0,
            'summary': summary,
            'telemetry': final_telemetry,
        }

    for item in bucket_plan:
        dt = item['dt']
        mode = item['mode']
        cat = item['cat']
        ing_count = item['ing_count']
        target_cap = item['target_cap']
        needed = item['needed']
        bucket_label = f"{dt} / {cat} ({ing_count}-ing, {mode})"

        if needed <= 0:
            skipped_full_buckets += 1
            continue

        # Prepare inventory context and candidate pool for this lab + mode
        if mode == 'standard':
            pool = [ing for ing in in_stock_all if dt in (ing.compatible_systems or '').upper()]
            inv_context = AIAssistant.get_static_ingredients_context(drink_type=dt)
        else:
            pool = list(in_stock_all)
            inv_context = AIAssistant.get_static_ingredients_context(drink_type=None)

        if len(pool) < ing_count:
            saturated_buckets += 1
            recipes_remaining = max(0, recipes_remaining - needed)
            continue

        existing_signatures = collect_existing_signatures(dt)
        consecutive_failures = 0

        while needed > 0 and consecutive_failures < 2:
            # Estimate ETA based on running average duration
            if durations:
                avg_duration = sum(durations) / len(durations)
                eta_seconds = int(recipes_remaining * avg_duration)
            elif created_total > 0:
                elapsed = time.time() - start_time
                avg_duration = elapsed / created_total
                eta_seconds = int(recipes_remaining * avg_duration)
            else:
                eta_seconds = None

            pct = min(95, max(5, int((created_total / total_recipes_needed) * 95)))
            msg = f"Synthesizing {bucket_label} ({created_total}/{total_recipes_needed} recipes created)..."
            notify(
                pct,
                msg,
                {
                    'created': created_total,
                    'total_needed': total_recipes_needed,
                    'remaining': recipes_remaining,
                    'eta_seconds': eta_seconds,
                    'eta_display': format_eta(eta_seconds),
                    'current_bucket': bucket_label,
                    'message': msg,
                }
            )

            step_t0 = time.time()
            raw_recipe = AIAssistant.generate_single_quick_drink(
                inventory=inv_context,
                drink_type=dt,
                mode=mode,
                profile=cat,
                ingredient_count=ing_count,
                excluded_signatures=sorted(existing_signatures),
            )
            step_duration = max(0.1, time.time() - step_t0)
            durations.append(step_duration)

            if not raw_recipe or not isinstance(raw_recipe.get('ingredients'), list):
                consecutive_failures += 1
                continue

            resolved_ings = resolve_generated_ingredients(raw_recipe['ingredients'], pool, dt)
            if len(resolved_ings) < 2:
                consecutive_failures += 1
                continue

            sig, actual_count, _ = compute_flavor_signature(resolved_ings, dt)
            if not sig or sig in existing_signatures:
                logger.info(
                    f"QuickCache - Info - Duplicate or invalid signature '{sig}' in {dt}/{cat}/{ing_count}-ing "
                    f"(failure {consecutive_failures + 1}/2)"
                )
                consecutive_failures += 1
                continue

            # Valid, unique recipe! Save to cache
            bucket_count = actual_count if actual_count in BUCKET_TARGETS.get(dt, {}) else ing_count
            CachedQuickDrink.objects.create(
                drink_type=dt,
                mode=mode,
                profile=cat,
                ingredient_count=bucket_count,
                name=str(raw_recipe.get('name') or 'Synthesized Elixir').strip()[:120],
                description=str(raw_recipe.get('description') or '').strip(),
                mixologist_notes=str(raw_recipe.get('mixologist_notes') or '').strip(),
                profile_description=str(raw_recipe.get('profile_description') or '').strip(),
                ingredients_json=resolved_ings,
                flavor_signature=sig,
            )
            existing_signatures.add(sig)
            created_total += 1
            needed -= 1
            recipes_remaining = max(0, recipes_remaining - 1)
            consecutive_failures = 0

        if consecutive_failures >= 2:
            saturated_buckets += 1
            recipes_remaining = max(0, recipes_remaining - needed)

    summary = (
        f"Created {created_total} cached recipes across {total_buckets} buckets "
        f"({skipped_full_buckets} already full, {saturated_buckets} saturated)."
    )
    config.last_run_at = timezone.now()
    config.last_status = 'SUCCESS'
    config.last_summary = summary
    config.save()

    final_telemetry = {
        'created': created_total,
        'total_needed': total_recipes_needed,
        'remaining': 0,
        'eta_seconds': 0,
        'eta_display': 'Complete',
        'current_bucket': 'All buckets complete',
        'message': summary,
    }
    notify(100, summary, final_telemetry)

    logger.info(f"QuickCache - Info - {summary}")
    return {
        'created': created_total,
        'total_needed': total_recipes_needed,
        'total_buckets': total_buckets,
        'skipped_full_buckets': skipped_full_buckets,
        'saturated_buckets': saturated_buckets,
        'summary': summary,
        'telemetry': final_telemetry,
    }


def draw_quick_drinks(
    drink_type: str,
    profile: str,
    mode: str = 'experimental',
    exclude_ids: Optional[Set[str]] = None,
    count: int = 5
) -> Dict[str, Any]:
    """Draw up to `count` drinks combining Existing Saved Recipes and CachedQuickDrink
    using the complexity distribution rules, cycling cleanly through unseen items first.
    """
    dt = normalize_drink_type(drink_type)
    profile_clean = (profile or '').strip()
    mode_clean = (mode or 'experimental').strip().lower()
    exclude_set = set(exclude_ids or set())

    in_stock_map: Dict[int, Ingredient] = {
        ing.id: ing for ing in Ingredient.objects.filter(is_in_inventory=True)
    }

    pool_by_bucket: Dict[int, List[Dict[str, Any]]] = {2: [], 3: [], 4: [], 5: []}
    all_candidates: List[Dict[str, Any]] = []

    # 1. Gather matching in-stock Official Saved Recipes
    db_drink_types = ['SLUSHIE', 'CRYO'] if dt == 'SLUSHIE' else [dt]
    recipes_qs = Recipe.objects.filter(drink_type__in=db_drink_types).prefetch_related(
        'recipe_ingredients__ingredient', 'categories'
    )
    for r in recipes_qs:
        rings = list(r.recipe_ingredients.all())
        if not rings:
            continue
        if not all(ri.ingredient and ri.ingredient.id in in_stock_map for ri in rings):
            continue

        # Check if recipe matches profile via primary ingredient category or RecipeCategory tag
        matched = False
        if not profile_clean:
            matched = True
        else:
            p_lower = profile_clean.lower()
            pri_cat = get_recipe_primary_category(r)
            if pri_cat and pri_cat.lower() == p_lower:
                matched = True
            elif any(cat.name.strip().lower() == p_lower for cat in r.categories.all()):
                matched = True

        if not matched:
            continue

        ings_payload = []
        for ri in rings:
            ing = ri.ingredient
            ings_payload.append({
                'id': ing.id,
                'name': ing.name,
                'amount': float(ri.amount),
                'parts': float(ri.amount),
                'category': ing.category,
                'type': ing.ingredient_type,
                'physical_state': ing.physical_state,
                'mixology_function': ing.mixology_function,
                'intensity': ing.intensity,
                'sweetness': ing.sweetness,
                'acidity': ing.acidity,
                'bitterness': ing.bitterness,
                'is_primary': ri.is_primary,
            })

        sig, ing_count, _ = compute_flavor_signature(ings_payload, dt)
        bucket_key = max(2, min(5, ing_count))
        if dt == 'COFFEE' and bucket_key < 3:
            bucket_key = 3

        item_dict = {
            'id': str(r.uuid),
            'uuid': str(r.uuid),
            'source_type': 'existing',
            'badge_label': 'EXISTING RECIPE',
            'name': r.name,
            'description': r.description or '',
            'rating': r.rating,
            'drink_type': dt,
            'ingredient_count': bucket_key,
            'flavor_signature': sig,
            'ingredients': ings_payload,
        }
        pool_by_bucket[bucket_key].append(item_dict)
        all_candidates.append(item_dict)

    # 2. Gather matching in-stock CachedQuickDrink records
    cached_qs = CachedQuickDrink.objects.filter(drink_type=dt, mode=mode_clean)
    if profile_clean:
        cached_qs = cached_qs.filter(profile__iexact=profile_clean)

    # Fallback: if no cached drinks for requested mode, also check the other mode before claiming empty
    if not cached_qs.exists():
        alt_qs = CachedQuickDrink.objects.filter(drink_type=dt)
        if profile_clean:
            alt_qs = alt_qs.filter(profile__iexact=profile_clean)
        cached_qs = alt_qs

    for cqd in cached_qs:
        raw_ings = cqd.ingredients_json or []
        if not raw_ings:
            continue
        if not all(int(i.get('id', 0)) in in_stock_map for i in raw_ings if i.get('id')):
            continue

        enriched_ings = []
        for i in raw_ings:
            ing_obj = in_stock_map.get(int(i.get('id', 0)))
            if not ing_obj:
                continue
            pts = float(i.get('parts', i.get('amount', 15.0)))
            enriched_ings.append({
                'id': ing_obj.id,
                'name': ing_obj.name,
                'amount': pts,
                'parts': pts,
                'category': ing_obj.category,
                'type': ing_obj.ingredient_type,
                'physical_state': ing_obj.physical_state,
                'mixology_function': ing_obj.mixology_function,
                'intensity': ing_obj.intensity,
                'sweetness': ing_obj.sweetness,
                'acidity': ing_obj.acidity,
                'bitterness': ing_obj.bitterness,
                'is_primary': bool(i.get('is_primary', False)),
            })

        bucket_key = max(2, min(5, cqd.ingredient_count or len(enriched_ings)))
        if dt == 'COFFEE' and bucket_key < 3:
            bucket_key = 3

        item_dict = {
            'id': str(cqd.uuid),
            'uuid': str(cqd.uuid),
            'source_type': 'cached',
            'badge_label': 'CACHED AI',
            'name': cqd.name,
            'description': cqd.description or '',
            'mixologist_notes': cqd.mixologist_notes or '',
            'profile_description': cqd.profile_description or '',
            'rating': 0,
            'drink_type': dt,
            'ingredient_count': bucket_key,
            'flavor_signature': cqd.flavor_signature,
            'ingredients': enriched_ings,
        }
        pool_by_bucket[bucket_key].append(item_dict)
        all_candidates.append(item_dict)

    total_pool_size = len(all_candidates)
    if total_pool_size == 0:
        return {
            'items': [],
            'total_pool_size': 0,
            'cycle_wrapped': False,
            'needs_live_generation': True,
        }

    # Check if we need to wrap around the cycle
    unseen_total = [c for c in all_candidates if c['id'] not in exclude_set]
    cycle_wrapped = False
    if len(unseen_total) == 0:
        exclude_set = set()
        cycle_wrapped = True

    # Target slot distribution for a 5-card draw
    if count == 1:
        slots = [random.choice([3, 4, 2, 5] if dt != 'COFFEE' else [3, 4, 5])]
    elif dt == 'COFFEE':
        slots = [3, 3, 4, 4, 5][:count]
    else:
        mid_pair = random.choice([[3, 3, 4], [3, 4, 4]])
        slots = ([2] + mid_pair + [5])[:count]

    selected_items: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()

    def pick_from_bucket(b_key: int, allow_seen: bool = False) -> Optional[Dict[str, Any]]:
        candidates = [
            c for c in pool_by_bucket.get(b_key, [])
            if c['id'] not in selected_ids and (allow_seen or c['id'] not in exclude_set)
        ]
        if not candidates:
            return None
        chosen = random.choice(candidates)
        selected_ids.add(chosen['id'])
        return chosen

    # Pass 1: Pick unseen items matching exact target bucket slots
    for slot in slots:
        picked = pick_from_bucket(slot, allow_seen=False)
        if picked:
            selected_items.append(picked)

    # Pass 2: Fill remaining slots from any unseen items across other buckets
    if len(selected_items) < min(count, total_pool_size):
        remaining_unseen = [
            c for c in all_candidates
            if c['id'] not in selected_ids and c['id'] not in exclude_set
        ]
        random.shuffle(remaining_unseen)
        while len(selected_items) < min(count, total_pool_size) and remaining_unseen:
            nxt = remaining_unseen.pop()
            selected_ids.add(nxt['id'])
            selected_items.append(nxt)

    # Pass 3: If unseen pool had fewer than `count` items, wrap around to seen items to complete the 5-card hand
    if len(selected_items) < min(count, total_pool_size):
        cycle_wrapped = True
        for slot in slots:
            if len(selected_items) >= min(count, total_pool_size):
                break
            picked = pick_from_bucket(slot, allow_seen=True)
            if picked:
                selected_items.append(picked)

        if len(selected_items) < min(count, total_pool_size):
            remaining_any = [c for c in all_candidates if c['id'] not in selected_ids]
            random.shuffle(remaining_any)
            while len(selected_items) < min(count, total_pool_size) and remaining_any:
                nxt = remaining_any.pop()
                selected_ids.add(nxt['id'])
                selected_items.append(nxt)

    return {
        'items': selected_items,
        'total_pool_size': total_pool_size,
        'cycle_wrapped': cycle_wrapped,
        'needs_live_generation': False,
    }
