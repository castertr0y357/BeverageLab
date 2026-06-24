"""Coffee Chemistry Engine API view."""

import json
import logging
from typing import Dict, Any, List, Set, Union, Optional
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def coffee_chemistry_api(request: HttpRequest) -> JsonResponse:
    """
    Ingest coffee ingredients and calculate drink chemistry, budgets, and validations.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as e:
        logger.warning(f"CoffeeChemistry - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    drink_category = data.get('drink_category', 'Hot Coffee').strip()
    cup_size_oz = float(data.get('cup_size_oz', 12.0))
    ingredients_input = data.get('ingredients', [])
    espresso_hot_mode = data.get('espresso_hot_mode', 'shots').strip().lower()

    drink_cat_lower = drink_category.lower()

    # Determine is_espresso_base early
    is_espresso_base = True
    if "standard" in drink_cat_lower or "brew" in drink_cat_lower:
        is_espresso_base = False
    
    for ing in ingredients_input:
        itype = str(ing.get('ingredient_type', ing.get('type', ''))).upper()
        if itype == 'COFFEE_BEAN':
            base_type = str(ing.get('coffee_base_type', '')).lower()
            if 'standard' in base_type or 'brew' in base_type:
                is_espresso_base = False
                break

    # Route Pure Espresso / Short Milk
    is_short_milk = "pure espresso" in drink_cat_lower or "short milk" in drink_cat_lower or "cortado" in drink_cat_lower or "cappuccino" in drink_cat_lower

    # 1. Volumetric Space Allocation & Budget
    if "iced" in drink_cat_lower:
        style_str = "Iced"
        ice_volume_oz = round(cup_size_oz * 0.40, 2)
        liquid_budget_oz = round(cup_size_oz * 0.60, 2)
    else:
        style_str = "Hot"
        ice_volume_oz = 0.0
        liquid_budget_oz = cup_size_oz

    # Partition ingredients by role
    coffee_inputs = []
    dairy_inputs = []
    modifier_inputs = []

    for ing in ingredients_input:
        itype = str(ing.get('ingredient_type', ing.get('type', ''))).upper()
        if itype == 'COFFEE_BEAN':
            coffee_inputs.append(ing)
        elif itype == 'DAIRY':
            dairy_inputs.append(ing)
        elif itype in ['ADDITIVE', 'OTHER', 'SODA_SYRUP']:
            modifier_inputs.append(ing)
        else:
            # Fallback based on name keywords
            name_lower = str(ing.get('name', '')).lower()
            if 'milk' in name_lower or 'oat' in name_lower or 'almond' in name_lower or 'soy' in name_lower or 'dairy' in name_lower:
                dairy_inputs.append(ing)
            elif 'syrup' in name_lower or 'sauce' in name_lower or 'honey' in name_lower or 'sugar' in name_lower:
                modifier_inputs.append(ing)
            else:
                modifier_inputs.append(ing)

    # 2. Coffee Base Mix calculations
    if not coffee_inputs:
        logger.warning("CoffeeChemistry - Warning - No coffee base components provided.")
        return JsonResponse({
            "recipe_validation": "Fail: No coffee base components provided.",
            "drink_metrics": {
                "style": style_str,
                "cup_size_oz": cup_size_oz,
                "ice_space_reserved_oz": ice_volume_oz,
                "total_liquid_budget_oz": liquid_budget_oz
            },
            "ingredients": {
                "coffee_base": {"name": "None", "shots": 0, "volume_oz": 0.0},
                "base_modifiers": [],
                "payload_filler": {"name": "None", "volume_oz": 0.0},
                "flavor_modifiers": [],
                "coffee_base_mix": [],
                "dairy_or_filler": {"name": "None", "volume_oz": 0.0, "percentage_of_liquid": 0.0},
                "modifiers": []
            },
            "barista_notes": "Decommissioned: Formula lacks active extraction baseline.",
            "aggregate_base_metrics": {
                "calculated_body": 0.0,
                "calculated_acidity": 0.0,
                "calculated_bitterness": 0.0,
                "combined_notes": []
            },
            "ice_volume_oz": ice_volume_oz,
            "liquid_budget_oz": liquid_budget_oz,
            "hot_water_volume_oz": 0.0
        })

    # Blending Ratios
    total_proportion = 0.0
    for c in coffee_inputs:
        ratio = float(c.get('ratio', c.get('amount', 0.0)))
        total_proportion += ratio

    ratios = []
    if total_proportion > 0.0:
        for c in coffee_inputs:
            ratio = float(c.get('ratio', c.get('amount', 0.0)))
            ratios.append(ratio / total_proportion)
    else:
        # Equal ratio fallback
        count = len(coffee_inputs)
        ratios = [1.0 / count] * count

    # Aggregate Base Profile
    calculated_body = 0.0
    calculated_acidity = 0.0
    calculated_bitterness = 0.0
    combined_notes_set = set()

    for idx, c in enumerate(coffee_inputs):
        ratio = ratios[idx]
        
        # Read scores resiliently
        body = float(c.get('body_intensity', c.get('intensity', 3.0)))
        acidity = float(c.get('acidity_score', c.get('acidity', 3.0)))
        bitter = float(c.get('bitterness_score', c.get('bitterness', 3.0)))
        
        calculated_body += ratio * body
        calculated_acidity += ratio * acidity
        calculated_bitterness += ratio * bitter
        
        # Parse flavor notes
        notes = c.get('flavor_notes', [])
        if isinstance(notes, str):
            notes = [n.strip().lower() for n in notes.split(',') if n.strip()]
        for n in notes:
            combined_notes_set.add(n.lower().strip())

    combined_notes = sorted(list(combined_notes_set))
    calculated_body = round(calculated_body, 2)
    calculated_acidity = round(calculated_acidity, 2)
    calculated_bitterness = round(calculated_bitterness, 2)

    # Blending Conflict Logic
    body_dilution = calculated_body < 3.5

    # Flavor clash groups
    group_earthy_herbal = {'earthy', 'herbal', 'wood', 'woody', 'spice', 'spicy', 'tobacco', 'grass', 'grassy', 'tea', 'tea-like'}
    group_acidic_citrus = {'citrus', 'lemon', 'lime', 'orange', 'grapefruit', 'acidity', 'acidic', 'tangy', 'bright', 'sour', 'fruit', 'fruity', 'berry'}

    has_earthy_herbal = any(note in group_earthy_herbal for note in combined_notes)
    has_acidic_citrus = any(note in group_acidic_citrus for note in combined_notes)
    flavor_clash = has_earthy_herbal and has_acidic_citrus

    recipe_validation = "Pass"
    validation_notes = ""

    # Adjust modifiers to neutral profiles if flavor notes clash
    caramelized_keywords = {'caramel', 'chocolate', 'cocoa', 'mocha', 'toffee', 'butterscotch', 'maple', 'honey', 'molasses', 'marshmallow', 'toasted'}
    
    modified_list = []
    for mod in modifier_inputs:
        name = mod.get('name', 'Syrup')
        name_lower = name.lower()
        if flavor_clash and any(k in name_lower for k in caramelized_keywords):
            # Rename to neutral profile
            mod_adjusted = dict(mod)
            mod_adjusted['name'] = "Vanilla Syrup"
            modified_list.append(mod_adjusted)
        else:
            modified_list.append(mod)

    if flavor_clash:
        recipe_validation = "Warning"
        validation_notes = "Warning: High-acidity blend may clash with caramelized syrups. Modifiers adjusted to neutral profiles."

    # 3. Flavor Balancing & "Modifier Crowding" Rules
    requested_modifier_total = 0.0
    has_modifier_amounts = False
    combined_swe = 0.0
    for m in modified_list:
        swe = float(m.get('sweetness_score', m.get('sweetness', 3.0)))
        combined_swe += swe
        
        amt = m.get('amount')
        if amt is not None:
            amt_val = float(amt)
            if amt_val > 4.0:
                amt_val = amt_val / 29.5735
            requested_modifier_total += amt_val
            has_modifier_amounts = True

    num_modifiers = len(modified_list)
    if num_modifiers > 1 or combined_swe > 5:
        modifier_cap = liquid_budget_oz * 0.10
    else:
        modifier_cap = liquid_budget_oz * 0.15

    if not modified_list:
        modifier_budget = 0.0
    else:
        if not has_modifier_amounts:
            modifier_budget = modifier_cap
        else:
            modifier_budget = min(requested_modifier_total, modifier_cap)

    # Re-calculate exact modifier budget shares (60% dominant, 40% accent split)
    flavor_modifiers_output = []
    if modified_list:
        if len(modified_list) == 1:
            name = modified_list[0].get('name', 'Syrup')
            flavor_modifiers_output.append({
                "name": f"{name} (Dominant)",
                "volume_oz": round(modifier_budget, 2)
            })
        else:
            group_dark_chocolaty = {'chocolate', 'dark', 'cocoa', 'nutty', 'roasted', 'smoky', 'caramel', 'sweet'}
            is_dark_base = any(note in group_dark_chocolaty for note in combined_notes)
            is_earthy_base = has_earthy_herbal

            mod_scores = []
            for idx, m in enumerate(modified_list):
                name = m.get('name', '').lower()
                is_caramelized = any(k in name for k in caramelized_keywords) or 'sugar' in name
                is_chocolaty_nutty = any(k in name for k in ['chocolate', 'cocoa', 'mocha', 'nutty', 'hazelnut', 'almond', 'macadamia'])
                
                score = 1
                if is_earthy_base and is_caramelized:
                    score = 0
                elif is_dark_base and (is_caramelized or is_chocolaty_nutty):
                    score = 2
                
                mod_scores.append((score, idx))

            mod_scores.sort(key=lambda x: (x[0], -x[1]), reverse=True)
            dominant_idx = mod_scores[0][1]

            dominant_budget = modifier_budget * 0.60
            accent_budget_total = modifier_budget * 0.40
            accent_count = len(modified_list) - 1
            accent_budget_each = accent_budget_total / accent_count if accent_count > 0 else 0.0

            for idx, m in enumerate(modified_list):
                name = m.get('name', 'Syrup')
                if idx == dominant_idx:
                    vol = dominant_budget
                    role = "(Dominant)"
                else:
                    vol = accent_budget_each
                    role = "(Accent)"
                
                flavor_modifiers_output.append({
                    "name": f"{name} {role}",
                    "volume_oz": round(vol, 2)
                })

    # 4. Base-Specific Processing Guardrails
    if is_espresso_base:
        if cup_size_oz <= 4.0:
            shot_count = max(1, int(round(cup_size_oz)))
        elif cup_size_oz <= 8.0:
            shot_count = 1
        elif cup_size_oz <= 12.0:
            shot_count = 2
        elif cup_size_oz <= 16.0:
            shot_count = 3
        else:
            shot_count = 4
        coffee_base_vol = round(shot_count * 0.9, 2)
        
        if is_short_milk:
            hot_water_vol = 0.0
        else:
            if "iced" not in drink_cat_lower and espresso_hot_mode == 'water':
                hot_water_vol = coffee_base_vol  # 1:1 dilution ratio
            else:
                hot_water_vol = 0.0
    else:
        # Route B: Standard Brew
        shot_count = 0
        if "iced" in drink_cat_lower:
            coffee_base_vol = round(liquid_budget_oz * 0.70, 2)
        else:
            coffee_base_vol = round(cup_size_oz * 0.70, 2)
        hot_water_vol = 0.0
        if is_short_milk:
            recipe_validation = "Warning"
            validation_notes = "Warning: Standard Brew is incompatible with Pure Espresso / Short Milk format."

    # 5. Dynamic Whole Milk / Dairy Payload (Floating Filler Rule)
    secondary_liquid_vol = liquid_budget_oz - coffee_base_vol - modifier_budget - hot_water_vol
    if secondary_liquid_vol < 0.0:
        secondary_liquid_vol = 0.0

    # Apply Melt-Tax Protocol (Category A: Iced only and Espresso Base)
    ice_melt_water_vol = 0.0
    if "iced" in drink_cat_lower and is_espresso_base:
        ice_melt_water_vol = round(secondary_liquid_vol * 0.10, 2)
        secondary_liquid_vol = round(secondary_liquid_vol * 0.90, 2)

    # Note: Body dilution penalty is removed from ratio volumes per overhaul rules, 
    # but we retain the validation warnings/notes.
    if body_dilution:
        if recipe_validation == "Pass":
            recipe_validation = "Warning"
            validation_notes = "Warning: Low aggregate body intensity detected."

    # Round final volumes
    coffee_base_vol = round(coffee_base_vol, 2)
    secondary_liquid_vol = round(secondary_liquid_vol, 2)
    hot_water_vol = round(hot_water_vol, 2)

    # Base Modifiers format
    base_modifiers_output = []
    if hot_water_vol > 0.0:
        base_modifiers_output.append({
            "name": "Hot Water (Americano Toggle)",
            "volume_oz": hot_water_vol
        })
    if ice_melt_water_vol > 0.0:
        base_modifiers_output.append({
            "name": "Ice Melt Water",
            "volume_oz": ice_melt_water_vol
        })

    # Dairy or Filler formatting
    dairy_name = dairy_inputs[0].get('name', 'Whole Milk') if dairy_inputs else ("Hot Water" if not is_espresso_base and not dairy_inputs else "Whole Milk")
    
    # Barista Notes
    barista_notes = "Extraction and chemistry parameters are balanced. Serve and enjoy!"
    if "iced" in drink_cat_lower:
        if is_espresso_base:
            barista_notes = "Hot espresso melts ice rapidly; consider pulling shots over ice directly to manage dilution."
        else:
            barista_notes = "Standard brew is more easily washed out than espresso; keep dairy below 20% to preserve texture."
    elif flavor_clash:
        barista_notes = "Adjusted caramelized modifiers to Vanilla Syrup to avoid clashing with the bright, high-acidity/citrus profile of the coffee base."
    elif body_dilution:
        barista_notes = "Low aggregate body intensity detected. Dairy volume penalized by 10% to preserve coffee flavor definition."

    # Construct final v3.0 JSON output format
    res_data = {
        "recipe_validation": validation_notes if validation_notes else recipe_validation,
        "drink_metrics": {
            "style": style_str,
            "cup_size_oz": cup_size_oz,
            "ice_space_reserved_oz": ice_volume_oz,
            "total_liquid_budget_oz": liquid_budget_oz
        },
        "ingredients": {
            "coffee_base": {
                "name": coffee_inputs[0].get('name', 'Espresso Extraction') if coffee_inputs else "Espresso Extraction",
                "shots": shot_count,
                "volume_oz": coffee_base_vol
            },
            "base_modifiers": base_modifiers_output,
            "payload_filler": {
                "name": dairy_name if secondary_liquid_vol > 0.0 else "None",
                "volume_oz": secondary_liquid_vol
            },
            "flavor_modifiers": flavor_modifiers_output,
            # backward compatibility keys for UI:
            "coffee_base_mix": [
                {
                    "name": coffee_inputs[idx].get('name', 'Coffee'),
                    "volume_oz": round(coffee_base_vol * ratios[idx], 2),
                    "percentage_of_liquid": round((coffee_base_vol * ratios[idx] / liquid_budget_oz) * 100, 2)
                }
                for idx in range(len(coffee_inputs))
            ] + ([
                {
                    "name": "Hot Water",
                    "volume_oz": hot_water_vol,
                    "percentage_of_liquid": round((hot_water_vol / liquid_budget_oz) * 100, 2)
                }
            ] if hot_water_vol > 0.0 else []),
            "dairy_or_filler": {
                "name": dairy_name if secondary_liquid_vol > 0.0 else "None",
                "volume_oz": secondary_liquid_vol,
                "percentage_of_liquid": round((secondary_liquid_vol / liquid_budget_oz) * 100, 2)
            },
            "modifiers": [
                {
                    "name": m["name"],
                    "volume_oz": m["volume_oz"],
                    "percentage_of_liquid": round((m["volume_oz"] / liquid_budget_oz) * 100, 2)
                }
                for m in flavor_modifiers_output
            ]
        },
        "barista_notes": barista_notes,
        # backward compatibility keys for UI:
        "aggregate_base_metrics": {
            "calculated_body": calculated_body,
            "calculated_acidity": calculated_acidity,
            "calculated_bitterness": calculated_bitterness,
            "combined_notes": combined_notes
        },
        "ice_volume_oz": ice_volume_oz,
        "liquid_budget_oz": liquid_budget_oz,
        "hot_water_volume_oz": hot_water_vol
    }

    return JsonResponse(res_data)
