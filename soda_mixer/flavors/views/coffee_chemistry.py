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
    has_seen_dairy = False

    for idx, ing in enumerate(ingredients_input):
        itype = str(ing.get('ingredient_type', ing.get('type', ''))).upper()
        if itype == 'COFFEE_BEAN':
            coffee_inputs.append(ing)
        elif itype == 'DAIRY':
            if has_seen_dairy:
                modifier_inputs.append(ing)
            else:
                dairy_inputs.append(ing)
                has_seen_dairy = True
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

    # Resolve Americano Toggle
    americano_toggle = data.get('americano_style', False) is True

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
    # Baseline modifier cap: 15% of liquid budget.
    # Sweetness Safety Valve: 10% cap if num_modifiers > 1 OR combined_swe > 5.
    if num_modifiers > 1 or combined_swe > 5:
        modifier_cap_pct = 0.10
    else:
        modifier_cap_pct = 0.15

    # Cold Sugar Tax: expand modifier cap by absolute +2% if drink style is Iced.
    if "iced" in drink_cat_lower:
        modifier_cap_pct += 0.02

    modifier_cap = liquid_budget_oz * modifier_cap_pct

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
                "id": modified_list[0].get('id'),
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
                    "id": m.get('id'),
                    "name": f"{name} {role}",
                    "volume_oz": round(vol, 2)
                })

    # Viscosity Protection
    is_thin_warning = False
    if num_modifiers > 0 and calculated_bitterness >= 4:
        all_syrups = True
        for m in modified_list:
            name_lower = m.get('name', '').lower()
            desc_lower = str(m.get('description', '')).lower() if m.get('description') else ''
            if 'sauce' in name_lower or 'sauce' in desc_lower:
                all_syrups = False
                break
        if all_syrups:
            is_thin_warning = True

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
            if americano_toggle:
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

    # Fat Buffer Requirement
    fat_content_score = 3
    if dairy_inputs:
        payload_ing = dairy_inputs[0]
        if 'fat_content_score' in payload_ing:
            fat_content_score = int(payload_ing['fat_content_score'])
        elif 'fat_content' in payload_ing:
            fat_content_score = int(payload_ing['fat_content'])
        else:
            p_name = payload_ing.get('name', '').lower()
            if 'cream' in p_name or 'half' in p_name:
                fat_content_score = 4
            elif 'whole' in p_name or 'dairy' in p_name:
                fat_content_score = 3
            elif 'skim' in p_name or 'nonfat' in p_name or 'fat free' in p_name:
                fat_content_score = 1
            elif 'oat' in p_name or 'almond' in p_name or 'soy' in p_name or 'coconut' in p_name or 'plant' in p_name:
                fat_content_score = 2

    is_fat_buffer_warning = False
    if calculated_bitterness >= 4 and len(dairy_inputs) > 0 and fat_content_score < 3:
        is_fat_buffer_warning = True

    # Dairy or Filler baseline name determination
    dairy_name = dairy_inputs[0].get('name', 'Whole Milk') if dairy_inputs else ("Hot Water" if not is_espresso_base and not dairy_inputs else "Whole Milk")

    # Autonomic Mouthfeel Correction Protocol (Action Override)
    is_corrected = False
    primary_filler_name = dairy_name
    primary_filler_vol = secondary_liquid_vol
    texturizer_vol = 0.0
    texturizer_name = "Heavy Cream"

    if is_thin_warning and secondary_liquid_vol > 0.0 and dairy_name != "Hot Water":
        # Check if texturizer is manually selected
        has_manual_texturizer = any(
            "heavy cream" in str(m.get('name', '')).lower() or "half-and-half" in str(m.get('name', '')).lower() or "half and half" in str(m.get('name', '')).lower()
            for m in modifier_inputs
        )
        if has_manual_texturizer:
            is_corrected = False
            # Suppress alerts since it has been manually overridden and resolved
            is_thin_warning = False
            is_fat_buffer_warning = False
        else:
            is_corrected = True
            texturizer_vol = round(secondary_liquid_vol * 0.20, 2)
            primary_filler_vol = round(secondary_liquid_vol - texturizer_vol, 2)
            
            # Suppress alerts since they have been programmatically resolved
            is_thin_warning = False
            is_fat_buffer_warning = False

    # pH Curdling Protection
    citrus_fruit_keywords = {'citrus', 'lemon', 'lime', 'orange', 'grapefruit', 'cherry', 'fruit', 'fruity', 'berry', 'berries', 'raspberry', 'strawberry', 'blueberry', 'blackberry', 'hibiscus'}
    has_citrus_modifier = False
    for m in modified_list:
        if m.get('category') in ['citrus', 'berry', 'sour']:
            has_citrus_modifier = True
            break
        name_lower = m.get('name', '').lower()
        notes_lower = str(m.get('flavor_notes', '')).lower()
        desc_lower = str(m.get('description', '')).lower() if m.get('description') else ''
        if any(kw in name_lower or kw in notes_lower or kw in desc_lower for kw in citrus_fruit_keywords):
            has_citrus_modifier = True
            break

    is_curdling_risk = False
    if "iced" not in drink_cat_lower and len(dairy_inputs) > 0:
        if calculated_acidity >= 4 or has_citrus_modifier:
            is_curdling_risk = True

    # Gather Warnings and Failures
    warnings = []
    if flavor_clash:
        warnings.append("Warning: High-acidity blend may clash with caramelized syrups. Modifiers adjusted to neutral profiles.")
    if body_dilution:
        warnings.append("Warning: Low aggregate body intensity detected.")
    if is_thin_warning:
        warnings.append("Warning: Bitterness score >= 4 combined with thin syrups may result in a watery mouthfeel. Recommending a sauce modifier or a higher fat payload.")
    if is_fat_buffer_warning:
        warnings.append("Warning: Low-fat payload may not properly mask coffee bitterness.")

    if is_curdling_risk:
        recipe_validation = "Fail: High acidity poses a milk curdling risk under hot configurations."
    elif warnings:
        recipe_validation = " ".join(warnings)
    else:
        recipe_validation = "Pass"

    # Round final volumes
    coffee_base_vol = round(coffee_base_vol, 2)
    secondary_liquid_vol = round(secondary_liquid_vol, 2)
    hot_water_vol = round(hot_water_vol, 2)
    if is_corrected:
        primary_filler_vol = round(primary_filler_vol, 2)
        texturizer_vol = round(texturizer_vol, 2)

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

    def format_list_with_and(items: List[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + f", and {items[-1]}"

    # Barista Notes & Prepare Step-by-Step Preparation Steps (Solubility)
    prep_steps = []
    
    # Check for dry reagents (powder)
    has_powder = any(ing.get('is_dry') or 'powder' in str(ing.get('name', '')).lower() for ing in modifier_inputs)
    
    # Step 1: Modifiers
    mod_items = []
    for m in flavor_modifiers_output:
        # Find the original input ingredient to check if it is dry
        orig = next((ing for ing in modifier_inputs if ing.get('id') == m['id']), None)
        is_dry_modifier = False
        if orig:
            is_dry_modifier = orig.get('is_dry') or 'powder' in str(orig.get('name', '')).lower()
        
        m_name = m['name'].split(' (')[0]
        if is_dry_modifier:
            m_amt = orig.get('amount', 0.0)
            mod_items.append(f"{m_amt:.0f}g of {m_name}")
        else:
            m_oz = m['volume_oz']
            m_ml = round(m_oz * 29.5735)
            mod_items.append(f"{m_ml}ml ({m_oz:.2f}oz) of {m_name}")
            
    if mod_items:
        step_1_text = f"Dispense {format_list_with_and(mod_items)} into the base of a {cup_size_oz:.0f}oz vessel."
    else:
        step_1_text = f"Prepare a {cup_size_oz:.0f}oz vessel."
    prep_steps.append(f"Step 1: {step_1_text}")
    
    # Step 2: Coffee Base
    coffee_names = [c.get('name', 'Espresso') for c in coffee_inputs]
    if len(coffee_names) > 1:
        coffee_desc = f"the {'/'.join(coffee_names)} blend"
    elif coffee_names:
        coffee_desc = coffee_names[0]
    else:
        coffee_desc = "the espresso base"
        
    target_action = "directly over the modifiers" if mod_items else "directly into the vessel"
    
    if is_espresso_base:
        if has_powder:
            step_2_text = f"Extract {shot_count} shots ({coffee_base_vol:.1f}oz total) of {coffee_desc} {target_action}. Stir thoroughly to agitate and dissolve the powder."
        else:
            step_2_text = f"Extract {shot_count} shots ({coffee_base_vol:.1f}oz total) of {coffee_desc} {target_action} and agitate."
    else:
        coffee_base_vol_ml = round(coffee_base_vol * 29.5735)
        if has_powder:
            step_2_text = f"Pour {coffee_base_vol_ml}ml ({coffee_base_vol:.1f}oz) of brewed {coffee_desc} {target_action}. Stir thoroughly to agitate and dissolve the powder."
        else:
            step_2_text = f"Pour {coffee_base_vol_ml}ml ({coffee_base_vol:.1f}oz) of brewed {coffee_desc} {target_action} and agitate."
    prep_steps.append(f"Step 2: {step_2_text}")
    
    # Step 3: Payload
    is_plant_milk = False
    for d in dairy_inputs:
        name_lower = str(d.get('name', '')).lower()
        if any(plant_keyword in name_lower for plant_keyword in ['oat', 'almond', 'soy', 'plant', 'coconut', 'cashew']):
            is_plant_milk = True
            break
            
    if "iced" not in drink_cat_lower:
        if is_corrected:
            pri_ml = round(primary_filler_vol * 29.5735)
            tex_ml = round(texturizer_vol * 29.5735)
            step_3_text = f"Incorporate {pri_ml}ml ({primary_filler_vol:.2f}oz) of steamed {primary_filler_name} and {tex_ml}ml ({texturizer_vol:.2f}oz) of steamed {texturizer_name} (steam to a temperature ceiling of 140°F)."
        else:
            filler_vol_ml = round(secondary_liquid_vol * 29.5735)
            temp_ceiling = 130 if is_plant_milk else 140
            step_3_text = f"Incorporate {filler_vol_ml}ml ({secondary_liquid_vol:.2f}oz) of steamed {dairy_name} (steam to a temperature ceiling of {temp_ceiling}°F)."
    else:
        if is_corrected:
            pri_ml = round(primary_filler_vol * 29.5735)
            tex_ml = round(texturizer_vol * 29.5735)
            step_3_text = f"Pour in {pri_ml}ml ({primary_filler_vol:.2f}oz) of cold {primary_filler_name} and {tex_ml}ml ({texturizer_vol:.2f}oz) of cold {texturizer_name}."
        else:
            filler_vol_ml = round(secondary_liquid_vol * 29.5735)
            step_3_text = f"Pour in {filler_vol_ml}ml ({secondary_liquid_vol:.2f}oz) of cold {dairy_name}."
    prep_steps.append(f"Step 3: {step_3_text}")
    
    # Step 4: Ice
    if "iced" in drink_cat_lower:
        ice_str = f"{int(ice_volume_oz)}oz" if ice_volume_oz.is_integer() else f"{ice_volume_oz:.1f}oz"
        prep_steps.append(f"Step 4: Top with {ice_str} of clean ice to complete the compound.")

    barista_notes = "Extraction and chemistry parameters are balanced. Serve and enjoy!"
    if is_curdling_risk:
        barista_notes = "Curdling Risk: High acidity poses a milk curdling risk under hot configurations."
    elif is_corrected:
        barista_notes = f"Autonomic Mouthfeel Correction Protocol activated: Bitter coffee base combined with thin syrups detected. Re-engineered the payload to include a 20% splash of {texturizer_name} to optimize texture and mask bitterness."
    elif "iced" in drink_cat_lower:
        if is_espresso_base:
            barista_notes = "Hot espresso melts ice rapidly; consider pulling shots over ice directly to manage dilution."
        else:
            barista_notes = "Standard brew is more easily washed out than espresso; keep dairy below 20% to preserve texture."
    elif flavor_clash:
        barista_notes = "Adjusted caramelized modifiers to Vanilla Syrup to avoid clashing with the bright, high-acidity/citrus profile of the coffee base."
    elif body_dilution:
        barista_notes = "Low aggregate body intensity detected. Dairy volume penalized by 10% to preserve coffee flavor definition."
    elif is_thin_warning:
        barista_notes = "Bitterness score >= 4 combined with thin syrups may result in a watery mouthfeel. Recommending a sauce modifier or a higher fat payload."

    dairy_id = dairy_inputs[0].get('id') if dairy_inputs else None

    payload_filler_data = {
        "id": dairy_id,
        "name": dairy_name if secondary_liquid_vol > 0.0 else "None",
        "volume_oz": secondary_liquid_vol
    }
    if is_corrected and secondary_liquid_vol > 0.0:
        pri_ml = round(primary_filler_vol * 29.5735)
        tex_ml = round(texturizer_vol * 29.5735)
        payload_filler_data = {
            "id": dairy_id,
            "name": f"{dairy_name}: {pri_ml}ml (Primary Filler) and Heavy Cream: {tex_ml}ml (Texture Anchor)",
            "volume_oz": secondary_liquid_vol,
            "is_corrected": True,
            "primary_name": dairy_name,
            "primary_volume_oz": primary_filler_vol,
            "texturizer_name": "Heavy Cream",
            "texturizer_volume_oz": texturizer_vol
        }

    dairy_or_filler_data = {
        "id": dairy_id,
        "name": dairy_name if secondary_liquid_vol > 0.0 else "None",
        "volume_oz": secondary_liquid_vol,
        "percentage_of_liquid": round((secondary_liquid_vol / liquid_budget_oz) * 100, 2)
    }
    if is_corrected and secondary_liquid_vol > 0.0:
        dairy_or_filler_data = {
            "id": dairy_id,
            "name": payload_filler_data["name"],
            "volume_oz": secondary_liquid_vol,
            "percentage_of_liquid": round((secondary_liquid_vol / liquid_budget_oz) * 100, 2),
            "is_corrected": True,
            "primary_name": dairy_name,
            "primary_volume_oz": primary_filler_vol,
            "texturizer_name": "Heavy Cream",
            "texturizer_volume_oz": texturizer_vol
        }

    # Construct final JSON output format
    res_data = {
        "recipe_validation": recipe_validation,
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
            "payload_filler": payload_filler_data,
            "flavor_modifiers": flavor_modifiers_output,
            # backward compatibility keys for UI:
            "coffee_base_mix": [
                {
                    "id": coffee_inputs[idx].get('id'),
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
            "dairy_or_filler": dairy_or_filler_data,
            "modifiers": [
                {
                    "id": m.get("id"),
                    "name": m["name"],
                    "volume_oz": m["volume_oz"],
                    "percentage_of_liquid": round((m["volume_oz"] / liquid_budget_oz) * 100, 2)
                }
                for m in flavor_modifiers_output
            ]
        },
        "barista_notes": barista_notes,
        "preparation_steps": prep_steps,
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
