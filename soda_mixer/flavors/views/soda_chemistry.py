"""Soda Chemistry Engine API view."""

import json
import logging
from typing import Dict, Any, List
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

def classify_soda_ingredient(name: str, intensity: int) -> str:
    """Classify ingredients into Delicate, Blender, or Accent based on intensity and keywords."""
    name_lower = name.lower()
    
    delicate_names = ['watermelon', 'guava', 'pear', 'peach', 'melon', 'strawberry', 'berry']
    blender_names = ['coconut', 'vanilla', 'marshmallow', 'butterscotch', 'caramel', 'chocolate', 'cocoa']
    accent_names = ['lime', 'peppermint', 'ginger', 'lavender', 'mint']
    
    if any(k in name_lower for k in delicate_names):
        return 'DELICATE'
    if any(k in name_lower for k in blender_names):
        return 'BLENDER'
    if any(k in name_lower for k in accent_names):
        return 'ACCENT'
        
    if intensity >= 4:
        return 'ACCENT'
    elif intensity == 3:
        return 'BLENDER'
    else:
        return 'DELICATE'

@csrf_exempt
@require_http_methods(["POST"])
def soda_chemistry_api(request: HttpRequest) -> JsonResponse:
    """
    Ingest soda ingredients and calculate volumes, budgets, validations, and prep instructions.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as e:
        logger.warning(f"SodaChemistry - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    sweetness_style = data.get('sweetness_style', '').strip().upper()
    bottle_scale = float(data.get('bottle_scale', 1.0))
    ingredients_input = data.get('ingredients', [])

    # Validate scale parameter
    if bottle_scale <= 0.0:
        bottle_scale = 1.0

    # Auto-detect sweetness style if not specified or set to AUTO
    if not sweetness_style or sweetness_style == 'AUTO':
        baseline_sum = 0.0
        for ing in ingredients_input:
            itype = str(ing.get('ingredient_type', ing.get('type', ''))).upper()
            if itype in ['SODA_SYRUP', 'ADDITIVE', 'OTHER'] and not ing.get('is_dry', False):
                baseline_sum += float(ing.get('amount', 0.0))
        
        unscaled_sum = baseline_sum / bottle_scale
        if unscaled_sum <= 110.0:
            sweetness_style = 'CRISP'
        elif unscaled_sum >= 130.0:
            sweetness_style = 'FOUNTAIN'
        else:
            sweetness_style = 'CRAFT'

    # 1. Hardware Constraints & Volumetric Anchors
    water_volume_ml = 840.0 * bottle_scale
    overflow_ceiling_ml = 160.0 * bottle_scale

    # 2. Sweetness Selector Enforcement (The Syrup Budget)
    if sweetness_style == 'CRISP':
        base_syrup_budget = 105.0
        baseline_sweetness = 3.5
    elif sweetness_style == 'FOUNTAIN':
        base_syrup_budget = 140.0
        baseline_sweetness = 5.0
    else:
        sweetness_style = 'CRAFT'  # Ensure it is normalized
        base_syrup_budget = 120.0  # CRAFT is the default
        baseline_sweetness = 4.0

    syrup_budget_ml = base_syrup_budget * bottle_scale

    # Partition ingredients using the Primary Flavor Anchor Protocol
    flavor_modifiers = []
    for ing in ingredients_input:
        itype = str(ing.get('ingredient_type', ing.get('type', ''))).upper()
        if itype in ['SODA_SYRUP', 'ADDITIVE', 'OTHER'] and not ing.get('is_dry', False):
            flavor_modifiers.append(ing)

    total_ingredients_count = len(flavor_modifiers)

    if total_ingredients_count == 0:
        logger.warning("SodaChemistry - Warning - No flavor modifiers provided.")
        return JsonResponse({
            "recipe_validation": "Fail: No flavor modifiers provided.",
            "drink_metrics": {
                "style": "Soda",
                "sweetness_style": sweetness_style,
                "bottle_scale": bottle_scale,
                "water_volume_ml": round(water_volume_ml, 1),
                "total_syrup_volume_ml": 0.0,
                "maximum_syrup_limit_ml": round(overflow_ceiling_ml, 1)
            },
            "ingredients": {
                "carbonated_water": {"name": "Carbonated Water", "volume_ml": round(water_volume_ml, 1)},
                "modifiers": []
            },
            "barista_notes": "Decommissioned: Formula lacks active flavor modifiers.",
            "preparation_steps": [],
            "extraction_analysis": {
                "sweetness": 0.0,
                "acidity": 1.0,
                "bitterness": 1.0
            }
        })

    # Identify Primary Base (Anchor)
    primary_base_ing = None
    primary_idx = -1
    for idx, ing in enumerate(flavor_modifiers):
        is_prim = ing.get('is_primary')
        if is_prim is None:
            is_prim = ing.get('primary')
        if is_prim is True or is_prim == 'true':
            primary_base_ing = ing
            primary_idx = idx
            break
    
    if not primary_base_ing and flavor_modifiers:
        primary_base_ing = flavor_modifiers[0]
        primary_idx = 0

    # Partition the remaining modifiers
    remaining_modifiers = [ing for idx, ing in enumerate(flavor_modifiers) if idx != primary_idx]
    rem_blenders = []
    rem_accents = []
    for ing in remaining_modifiers:
        name = ing.get('name', 'Syrup')
        intensity = int(ing.get('intensity', 3))
        classification = classify_soda_ingredient(name, intensity)
        if classification in ['DELICATE', 'BLENDER']:
            rem_blenders.append(ing)
        else:
            rem_accents.append(ing)

    N_accent = len(rem_accents)
    N_blender = len(rem_blenders)

    # Calculate proportions
    if total_ingredients_count == 1:
        primary_share = 1.0
        blender_share = 0.0
        accent_share = 0.0
    else:
        primary_share = 0.60
        if N_blender > 0 and N_accent > 0:
            accent_share = 0.075
            blender_share = (0.40 - N_accent * 0.075) / N_blender
        elif N_blender > 0 and N_accent == 0:
            accent_share = 0.0
            blender_share = 0.40 / N_blender
        else: # N_blender == 0 and N_accent > 0
            accent_share = 0.075
            blender_share = 0.0
            primary_share = 1.0 - N_accent * 0.075

    # Proportional volume distribution
    modifiers_output = []
    total_calculated_volume = 0.0

    # 1. Primary Base
    p_vol = primary_share * syrup_budget_ml
    modifiers_output.append({
        "id": primary_base_ing.get('id'),
        "name": primary_base_ing.get('name'),
        "volume_ml": round(p_vol, 1),
        "percentage_of_syrup": round(primary_share * 100, 1),
        "role": "Primary Base"
    })
    total_calculated_volume += p_vol

    # 2. Remaining Blenders/Delicates
    if N_blender > 0:
        b_vol = blender_share * syrup_budget_ml
        for ing in rem_blenders:
            modifiers_output.append({
                "id": ing.get('id'),
                "name": ing.get('name'),
                "volume_ml": round(b_vol, 1),
                "percentage_of_syrup": round(blender_share * 100, 1),
                "role": "Complementary Blender"
            })
            total_calculated_volume += b_vol

    # 3. Remaining Accents
    if N_accent > 0:
        a_vol = accent_share * syrup_budget_ml
        for ing in rem_accents:
            modifiers_output.append({
                "id": ing.get('id'),
                "name": ing.get('name'),
                "volume_ml": round(a_vol, 1),
                "percentage_of_syrup": round(accent_share * 100, 1),
                "role": "Aggressive Accent"
            })
            total_calculated_volume += a_vol

    # 4. Extraction Analysis Output Logic (Sweetness, Acidity, Bitterness)
    # Perceived Sweetness rating and high-acid penalty check
    sweetness_score = baseline_sweetness
    accent_acidity_scores = [float(ing.get('acidity_score', ing.get('acidity', 3.0))) for ing in rem_accents]
    if len(accent_acidity_scores) > 0:
        avg_accent_acidity = sum(accent_acidity_scores) / len(accent_acidity_scores)
        if avg_accent_acidity >= 4.0:
            sweetness_score -= 0.5

    # Weighted Average acidity & bitterness
    total_weights = 0.0
    weighted_acidity = 0.0
    weighted_bitterness = 0.0

    for out_ing in modifiers_output:
        vol = out_ing["volume_ml"]
        # find original ingredient for metadata
        orig = next((i for i in ingredients_input if i.get('id') == out_ing["id"]), None)
        if orig:
            acid = float(orig.get('acidity_score', orig.get('acidity', 3.0)))
            bitter = float(orig.get('bitterness_score', orig.get('bitterness', 1.0)))
            weighted_acidity += acid * vol
            weighted_bitterness += bitter * vol
            total_weights += vol

    if total_weights > 0.0:
        acidity_score = round(weighted_acidity / total_weights, 2)
        bitterness_score = round(weighted_bitterness / total_weights, 2)
    else:
        acidity_score = 1.0
        bitterness_score = 1.0

    # Round sweetness rating
    sweetness_score = round(sweetness_score, 2)

    # Validation & Overflow Checks
    validation_status = "Pass"
    if total_calculated_volume > overflow_ceiling_ml:
        validation_status = "Fail: SodaStream bottle overflow risk. Combined flavor modifiers exceed limit."

    # 5. Execution & Build Path Generation
    prep_steps = [
        "Step 1: Dispense the calculated volumes of all Monin syrups directly into the empty serving or mixing vessel first.",
        f"Step 2: Carbonate exactly {water_volume_ml:.0f}ml of cold water in the standard hardware vessel up to the designated fill line.",
        "Step 3: Slowly tilt the syrup vessel and pour the carbonated water down the inside wall of the glass to preserve carbonation.",
        "Step 4: Cap bottle back and gently rotate 180 degrees 2-4 times. Let the bottle sit for at least 30 seconds before enjoying."
    ]

    barista_notes = f"Soda ratio synthesized at {sweetness_style} sweetness level. Output optimized for Monin flavor syrups."
    if total_calculated_volume > overflow_ceiling_ml:
        barista_notes = "Overflow warning! The combined syrup volumes exceed the physical safety constraints of the Sodastream system."

    res_data = {
        "recipe_validation": validation_status,
        "drink_metrics": {
            "style": "Soda",
            "sweetness_style": sweetness_style,
            "bottle_scale": bottle_scale,
            "water_volume_ml": round(water_volume_ml, 1),
            "total_syrup_volume_ml": round(total_calculated_volume, 1),
            "maximum_syrup_limit_ml": round(overflow_ceiling_ml, 1)
        },
        "ingredients": {
            "carbonated_water": {
                "name": "Carbonated Water",
                "volume_ml": round(water_volume_ml, 1)
            },
            "modifiers": modifiers_output
        },
        "barista_notes": barista_notes,
        "preparation_steps": prep_steps,
        "extraction_analysis": {
            "sweetness": sweetness_score,
            "acidity": acidity_score,
            "bitterness": bitterness_score
        }
    }

    return JsonResponse(res_data)
