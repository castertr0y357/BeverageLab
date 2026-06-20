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

    hot_water_vol = 0.0
    if is_espresso_base and not is_short_milk and "iced" not in drink_cat_lower and espresso_hot_mode == 'water':
        hot_water_vol = round(cup_size_oz * 0.40, 2)

    # 1. Volumetric Budget Rules
    if "iced" in drink_cat_lower:
        ice_volume_oz = round(cup_size_oz * 0.40, 2)
        liquid_budget_oz = round(cup_size_oz * 0.60, 2)
    else:
        ice_volume_oz = 0.0
        liquid_budget_oz = cup_size_oz

    # Partition ingredients by role
    coffee_inputs = []
    dairy_inputs = []
    modifier_inputs = []

    for ing in ingredients_input:
        itype = str(ing.get('ingredient_type', '')).upper()
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
            "aggregate_base_metrics": {
                "calculated_body": 0.0,
                "calculated_acidity": 0.0,
                "calculated_bitterness": 0.0,
                "combined_notes": []
            },
            "ice_volume_oz": ice_volume_oz,
            "liquid_budget_oz": liquid_budget_oz,
            "ingredients": {
                "coffee_base_mix": [],
                "dairy_or_filler": {"name": "None", "volume_oz": 0.0, "percentage_of_liquid": 0.0},
                "modifiers": []
            },
            "barista_notes": "Decommissioned: Formula lacks active extraction baseline."
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
    # Sum modifier requested volumes, default to 10% of liquid budget if not specified
    requested_modifier_total = 0.0
    has_modifier_amounts = False
    for m in modified_list:
        amt = m.get('amount')
        if amt is not None:
            requested_modifier_total += float(amt)
            has_modifier_amounts = True

    if not has_modifier_amounts:
        # Default to 10% of liquid budget total
        modifier_budget = liquid_budget_oz * 0.10 if modified_list else 0.0
    else:
        modifier_budget = requested_modifier_total

    # Strict Cap at 15% maximum
    max_modifier_cap = liquid_budget_oz * 0.15
    if modifier_budget > max_modifier_cap:
        modifier_budget = max_modifier_cap

    # Execute the Flavor Hierarchy Protocol if there are multiple syrups
    modifiers_output = []
    if modified_list:
        if len(modified_list) == 1:
            # Only one syrup, gets 100% of budget
            name = modified_list[0].get('name', 'Syrup')
            modifiers_output.append({
                "name": f"{name} (Dominant)",
                "volume_oz": round(modifier_budget, 2),
                "percentage_of_liquid": round((modifier_budget / liquid_budget_oz) * 100, 2)
            })
        else:
            # Score compatibility against aggregate profile
            # Dark/Chocolaty aggregates
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

            # Sort by score descending, breaking ties by index (first in list)
            mod_scores.sort(key=lambda x: (x[0], -x[1]), reverse=True)
            dominant_idx = mod_scores[0][1]

            if has_modifier_amounts and requested_modifier_total > 0.0:
                for idx, m in enumerate(modified_list):
                    amt = float(m.get('amount', 0.0))
                    vol = (amt / requested_modifier_total) * modifier_budget
                    role = "(Dominant)" if idx == dominant_idx else "(Accent)"
                    modifiers_output.append({
                        "name": f"{m.get('name', 'Syrup')} {role}",
                        "volume_oz": round(vol, 2),
                        "percentage_of_liquid": round((vol / liquid_budget_oz) * 100, 2)
                    })
            else:
                # Dominant modifier gets 60%
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
                    
                    modifiers_output.append({
                        "name": f"{name} {role}",
                        "volume_oz": round(vol, 2),
                        "percentage_of_liquid": round((vol / liquid_budget_oz) * 100, 2)
                    })

    # 4. Base-Specific Processing Guardrails
    if is_short_milk:
        if not is_espresso_base:
            recipe_validation = "Warning"
            validation_notes = "Warning: Standard Brew is incompatible with Pure Espresso / Short Milk format."
        
        # Espresso Shots only.
        if dairy_inputs:
            coffee_base_pct = 40.0
        else:
            coffee_base_pct = 100.0
    else:
        if is_espresso_base:
            # Route A: Espresso concentrate
            if "iced" not in drink_cat_lower and espresso_hot_mode == 'water':
                coffee_base_pct = 18.0
            else:
                coffee_base_pct = 30.0 # Midpoint of 25%-35%
        else:
            # Route B: Standard Brew
            if "iced" in drink_cat_lower:
                coffee_base_pct = 80.0 # Midpoint of 75%-80%
            else:
                coffee_base_pct = 90.0 # Midpoint of 85%-95%

    coffee_base_vol = liquid_budget_oz * (coffee_base_pct / 100.0)
    
    # Calculate secondary liquid (dairy/filler)
    secondary_liquid_vol = liquid_budget_oz - coffee_base_vol - modifier_budget - hot_water_vol
    if secondary_liquid_vol < 0.0:
        secondary_liquid_vol = 0.0

    # Apply Route A thermal dilution factor (Iced Espresso only)
    if is_espresso_base and "iced" in drink_cat_lower and not is_short_milk:
        secondary_liquid_vol = secondary_liquid_vol * 0.9

    # Apply Body Dilution penalty (reduce total dairy volume by 10%)
    if body_dilution:
        secondary_liquid_vol = secondary_liquid_vol * 0.9
        if recipe_validation == "Pass":
            recipe_validation = "Warning"
            validation_notes = "Warning: Low aggregate body intensity (< 3.5). Dairy threshold reduced to prevent masking."

    # Round volumes
    coffee_base_vol = round(coffee_base_vol, 2)
    secondary_liquid_vol = round(secondary_liquid_vol, 2)

    # Assign individual coffee component volumes
    coffee_base_mix_output = []
    for idx, c in enumerate(coffee_inputs):
        ratio = ratios[idx]
        vol = coffee_base_vol * ratio
        coffee_base_mix_output.append({
            "name": c.get('name', 'Coffee'),
            "volume_oz": round(vol, 2),
            "percentage_of_liquid": round((vol / liquid_budget_oz) * 100, 2)
        })

    if hot_water_vol > 0.0:
        coffee_base_mix_output.append({
            "name": "Hot Water",
            "volume_oz": round(hot_water_vol, 2),
            "percentage_of_liquid": round((hot_water_vol / liquid_budget_oz) * 100, 2)
        })

    # Dairy or Filler formatting
    dairy_name = dairy_inputs[0].get('name', 'Whole Milk') if dairy_inputs else ("Hot Water" if not is_espresso_base and not dairy_inputs else "Whole Milk")
    dairy_output = {
        "name": dairy_name if secondary_liquid_vol > 0.0 else "None",
        "volume_oz": round(secondary_liquid_vol, 2),
        "percentage_of_liquid": round((secondary_liquid_vol / liquid_budget_oz) * 100, 2)
    }

    # 5. Barista Notes
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

    # Final response structure
    res_data = {
        "recipe_validation": validation_notes if validation_notes else recipe_validation,
        "aggregate_base_metrics": {
            "calculated_body": calculated_body,
            "calculated_acidity": calculated_acidity,
            "calculated_bitterness": calculated_bitterness,
            "combined_notes": combined_notes
        },
        "ice_volume_oz": ice_volume_oz,
        "liquid_budget_oz": liquid_budget_oz,
        "hot_water_volume_oz": round(hot_water_vol, 2),
        "ingredients": {
            "coffee_base_mix": coffee_base_mix_output,
            "dairy_or_filler": dairy_output,
            "modifiers": modifiers_output
        },
        "barista_notes": barista_notes
    }

    return JsonResponse(res_data)
