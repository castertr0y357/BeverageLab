"""Cryo-Synthesis Engine API view."""

import json
import logging
from typing import Dict, Any, List
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from ..engines.base import BaseChemistryEngine

logger = logging.getLogger(__name__)

def get_cryo_sugar_fraction(name: str, type_str: str, physical_state: str = "", mixology_function: str = "") -> float:
    """Evaluate sugar mass contribution fraction by volume."""
    name_lower = name.lower()
    type_upper = type_str.upper()
    pstate = physical_state.upper()
    mfunc = mixology_function.upper()
    
    # 1. Raw Honey (80%)
    if 'honey' in name_lower:
        return 0.80
    
    # 2. Pure Fruit Juices (10%)
    if 'juice' in name_lower:
        return 0.10
        
    # 3. Water (0%) / Coconut Water (3%)
    if 'coconut water' in name_lower:
        return 0.03
    if 'water' in name_lower:
        return 0.0
        
    # 4. Monin Syrups (65%)
    # Ginger Beer explicitly treated as dense flavor syrup reagent
    if 'ginger beer' in name_lower or 'syrup' in name_lower or 'sauce' in name_lower or type_upper == 'SODA_SYRUP' or pstate in ['SYRUP', 'SAUCE']:
        return 0.65
        
    if type_upper == 'ADDITIVE' or mfunc in ['FLAVORING', 'SWEETENER', 'TEXTURIZER']:
        return 0.65
    return 0.0

class CryoChemistryEngine(BaseChemistryEngine):
    def __init__(self, ingredients_input: List[Dict[str, Any]], bottle_scale: float):
        super().__init__(ingredients_input)
        self.bottle_scale = bottle_scale
        if self.bottle_scale <= 0.0:
            self.bottle_scale = 1.0

    def process(self) -> Dict[str, Any]:
        # 1. Hardware Volumetric Boundaries (Ninja Slushi)
        if abs(self.bottle_scale - 0.5) < 0.01:
            target_volume_ml = 473.0
            target_label = "16oz Batch"
        elif abs(self.bottle_scale - 1.5) < 0.01:
            target_volume_ml = 1420.0
            target_label = "48oz Batch"
        elif abs(self.bottle_scale - 2.0) < 0.01:
            target_volume_ml = 1892.0
            target_label = "64oz Batch"
        else:
            target_volume_ml = 946.0  # 32oz Batch (1.0)
            target_label = "32oz Batch"

        menthol_cap_ml = 0.03 * target_volume_ml

        # State Safety Verification - Carbonation Hard-Ban
        for ing in self.ingredients_input:
            name = ing.get('name', 'Ingredient')
            name_lower = name.lower()
            if 'ginger beer' in name_lower:
                continue
            carbonation_keywords = ['soda', 'cola', 'sprite', 'carbonated', 'tonic', 'fizz', 'sparkling', 'pop', 'ginger ale']
            if any(kw in name_lower for kw in carbonation_keywords):
                logger.warning(f"CryoChemistry - Warning - Carbonation detected in slushie recipe: {name}")
                return {
                    "recipe_validation": "Fail: Carbonation Hard-Ban. Carbonated liquids are structurally barred from CryoLab calculations due to physical degassing and pocket-void collapsing during the auger rotation cycle.",
                    "drink_metrics": {
                        "style": "Slushie",
                        "batch_scale": self.bottle_scale,
                        "target_volume_ml": target_volume_ml,
                        "achieved_brix": 0.0,
                        "total_syrup_volume_ml": 0.0,
                        "filler_volume_ml": 0.0
                    },
                    "ingredients": {
                        "filler": {"name": "None", "volume_ml": 0.0},
                        "modifiers": []
                    },
                    "mixologist_notes": " auger failure: Carbonated reactants detected.",
                    "preparation_steps": [],
                    "extraction_analysis": {"sweetness": 0.0, "acidity": 1.0, "bitterness": 1.0}
                }

        # Partition ingredients into Modifier vs Filler
        modifiers = []
        filler_ing = None

        for ing in self.ingredients_input:
            name = ing.get('name', 'Ingredient')
            name_lower = name.lower()
            is_rtd = (
                ing.get('mixology_function', '').upper() == 'VOLUME_BASE'
                or ing.get('is_ready_to_drink', False)
                or ing.get('isReadyToDrink', False)
            )
            is_virtual_water = ing.get('id') == 'virtual_water'
            
            if is_rtd or is_virtual_water or 'water' in name_lower or 'juice' in name_lower:
                if not filler_ing:
                    filler_ing = ing
                    continue
            modifiers.append(ing)

        # Fallback filler if none is present
        if not filler_ing:
            filler_ing = {
                'id': 'virtual_water',
                'name': 'Water',
                'ingredient_type': 'OTHER',
                'is_ready_to_drink': True
            }

        # Evaluate modifiers sugar mass and volumes
        modifier_volumes = []
        is_solitary = (len(modifiers) == 1)

        for ing in modifiers:
            name = ing.get('name', 'Syrup')
            itype = ing.get('ingredient_type', ing.get('type', 'SODA_SYRUP'))
            sweetness = int(ing.get('sweetness_score', ing.get('sweetness', 3)))
            
            is_user_overridden = ing.get('isUserOverridden', False) or ing.get('is_user_overridden', False)
            amt = float(ing.get('amount', 0.0)) if is_user_overridden else 0.0
            
            if is_solitary and not is_user_overridden:
                filler_name = filler_ing.get('name', 'Water')
                filler_type = filler_ing.get('ingredient_type', filler_ing.get('type', 'OTHER'))
                filler_sugar_frac = get_cryo_sugar_fraction(
                    filler_name, 
                    filler_type, 
                    filler_ing.get('physical_state', ''), 
                    filler_ing.get('mixology_function', '')
                )
                
                sugar_frac = get_cryo_sugar_fraction(
                    name, 
                    itype, 
                    ing.get('physical_state', ''), 
                    ing.get('mixology_function', '')
                )
                sugar_diff = sugar_frac - filler_sugar_frac
                if abs(sugar_diff) > 0.001:
                    required_vol = (0.13 - filler_sugar_frac) * target_volume_ml / sugar_diff
                else:
                    required_vol = 80.0 * self.bottle_scale
                
                if sweetness >= 4:
                    scaled_amt = required_vol / 1.05
                else:
                    scaled_amt = required_vol
            else:
                if not amt:
                    idx = len(modifier_volumes)
                    amt = 80.0 if idx == 0 else (40.0 if idx == 1 else 20.0)

                # Scale by bottle_scale
                scaled_amt = amt * self.bottle_scale

            # Apply Cryo-Sweetness Tax
            if sweetness >= 4:
                scaled_amt *= 1.05

            sugar_frac = get_cryo_sugar_fraction(
                name, 
                itype, 
                ing.get('physical_state', ''), 
                ing.get('mixology_function', '')
            )

            modifier_volumes.append({
                'ing': ing,
                'volume': scaled_amt,
                'sugar_fraction': sugar_frac
            })

        # Solver equation:
        scaled_mods = list(modifier_volumes)
        fixed_mods = []
        filler_name = filler_ing.get('name', 'Water')
        filler_type = filler_ing.get('ingredient_type', filler_ing.get('type', 'OTHER'))
        filler_sugar_frac = get_cryo_sugar_fraction(
            filler_name, 
            filler_type, 
            filler_ing.get('physical_state', ''), 
            filler_ing.get('mixology_function', '')
        )
        k = 1.0

        for _ in range(3):
            fixed_sugar_mass = sum(m['volume'] * m['sugar_fraction'] for m in fixed_mods)
            fixed_volume = sum(m['volume'] for m in fixed_mods)

            scaled_sugar_mass_base = sum(m['volume'] * m['sugar_fraction'] for m in scaled_mods)
            scaled_volume_base = sum(m['volume'] for m in scaled_mods)

            numerator = (0.13 - filler_sugar_frac) * target_volume_ml - fixed_sugar_mass + fixed_volume * filler_sugar_frac
            denominator = scaled_sugar_mass_base - (scaled_volume_base * filler_sugar_frac)

            if abs(denominator) > 0.001:
                k = numerator / denominator
            else:
                k = 1.0

            if k <= 0.0 or k > 10.0:
                k = 1.0

            cap_exceeded = False
            for m in list(scaled_mods):
                name_lower = m['ing'].get('name', '').lower()
                if 'mint' in name_lower or 'menthol' in name_lower:
                    final_vol = m['volume'] * k
                    if final_vol > menthol_cap_ml:
                        m_fixed = m.copy()
                        m_fixed['volume'] = menthol_cap_ml
                        fixed_mods.append(m_fixed)
                        scaled_mods.remove(m)
                        cap_exceeded = True
                        break

            if not cap_exceeded:
                break

        scaled_modifier_volume = 0.0
        scaled_modifier_sugar = 0.0
        modifiers_output = []

        for mv in modifier_volumes:
            is_fixed = False
            final_vol = 0.0
            for fm in fixed_mods:
                if fm['ing'].get('id') == mv['ing'].get('id'):
                    final_vol = fm['volume']
                    is_fixed = True
                    break
            if not is_fixed:
                final_vol = mv['volume'] * k

            scaled_modifier_volume += final_vol
            scaled_modifier_sugar += final_vol * mv['sugar_fraction']

            modifiers_output.append({
                "id": mv['ing'].get('id'),
                "name": mv['ing'].get('name'),
                "volume_ml": round(final_vol, 1),
                "percentage_of_batch": round((final_vol / target_volume_ml) * 100, 1),
                "role": "Flavor Modifier"
            })

        filler_volume = max(0.0, target_volume_ml - scaled_modifier_volume)

        actual_sugar_mass = scaled_modifier_sugar + (filler_volume * filler_sugar_frac)
        achieved_brix = (actual_sugar_mass / target_volume_ml) * 100

        validation_status = "Pass"
        if achieved_brix < 12.0:
            validation_status = f"Fail: Sugar density check failed. Achieved brix of {achieved_brix:.1f}% is below freezing threshhold (min 12%). Mixture may lock auger."
        elif achieved_brix > 14.0:
            validation_status = f"Fail: Sugar density check failed. Achieved brix of {achieved_brix:.1f}% is above freezing threshhold (max 14%). Slushie will not freeze."

        prep_steps = [
            "Step 1: Combine the calculated volumes of flavor syrups and modifiers into a large mixing pitcher.",
            f"Step 2: Add exactly {filler_volume:.0f}ml of {filler_name} to the pitcher. Whisk vigorously for 30-45 seconds to achieve full molecular suspension.",
            "Step 3: Pour the combined mixture directly into the Ninja Slushi physical reservoir tank.",
            "Step 4: Select the Slushie mode on the control panel, adjust the temperature setting to level 3, and freeze for 45-60 minutes."
        ]

        all_items = modifiers_output + [{
            "id": filler_ing.get('id'),
            "name": filler_name,
            "volume_ml": filler_volume
        }]

        metrics = self.calculate_metrics(all_items)
        # Cryo-specific sweetness adjustment:
        # Re-calculate to match cryo sweetness tax if sweet >= 4.0
        # Wait, calculate_metrics just does raw calculation, let's keep it simple.
        
        # We need to manually adjust cryo sweetness boost
        weighted_sweetness = 0.0
        total_weights = 0.0
        for item in all_items:
            vol = item.get('volume_ml', 0.0)
            if vol <= 0.0: continue
            orig = next((i for i in self.ingredients_input if i.get('id') == item.get('id')), None)
            if not orig and item.get('id') == 'virtual_water':
                orig = {'sweetness': 1}
            if orig:
                sweet = float(orig.get('sweetness_score', orig.get('sweetness', 3.0)))
                if sweet >= 4.0:
                    sweet += 0.5
                weighted_sweetness += sweet * vol
                total_weights += vol
                
        if total_weights > 0.0:
            metrics['sweetness'] = round(weighted_sweetness / total_weights, 2)

        mixologist_notes = f"Freezing profile synthesized for {target_label} with sugar density calibrated to {achieved_brix:.2f}% Brix."
        if validation_status != "Pass":
            mixologist_notes = "Auger speed caution! Sugar density is outside physical thresholds. Freezing cycle suspended."

        return {
            "recipe_validation": validation_status,
            "drink_metrics": {
                "style": "Slushie",
                "batch_scale": self.bottle_scale,
                "target_volume_ml": round(target_volume_ml, 1),
                "achieved_brix": round(achieved_brix, 2),
                "total_syrup_volume_ml": round(scaled_modifier_volume, 1),
                "filler_volume_ml": round(filler_volume, 1)
            },
            "ingredients": {
                "filler": {
                    "name": filler_name,
                    "volume_ml": round(filler_volume, 1)
                },
                "modifiers": modifiers_output
            },
            "mixologist_notes": mixologist_notes,
            "preparation_steps": prep_steps,
            "extraction_analysis": metrics
        }

@csrf_exempt
@require_http_methods(["POST"])
def cryo_chemistry_api(request: HttpRequest) -> JsonResponse:
    """
    Ingest slushie ingredients and calculate dynamic volumes to achieve exactly 13% Brix.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as e:
        logger.warning(f"CryoChemistry - Warning - Invalid JSON payload: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    bottle_scale = float(data.get('bottle_scale', 1.0))
    ingredients_input = data.get('ingredients', [])

    engine = CryoChemistryEngine(ingredients_input, bottle_scale)
    res_data = engine.process()

    return JsonResponse(res_data)
