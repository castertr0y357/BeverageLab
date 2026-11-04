import os
import requests
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional, Union, Generator

from ..models import LLMProvider, SystemConfiguration

logger = logging.getLogger(__name__)



class AIGenerationMixin:
    @classmethod
    def suggest_autonomous(cls, ingredients: List[str], mode: str = 'standard', drink_type: str = 'SODA', inventory: Optional[str] = None, exclude: Optional[List[str]] = None, retry_note: Optional[str] = None, force_type: Optional[str] = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
            """
            Generate multiple proactive suggestions as a structured JSON array.
            Returns 10 to 15 specific ingredient recommendations from the inventory.
            """
            drink_type = drink_type.upper()
            
            # Fallback if inventory is not passed explicitly
            if not inventory:
                inventory = cls.get_static_ingredients_context(drink_type=drink_type)
    
            # Look up detailed metadata for ingredients currently in the mix
            current_compound_details = []
            from ..models import Ingredient
            from django.db.models import Q
            
            for ing_name in ingredients:
                db_ing = Ingredient.objects.filter(Q(name__iexact=ing_name) | Q(brand__iexact=ing_name)).first()
                if not db_ing:
                    # Try cleaning up brand suffixes (e.g. "Vanilla (Monin)" -> "Vanilla")
                    cleaned_name = re.sub(r'\s*\([^)]*\)', '', ing_name).strip()
                    db_ing = Ingredient.objects.filter(Q(name__iexact=cleaned_name) | Q(brand__iexact=cleaned_name)).first()
                
                if db_ing:
                    ing_display = db_ing.name
                    profile_part = f", Profile: {db_ing.flavor_notes}" if db_ing.flavor_notes else ""
                    sensory_part = f", Sensory: {db_ing.ai_notes}" if db_ing.ai_notes else ""
                    if db_ing.ingredient_type == 'COFFEE_BEAN':
                        decaf_str = "Decaf" if db_ing.is_decaf else "Regular"
                        details = f"Type: {db_ing.ingredient_type}, Roast: {db_ing.roast_level}, {decaf_str}{profile_part}{sensory_part}"
                    else:
                        details = f"Type: {db_ing.ingredient_type}, Category: {db_ing.category}{profile_part}{sensory_part}"
                    current_compound_details.append(f"{ing_display} ({details})")
                else:
                    current_compound_details.append(ing_name)
                    
            current_compound_str = ", ".join(current_compound_details) if current_compound_details else "NONE - Initial Synthesis"
            
            force_rule = ""
            if force_type:
                force_display = "Dairy or Plant Milks" if force_type == 'DAIRY' else ("Creamers or Milks/Additives" if force_type == 'ADDITIVE' else force_type)
                force_rule = f"\nMANDATORY RULE: You must EXCLUSIVELY suggest new ingredients of type '{force_type}' (e.g., {force_display})."
                
            exclude_str = f"Exclude these previously suggested items: {', '.join(exclude)}." if exclude else "None"
    
            prompt = f"""[STRUCTURED DATA REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE].
    
    Task: Recommending between 10 to 15 compatible ingredients from the Inventory Registry to create/stabilize a drink compound. Prioritize ingredients marked with '*FAVORITE*'.
    
    [DYNAMIC REQUEST PARAMETERS]:
    Current Mode: {drink_type}
    Active Mixture: {current_compound_str}
    Force Type Constraint: {force_type or 'None'}{force_rule}
    Exclusion List: {exclude_str}
    
    Instruction: Analyze the active mixture '{current_compound_str}' and evaluate how all of its ingredients interact. Recommend items that complement the overall taste profile of the entire active mixture. For the 'reason' field, provide a detailed, vivid 15-25 word mixology explanation of exactly why the ingredient's flavor molecules synergize with the active compound.
    """
            if retry_note:
                prompt += f"\n[RETRY COMMAND]: {retry_note}\n"
    
            response = cls.chat(prompt, context=inventory, drink_type=drink_type, mode=mode)
            return cls._extract_json(response)

    @classmethod
    def suggest_autonomous_stream(cls, ingredients: List[str], mode: str = 'standard', drink_type: str = 'SODA', inventory: Optional[str] = None, exclude: Optional[List[str]] = None, exclude_types: Optional[List[str]] = None, retry_note: Optional[str] = None, force_type: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
            """
            Streaming version of suggest_autonomous. Yields individual parsed suggestion objects as they arrive, 
            and then yields a final 'complete' object containing the full structured response (rebalancing, reasoning).
            """
            drink_type = drink_type.upper()
            
            if not inventory:
                inventory = cls.get_static_ingredients_context(drink_type=drink_type)
    
            current_compound_details = []
            current_volume = 0.0
            from ..models import Ingredient
            from django.db.models import Q
            
            for ing_name in ingredients:
                db_ing = Ingredient.objects.filter(Q(name__iexact=ing_name) | Q(brand__iexact=ing_name)).first()
                if not db_ing:
                    cleaned_name = re.sub(r'\s*\([^)]*\)', '', ing_name).strip()
                    db_ing = Ingredient.objects.filter(Q(name__iexact=cleaned_name) | Q(brand__iexact=cleaned_name)).first()
                
                if db_ing:
                    ing_display = db_ing.name
                    profile_part = f", Profile: {db_ing.flavor_notes}" if db_ing.flavor_notes else ""
                    sensory_part = f", Sensory: {db_ing.ai_notes}" if db_ing.ai_notes else ""
                    if db_ing.ingredient_type == 'COFFEE_BEAN':
                        decaf_str = "Decaf" if db_ing.is_decaf else "Regular"
                        details = f"Type: {db_ing.ingredient_type}, Roast: {db_ing.roast_level}, {decaf_str}{profile_part}{sensory_part}"
                        current_volume += 18.0
                    else:
                        details = f"Type: {db_ing.ingredient_type}, Category: {db_ing.category}{profile_part}{sensory_part}"
                        if drink_type == 'COFFEE' and db_ing.mixology_function == 'VOLUME_BASE' and db_ing.physical_state == 'LIQUID':
                            current_volume += 50.0
                        elif drink_type == 'SLUSHIE' and db_ing.mixology_function == 'VOLUME_BASE':
                            current_volume += 80.0
                        elif drink_type == 'SLUSHIE' and db_ing.category == 'payload':
                            current_volume += 40.0
                        else:
                            current_volume += 15.0
                    current_compound_details.append(f"{ing_display} ({details})")
                else:
                    current_compound_details.append(ing_name)
                    if ing_name != "NONE - Initial Synthesis":
                        current_volume += 15.0
                    
            current_compound_str = ", ".join(current_compound_details) if current_compound_details else "NONE - Initial Synthesis"
            
            force_rule = ""
            if force_type:
                force_display = "Dairy or Plant Milks" if force_type == 'DAIRY' else ("Creamers or Milks/Additives" if force_type == 'ADDITIVE' else force_type)
                force_rule = f"\nMANDATORY RULE: You must EXCLUSIVELY suggest new ingredients of type '{force_type}' (e.g., {force_display})."
                
            if exclude_types:
                exclude_display = ", ".join(exclude_types)
                force_rule += f"\nMANDATORY RULE: You must NEVER suggest any ingredients of type: {exclude_display}."
                
            exclude_str = f"Exclude these previously suggested items: {', '.join(exclude)}." if exclude else "None"
            
            math_rule = ""
            if drink_type in ['SODA', 'SLUSHIE'] and current_compound_str != "NONE - Initial Synthesis":
                remaining = max(0.0, 160.0 - current_volume)
                math_rule = f"\nMATH GROUNDING: The active mixture currently uses approximately {current_volume}ml of volume. You have a strict remaining budget of {remaining}ml (Total max 160ml). Distribute this remaining budget across your suggestions."
            elif drink_type == 'COFFEE' and current_compound_str != "NONE - Initial Synthesis":
                math_rule = f"\nMATH GROUNDING: The active mixture uses approximately {current_volume} (g/ml). Follow the Core Synthesis Mode Rules for coffee ratios."
    
            prompt = f"""[STRUCTURED DATA REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE].
    
    Task: Recommending between 10 to 15 compatible ingredients from the Inventory Registry to create/stabilize a drink compound. Prioritize ingredients marked with '*FAVORITE*'.
    
    [DYNAMIC REQUEST PARAMETERS]:
    Current Mode: {drink_type}
    Active Mixture: {current_compound_str}
    Force Type Constraint: {force_type or 'None'}{force_rule}
    Exclusion List: {exclude_str}{math_rule}
    
    Instruction: Analyze the active mixture '{current_compound_str}' and evaluate how all of its ingredients interact. Recommend items that complement the overall taste profile of the entire active mixture. For the 'reason' field, provide a detailed, vivid 15-25 word mixology explanation of exactly why the ingredient's flavor molecules synergize with the active compound.
    """
            if retry_note:
                prompt += f"\n[RETRY COMMAND]: {retry_note}\n"
    
            stream = cls.chat_stream(prompt, context=inventory, drink_type=drink_type, mode=mode)
            
            buffer = ""
            yielded_names = set()
            
            for event in stream:
                # event is typically 'data: {"chunk": "..."}\n\n'
                if event.startswith('data: '):
                    try:
                        data_str = event[6:].strip()
                        if not data_str or data_str == '[DONE]': continue
                        data_json = json.loads(data_str)
                        chunk = data_json.get('chunk', '')
                        buffer += chunk
                        
                        # Regex to find all complete flat objects
                        all_objects = re.findall(r'\{[^{}]+\}', buffer)
                        for obj_str in all_objects:
                            try:
                                obj = json.loads(obj_str)
                                if 'name' in obj and ('reason' in obj or 'amount' in obj):
                                    name = obj['name'].strip()
                                    if name not in yielded_names:
                                        yielded_names.add(name)
                                        yield {"type": "suggestion", "data": obj}
                            except json.JSONDecodeError:
                                pass
                    except json.JSONDecodeError:
                        pass
                        
            # Yield the final complete object for rebalancing/reasoning
            final_json = cls._extract_json(buffer)
            if final_json:
                yield {"type": "complete", "data": final_json}

    @classmethod
    def synthesize_surprise_mix(cls, inventory: Optional[str] = None, mode: str = 'standard', drink_type: str = 'SODA') -> Optional[Dict[str, Any]]:
            """
            Autonomous Synthesis: Select a cohesive set of ingredients from the inventory.
            Soda/Slushie: 3 ingredients.
            Coffee: 3-5 ingredients, including a stabilizer.
            """
            drink_type = drink_type.upper()
            drink_label = {'SODA': 'soda', 'COFFEE': 'coffee drink', 'SLUSHIE': 'slushie'}.get(drink_type, 'drink')
            count_limit = "BETWEEN 2 and 4" if drink_type != 'COFFEE' else "BETWEEN 3 and 5"
    
            if drink_type == 'COFFEE':
                rules = """Rules:
    1. USE THE EXACT NOMENCLATURE from the Inventory Registry.
    2. Select a base (e.g. coffee bean) and complementary reagents.
    3. Provide a suggested 'amount'. The base coffee beans MUST default to 18.0 (representing 18.0g weight in grams). Dairy/milks (type DAIRY) must default to 50.0 (representing 50.0ml volume in milliliters), and other minor additives/syrups/accents (type ADDITIVE) must default to 15.0 (representing 15.0ml volume in milliliters). Exclusively prescribe milliliters for liquids, and strictly use 18.0 for coffee beans.
    4. Provide a 'design_intent' (overall reasoning for the pairing, max 20 words).
    5. For each ingredient, provide a specific 'role' (10 to 20 words detailing its flavor contribution).
    6. MANDATORY: Include exactly one 'Dairy & Plant Milk' (type DAIRY) as the secondary ingredient (directly after the base coffee beans, at index 1 / position 2 of the list) with a default amount of 50.0. Exclusively use genuine dairy or milk bases for this secondary ingredient."""
                example = """{
        "design_intent": "A rich milk-balanced double espresso (MOCK_MODE).",
        "selection": [
            { "name": "Espresso Roast Blend", "amount": 18.0, "role": "Base extraction" },
            { "name": "Whole Milk", "amount": 50.0, "role": "Creamy body" }
        ]
    }"""
            elif drink_type == 'SLUSHIE':
                rules = """Rules:
    1. USE THE EXACT NOMENCLATURE from the Inventory Registry.
    2. Select a base (e.g. fruit syrup) and complementary reagents.
    3. Provide a suggested 'amount' in milliliters (ml). Total syrup MUST NOT exceed 160ml (e.g., 80ml base, 40ml payload, 20ml accents).
    4. Provide a 'design_intent' (overall reasoning for the pairing, max 20 words).
    5. For each ingredient, provide a specific 'role' (10 to 20 words detailing its flavor contribution)."""
                example = """{
        "design_intent": "A refreshing frozen berry fruit blend.",
        "selection": [
            { "name": "Strawberry Syrup", "amount": 80.0, "role": "Base fruit" },
            { "name": "Blueberry Syrup", "amount": 40.0, "role": "Complementary accent" }
        ]
    }"""
            else:
                rules = """Rules:
    1. USE THE EXACT NOMENCLATURE from the Inventory Registry.
    2. Select a base (e.g. sweet syrup) and complementary reagents.
    3. Provide a suggested 'amount' in milliliters (ml). Total syrup MUST NOT exceed 160ml (e.g., 80ml primary, 35ml secondary, 10ml accents).
    4. Provide a 'design_intent' (overall reasoning for the pairing, max 20 words).
    5. For each ingredient, provide a specific 'role' (10 to 20 words detailing its flavor contribution)."""
                example = """{
        "design_intent": "A sharp carbonated citrus blend.",
        "selection": [
            { "name": "Lemon Syrup", "amount": 80.0, "role": "Base sweetener" },
            { "name": "Lime Syrup", "amount": 35.0, "role": "Tart balance" }
        ]
    }"""
    
            if not inventory:
                inventory = cls.get_static_ingredients_context(drink_type=drink_type)
    
            prompt = f"""[AUTONOMOUS SYNTHESIS REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE].
            
    Task: Select {count_limit} ingredients from the Inventory Registry below to create a cohesive {drink_label} compound.
    
    {rules}
    
    OUTPUT FORMAT: A raw JSON object.
    {example}
    
    Inventory Registry for Selection: See context.
    
    [DYNAMIC REQUEST PARAMETERS]:
        """
            response = cls.chat(prompt, context=inventory, drink_type=drink_type, mode=mode)
            return cls._extract_json(response)

    @classmethod
    def synthesize_flavor_summary(cls, ingredients: List[Dict[str, Any]], drink_type: str = 'SODA') -> str:
            """
            Given a finalized set of selected ingredients, produce a brief
            synthesis report: why they work together and what to expect. Plain text, no JSON.
            """
            drink_type = drink_type.upper()
            drink_label = {'SODA': 'soda', 'COFFEE': 'coffee drink', 'SLUSHIE': 'slushie'}.get(drink_type, 'drink')
            
            enriched_list = []
            for i in ingredients:
                name = i.get('name', 'Unknown Reagent')
                itype = str(i.get('type', i.get('ingredient_type', ''))).upper()
                amt = i.get('amount')
                amt_str = f" ({amt}g)" if itype == 'COFFEE_BEAN' else (f" ({amt}ml)" if amt else "")
                
                notes = i.get('flavor_notes', '')
                if isinstance(notes, list):
                    notes = ", ".join(notes)
                ai_notes = i.get('ai_notes', '')
                
                profile_part = f", Profile: {notes}" if notes else ""
                sensory_part = f", Sensory: {ai_notes}" if ai_notes else ""
                
                if itype == 'COFFEE_BEAN':
                    roast = i.get('roast_level', 'MEDIUM')
                    decaf = "Decaf" if i.get('is_decaf') or i.get('is_decaf') == 'true' or i.get('is_decaf') is True else "Regular"
                    desc = f"{name}{amt_str} [Type: {itype}, Roast: {roast}, {decaf}{profile_part}{sensory_part}]"
                else:
                    desc = f"{name}{amt_str} [Type: {itype}, Category: {i.get('category', 'sweet')}{profile_part}{sensory_part}]"
                enriched_list.append(desc)
            
            ingredient_list = '\n'.join(f"- {item}" for item in enriched_list)
            
            prompt = f"""FLAVOR SYNTHESIS REPORT
    
    Finalized {drink_label} compound:
    {ingredient_list}
    
    Write a detailed, vivid 3-paragraph lab report:
    Paragraph 1 — FLAVOR SYNERGY & AROMA: Why do these ingredients work together? Reference specific flavor science (acidity, sweetness, bitterness, intensity balance). Describe the initial aroma.
    Paragraph 2 — THE TASTING EXPERIENCE: What will this drink taste like? Describe the opening notes, the body, and the finish sequentially.
    Paragraph 3 — OVERALL IMPRESSION: A concluding sentence on the final aesthetic and vibe of the compound.
    
    Focus exclusively on the flavor profile. Format exactly as plain text without markdown."""
            return cls.chat(prompt, drink_type=drink_type)

    @classmethod
    def synthesize_flavor_summary_stream(cls, ingredients: List[Dict[str, Any]], drink_type: str = 'SODA', barista_notes: str = '') -> Generator[str, None, None]:
            """
            Streaming version of synthesize_flavor_summary.
            """
            drink_type = drink_type.upper()
            drink_label = {'SODA': 'soda', 'COFFEE': 'coffee drink', 'SLUSHIE': 'slushie'}.get(drink_type, 'drink')
            
            enriched_list = []
            for i in ingredients:
                name = i.get('name', 'Unknown Reagent')
                itype = str(i.get('type', i.get('ingredient_type', ''))).upper()
                amt = i.get('amount')
                amt_str = f" ({amt}g)" if itype == 'COFFEE_BEAN' else (f" ({amt}ml)" if amt else "")
                
                notes = i.get('flavor_notes', '')
                if isinstance(notes, list):
                    notes = ", ".join(notes)
                ai_notes = i.get('ai_notes', '')
                
                profile_part = f", Profile: {notes}" if notes else ""
                sensory_part = f", Sensory: {ai_notes}" if ai_notes else ""
                
                if itype == 'COFFEE_BEAN':
                    roast = i.get('roast_level', 'MEDIUM')
                    decaf = "Decaf" if i.get('is_decaf') or i.get('is_decaf') == 'true' or i.get('is_decaf') is True else "Regular"
                    desc = f"{name}{amt_str} [Type: {itype}, Roast: {roast}, {decaf}{profile_part}{sensory_part}]"
                else:
                    desc = f"{name}{amt_str} [Type: {itype}, Category: {i.get('category', 'sweet')}{profile_part}{sensory_part}]"
                enriched_list.append(desc)
            
            ingredient_list = '\n'.join(f"- {item}" for item in enriched_list)
            barista_context = f"\n\n    Chemistry Lab Notes:\n    {barista_notes}" if barista_notes else ""
            
            prompt = f"""FLAVOR SYNTHESIS REPORT
    
    Finalized {drink_label} compound:
    {ingredient_list}{barista_context}
    
    You must provide your output in TWO exact sections. 
    
    First, start with exactly this line:
    [MIXOLOGIST_NOTES]
    Write a short, personalized note about this mix. You may selectively incorporate the Chemistry Lab Notes if they highlight safety or structural risks (like curdling or overflow), otherwise you can ignore them. Rephrase them naturally if used.
    
    Then, output exactly this line:
    [PROFILE_DESCRIPTION]
    Write a detailed, vivid 3-paragraph lab report:
    Paragraph 1 — FLAVOR SYNERGY & AROMA: Why do these ingredients work together? Reference specific flavor science (acidity, sweetness, bitterness, intensity balance). Describe the initial aroma.
    Paragraph 2 — THE TASTING EXPERIENCE: What will this drink taste like? Describe the opening notes, the body, and the finish sequentially.
    Paragraph 3 — OVERALL IMPRESSION: A concluding sentence on the final aesthetic and vibe of the compound.
    
    Focus exclusively on the flavor profile. Format exactly as plain text without markdown."""
            yield from cls.chat_stream(prompt, drink_type=drink_type)

    @classmethod
    def generate_recipe_name(cls, ingredient_names: List[str], drink_type: str = 'SODA') -> str:
        """
        Generate a highly creative recipe name lazily via LLM.
        """
        drink_type = drink_type.upper()
        if not ingredient_names:
            return "Mystery Mix"
        
        ingredients_str = ", ".join(ingredient_names)
        prompt = f"""[RAW STRING REQUEST] — RAW STRING ONLY. [NO PREAMBLE].
        
You are a highly creative master mixologist.
Task: Generate a single, highly creative, memorable, and aesthetic name for a {drink_type} beverage.
Ingredients in the mixture: {ingredients_str}.

Constraints:
- Provide ONLY the name, nothing else.
- Maximum 3 words.
- Provide the name exactly as unquoted plain text.
- Provide the name exclusively without any extra text or explanation.
- Keep the name purely creative, omitting any mode names (e.g. Experimental, Soda, Coffee, Cryo).
- Keep the name purely descriptive, omitting any ingredient brand names.
"""
        response = cls.chat(prompt, drink_type=drink_type, mode='creative')
        if not response:
            return "Mystery Mix"
        return response.strip(' "\'')

    @classmethod
    def stream_quick_recommendations(cls, inventory: str, drink_type: str = 'SODA', mode: str = 'creative', profile: str = None, existing_recipes: list = None) -> Generator[Dict[str, Any], None, None]:
        """Stream 5 distinct recipes based on active inventory, prioritizing anchor shifts and novel combinations."""
        drink_type = drink_type.upper()
        
        import random
        seed = random.randint(10000, 99999)
        
        if profile:
            inspiration_prompt = f'[TARGET PROFILE: "{profile.upper()}"] - Feature the "{profile}" profile prominently as a core foundation. Complement it with secondary modifiers and accents from other available flavor categories to create harmonious, multi-layered beverages.'
        else:
            inspirations = [
                "neon, cyberpunk, futuristic",
                "rustic, garden, earthy",
                "midnight, velvet, mysterious",
                "sunburst, tropical, vibrant",
                "nostalgic, childhood, sweet",
                "aggressive, sour, intense",
                "calm, zen, herbal",
                "autumn, spiced, warm",
                "ocean, breeze, crisp",
                "desert, arid, complex"
            ]
            inspiration = random.choice(inspirations)
            inspiration_prompt = f'[RANDOM INSPIRATION SEED: "{inspiration}"] - Use this inspiration seed to dramatically influence the naming, descriptions, and ingredient combinations of these recipes.'

        if drink_type == 'COFFEE':
            mode_rules = """2. For parts: The base coffee beans (State: SOLID_EXTRACTABLE) MUST be 18.0 parts. Distribute all other liquid modifiers as relative parts (e.g. 50 parts dairy, 15 parts syrup).
3. Include exactly ONE base coffee bean ingredient and ONE genuine dairy or milk ingredient.
4. Craft evocative menu titles focused on flavor, sensation, and atmosphere."""
        elif drink_type == 'SLUSHIE':
            mode_rules = """2. For parts: Assign relative mathematical 'parts' to represent each ingredient's proportion in the slushie payload. Use fractional values (like 0.25 or 0.5) for delicate accents, and larger values (like 3.0 or 5.0) for primary bases.
3. Craft evocative menu titles focused on flavor, sensation, and atmosphere."""
        else:
            mode_rules = """2. For parts: Assign relative mathematical 'parts' to represent each ingredient's proportion in the total syrup profile. Use fractional values (like 0.25 or 0.5) for delicate accents, and larger values (like 3.0 or 5.0) for primary bases.
3. Craft evocative menu titles focused on flavor, sensation, and atmosphere."""

        novelty_guidance = ""
        if existing_recipes and len(existing_recipes) > 0:
            novelty_guidance = f"""
FRESH FLAVOR EXPLORATION:
- Focus on pairing the core {profile or 'drink'} theme with diverse and under-explored accents from the inventory.
- Ensure each of your 5 recipes features a distinctly unique dominant flavor lead (the ingredient with the largest parts).
- When combining familiar ingredients, create a fresh flavor experience by shifting the hierarchy (for instance, elevating a subtle accent to the bold primary lead and reducing previous leads to a subtle background accent).
"""

        prompt = f"""[QUICK DRINKS REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE]. [SEED: {seed}]
        
Task: Act as a master mixologist. Create exactly 5 distinct, highly creative, and appealing {drink_type} recipes using ONLY the ingredients available in the provided Inventory Registry. If the inventory has fewer than 10 total ingredients, you may generate fewer recipes (minimum 3).

{inspiration_prompt}
{novelty_guidance}
DIVERSITY DIRECTIVE: Each recipe must showcase a unique balance of flavors (such as tart, earthy, creamy, floral, or aromatic spice). Vary the complexity across your formulations to deliver 5 distinctly different tasting experiences.

OUTPUT FORMAT:
Output your response as a JSON array of objects.
Each JSON object must have the following structure:
{{
    "name": "Recipe Name",
    "description": "A short, vivid menu description of the drink and its vibe (20-30 words).",
    "ingredients": [
        {{ "name": "Exact Ingredient Name from Inventory", "parts": 15.0 }}
    ]
}}

Rules:
1. USE THE EXACT NOMENCLATURE from the Inventory Registry for ingredient names.
2. Ingredient Count: Vary the complexity across your 5 recipes. Include at least one minimalist recipe (exactly 2 ingredients) and at least one complex recipe (4 to 5 ingredients). Distribute the remaining recipes naturally within the 2 to 5 ingredient range.
{mode_rules}

Inventory Registry: See context.
"""
        stream = cls.chat_stream(prompt, context=inventory, drink_type=drink_type, mode=mode)
        
        buffer = ""
        yielded_indices = set()
        emitted_signatures = []

        # Helper to compute signature of a recipe
        def get_flavor_signature(recipe_dict):
            ings = recipe_dict.get('ingredients', [])
            if not ings:
                return set(), None
            # Filter non-structural
            flavor_ings = []
            for item in ings:
                name_clean = item.get('name', '').strip().lower()
                parts = float(item.get('parts', item.get('amount', 1.0)))
                # If coffee, skip structural beans and plain dairy for modifier comparison
                if drink_type == 'COFFEE':
                    if any(term in name_clean for term in ['bean', 'espresso', 'roast', 'whole milk', 'oat milk', 'skim milk', 'almond milk', 'soy milk']):
                        continue
                flavor_ings.append((name_clean, parts))
            
            if not flavor_ings:
                # Fallback to all ingredients if only structural ingredients present
                flavor_ings = [(item.get('name', '').strip().lower(), float(item.get('parts', item.get('amount', 1.0)))) for item in ings]

            flavor_set = frozenset(name for name, _ in flavor_ings)
            # Find dominant flavor lead
            dominant = max(flavor_ings, key=lambda x: x[1])[0] if flavor_ings else None
            return flavor_set, dominant

        # Pre-compute signatures for existing recipes
        existing_signatures = []
        if existing_recipes:
            for er in existing_recipes:
                fset, dom = get_flavor_signature(er)
                if fset:
                    existing_signatures.append((fset, dom))
        
        for event in stream:
            if event.startswith('data: '):
                try:
                    data_str = event[6:].strip()
                    if not data_str or data_str == '[DONE]': continue
                    data_json = json.loads(data_str)
                    chunk = data_json.get('chunk', '')
                    buffer += chunk
                    
                    all_objects = re.findall(r'\{\s*"name"\s*:.*?"ingredients"\s*:.*?\]\s*\}', buffer, re.DOTALL)
                    for i, obj_str in enumerate(all_objects):
                        if i not in yielded_indices:
                            try:
                                obj = json.loads(obj_str)
                                if 'name' in obj and 'ingredients' in obj:
                                    for ing in obj.get('ingredients', []):
                                        raw_name = ing.get('name', '')
                                        ing['name'] = re.sub(r'\s*[\[\(].*?[\]\)]\s*', '', str(raw_name)).strip()
                                        if 'parts' in ing and 'amount' not in ing:
                                            ing['amount'] = ing['parts']
                                    
                                    # Novelty & Anchor Check
                                    cand_fset, cand_dom = get_flavor_signature(obj)
                                    is_clone = False
                                    
                                    # 1. Compare against existing saved recipes
                                    for ex_fset, ex_dom in existing_signatures:
                                        if cand_fset == ex_fset and cand_dom == ex_dom:
                                            is_clone = True
                                            break
                                    
                                    # 2. Compare against already yielded recipes in this stream
                                    if not is_clone:
                                        for prev_fset, prev_dom in emitted_signatures:
                                            if cand_fset == prev_fset and cand_dom == prev_dom:
                                                is_clone = True
                                                break
                                    
                                    if not is_clone:
                                        emitted_signatures.append((cand_fset, cand_dom))
                                        yield obj
                                        yielded_indices.add(i)
                                    else:
                                        # Mark handled so we don't re-process
                                        yielded_indices.add(i)
                            except json.JSONDecodeError:
                                pass
                except json.JSONDecodeError:
                    pass

    @classmethod
    def stream_vibe_drink(cls, vibe_prompt: str, inventory: str, drink_type: str = 'SODA', mode: str = 'creative') -> Generator[Dict[str, Any], None, None]:
        """Stream a single recipe based on a vibe prompt."""
        drink_type = drink_type.upper()
        
        if drink_type == 'COFFEE':
            mode_rules = """2. For parts: The base coffee beans (State: SOLID_EXTRACTABLE) MUST be 18.0 parts. All other liquid modifiers should be distributed as relative parts (e.g. 50 parts dairy, 15 parts syrup).
3. Ensure you include exactly ONE base coffee bean ingredient and ONE genuine dairy or milk ingredient.
4. Keep the recipe name purely creative, omitting any mode names (e.g. Experimental, Soda, Coffee, Cryo, Standard).
5. Keep the recipe name purely descriptive, omitting any ingredient brand names."""
        elif drink_type == 'SLUSHIE':
            mode_rules = """2. For parts: Assign relative mathematical 'parts' to represent each ingredient's proportion in the slushie payload. Use organic fractional values (like 0.25 or 1.5) that naturally represent the ratio. Use fractional parts (like 0.5 or 0.25) for microscopic accents, and larger parts (like 3 or 5) for bases.
3. Keep the recipe name purely creative, omitting any mode names (e.g. Experimental, Soda, Coffee, Cryo, Standard).
4. Keep the recipe name purely descriptive, omitting any ingredient brand names."""
        else:
            mode_rules = """2. For parts: Assign relative mathematical 'parts' to represent each ingredient's proportion in the total syrup profile. Use organic fractional values (like 0.25 or 1.5) that naturally represent the ratio. Use fractional parts (like 0.5 or 0.25) for microscopic accents, and larger parts (like 3 or 5) for bases.
3. Keep the recipe name purely creative, omitting any mode names (e.g. Experimental, Soda, Coffee, Cryo, Standard).
4. Keep the recipe name purely descriptive, omitting any ingredient brand names."""

        prompt = f"""[VIBE DRINKS REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE].
        
Task: Act as a master mixologist. Create a single, highly creative {drink_type} recipe that captures the essence of the following vibe/feeling: "{vibe_prompt}".
You must use ONLY the ingredients available in the provided Inventory Registry.

OUTPUT FORMAT:
Output exactly ONE JSON object with the following structure:
{{
    "name": "Creative Recipe Name",
    "description": "A vivid explanation (30-40 words) of how this drink captures the requested vibe.",
    "ingredients": [
        {{ "name": "Exact Ingredient Name from Inventory", "parts": 15.0 }}
    ]
}}

Rules:
1. USE THE EXACT NOMENCLATURE from the Inventory Registry.
2. Ingredient Count: Actively vary the complexity of your output to showcase different styles. Naturally use anywhere between 2 and 5 ingredients to best suit the vibe requested (e.g. use 2 ingredients for a clean, simple vibe, or up to 5 for a highly complex vibe).
{mode_rules}
"""
        stream = cls.chat_stream(prompt, context=inventory, drink_type=drink_type, mode=mode)
        
        buffer = ""
        for event in stream:
            if event.startswith('data: '):
                try:
                    data_str = event[6:].strip()
                    if not data_str or data_str == '[DONE]': continue
                    data_json = json.loads(data_str)
                    chunk = data_json.get('chunk', '')
                    buffer += chunk
                    
                    # Wait until we have a complete JSON object
                    try:
                        match = re.search(r'\{\s*"name"\s*:.*?"ingredients"\s*:.*?\]\s*\}', buffer, re.DOTALL)
                        if match:
                            obj = json.loads(match.group(0))
                            if 'name' in obj and 'ingredients' in obj:
                                for ing in obj.get('ingredients', []):
                                    raw_name = ing.get('name', '')
                                    ing['name'] = re.sub(r'\s*[\[\(].*?[\]\)]\s*', '', str(raw_name)).strip()
                                    if 'parts' in ing and 'amount' not in ing:
                                        ing['amount'] = ing['parts']
                                yield obj
                                buffer = "" # Clear buffer once we yield
                    except json.JSONDecodeError:
                        pass
                except json.JSONDecodeError:
                    pass

    @classmethod
    def generate_single_quick_drink(
        cls,
        inventory: str,
        drink_type: str = 'SODA',
        mode: str = 'experimental',
        profile: str = 'Fruity',
        ingredient_count: int = 3,
        excluded_signatures: Optional[List[str]] = None,
        holiday_directives: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate a single Quick Drink recipe for a specific bucket (1-at-a-time for small local models),
        including full pre-generated mixologist_notes and profile_description.
        """
        import random
        drink_type = drink_type.upper()
        if drink_type == 'CRYO':
            drink_type = 'SLUSHIE'

        seed = random.randint(10000, 99999)
        is_holiday = bool(holiday_directives)

        if drink_type == 'COFFEE':
            modifier_count = max(1, ingredient_count - 2)
            lead_desc = f'matching the "{profile}" seasonal theme' if is_holiday else f'featuring the "{profile}" profile'
            mode_rules = f"""2. Exact Ingredient Count: Include exactly {ingredient_count} total ingredients:
   - 1 coffee bean base (State: SOLID_EXTRACTABLE) at 18.0 parts
   - 1 genuine dairy or plant milk base (Function: VOLUME_BASE, State: LIQUID) at 50.0 parts
   - {modifier_count} flavor modifier(s) {lead_desc} with distinct parts (e.g., 25.0 parts for the primary flavor lead, 10.0 to 15.0 parts for secondary accents)."""
        elif drink_type == 'SLUSHIE':
            lead_desc = f'matching the "{profile}" seasonal theme' if is_holiday else f'from the "{profile}" category'
            mode_rules = f"""2. Exact Ingredient Count: Include exactly {ingredient_count} total ingredients from the Inventory Registry.
   - Assign the largest 'parts' value (e.g. 5.0) to a primary ingredient {lead_desc} so it serves as the unmistakable primary flavor lead.
   - Assign smaller 'parts' values (e.g. 2.0, 1.0, 0.5) to the remaining {ingredient_count - 1} complementary ingredient(s)."""
        else:
            lead_desc = f'matching the "{profile}" seasonal theme' if is_holiday else f'from the "{profile}" category'
            mode_rules = f"""2. Exact Ingredient Count: Include exactly {ingredient_count} total ingredients from the Inventory Registry.
   - Assign the largest 'parts' value (e.g. 5.0 or 60.0) to a primary ingredient {lead_desc} so it serves as the unmistakable primary flavor lead.
   - Assign smaller 'parts' values (e.g. 2.0, 1.0, 0.5) to the remaining {ingredient_count - 1} complementary ingredient(s)."""

        avoid_block = ""
        if excluded_signatures:
            recent_sigs = excluded_signatures[-30:]
            readable_sigs = [s.replace('::', ' leading with ').replace('|', ', ') for s in recent_sigs]
            avoid_block = (
                "\nFRESH COMBINATION REQUIREMENT:\n"
                "Select a fresh combination of ingredients that differs from these existing formulas:\n- "
                + "\n- ".join(readable_sigs)
                + "\n"
            )

        if is_holiday:
            task_line = (
                f'Task: Act as a master mixologist. Create 1 distinct, festive {drink_type} recipe '
                f'celebrating the "{profile}" holiday/seasonal theme using ONLY the ingredients in the Inventory Registry.\n\n'
                f'SEASONAL & HOLIDAY THEME DIRECTIVES:\n{holiday_directives}\n'
            )
        else:
            task_line = (
                f'Task: Act as a master mixologist. Create 1 distinct, creative {drink_type} recipe '
                f'featuring the "{profile}" flavor category using ONLY the ingredients in the Inventory Registry.'
            )

        prompt = f"""[SINGLE QUICK DRINK CACHE REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE]. [SEED: {seed}]

{task_line}
{avoid_block}
OUTPUT FORMAT:
Output a single JSON object with this exact structure:
{{
    "name": "Creative Menu Title",
    "description": "A vivid 20-30 word menu blurb describing the drink's flavor vibe.",
    "mixologist_notes": "A personalized 1-2 sentence bartender note on why this ratio works.",
    "profile_description": "A vivid 2-3 paragraph sensory tasting report covering aroma, palate progression, and finish.",
    "ingredients": [
        {{ "name": "Exact Ingredient Name from Inventory", "parts": 60.0 }}
    ]
}}

Rules:
1. USE THE EXACT NOMENCLATURE from the Inventory Registry for ingredient names.
{mode_rules}
3. Keep the recipe title creative and evocative.
"""
        response = cls.chat(prompt, context=inventory, drink_type=drink_type, mode=mode)
        parsed = cls._extract_json(response)
        if isinstance(parsed, list) and len(parsed) > 0:
            parsed = parsed[0]
        if isinstance(parsed, dict) and 'name' in parsed and 'ingredients' in parsed:
            for ing in parsed.get('ingredients', []):
                raw_name = ing.get('name', '')
                ing['name'] = re.sub(r'\s*[\[\(].*?[\]\)]\s*', '', str(raw_name)).strip()
                if 'parts' in ing and 'amount' not in ing:
                    ing['amount'] = ing['parts']
            return parsed
        return None

