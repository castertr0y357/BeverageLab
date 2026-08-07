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
                    ing_display = f"{db_ing.brand} {db_ing.name}" if db_ing.brand else db_ing.name
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
                force_rule = f"\nMANDATORY RULE: You must ONLY suggest new ingredients of type '{force_type}' (e.g., {force_display}). Do not suggest any other types of ingredients."
                
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
                    ing_display = f"{db_ing.brand} {db_ing.name}" if db_ing.brand else db_ing.name
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
                force_rule = f"\nMANDATORY RULE: You must ONLY suggest new ingredients of type '{force_type}' (e.g., {force_display}). Do not suggest any other types of ingredients."
                
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
    3. Provide a suggested 'amount'. The base coffee beans MUST default to 18.0 (representing 18.0g weight in grams). Dairy/milks (type DAIRY) must default to 50.0 (representing 50.0ml volume in milliliters), and other minor additives/syrups/accents (type ADDITIVE) must default to 15.0 (representing 15.0ml volume in milliliters). Do NOT prescribe grams for liquids, and do NOT use 100.0 or 50.0 for coffee beans.
    4. Provide a 'design_intent' (overall reasoning for the pairing, max 20 words).
    5. For each ingredient, provide a specific 'role' (10 to 20 words detailing its flavor contribution).
    6. MANDATORY: Include exactly one 'Dairy & Plant Milk' (type DAIRY) as the secondary ingredient (directly after the base coffee beans, at index 1 / position 2 of the list) with a default amount of 50.0. Minor additives (type ADDITIVE) like Heavy Cream must NOT be used as this secondary ingredient."""
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
    3. Provide a suggested 'amount' in milliliters (ml). Total syrup MUST NOT exceed 160ml (e.g., 100ml base, 50ml payload, 25ml accents).
    4. Provide a 'design_intent' (overall reasoning for the pairing, max 20 words).
    5. For each ingredient, provide a specific 'role' (10 to 20 words detailing its flavor contribution)."""
                example = """{
        "design_intent": "A sharp carbonated citrus blend.",
        "selection": [
            { "name": "Lemon Syrup", "amount": 100.0, "role": "Base sweetener" },
            { "name": "Lime Syrup", "amount": 50.0, "role": "Tart balance" }
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
    
    Do NOT give preparation instructions. Do NOT suggest more ingredients. No markdown formatting."""
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
    Write a short, personalized note about this mix. You may selectively incorporate the Chemistry Lab Notes if they highlight safety or structural risks (like curdling or overflow), otherwise you can ignore them. Do not just parrot them.
    
    Then, output exactly this line:
    [PROFILE_DESCRIPTION]
    Write a detailed, vivid 3-paragraph lab report:
    Paragraph 1 — FLAVOR SYNERGY & AROMA: Why do these ingredients work together? Reference specific flavor science (acidity, sweetness, bitterness, intensity balance). Describe the initial aroma.
    Paragraph 2 — THE TASTING EXPERIENCE: What will this drink taste like? Describe the opening notes, the body, and the finish sequentially.
    Paragraph 3 — OVERALL IMPRESSION: A concluding sentence on the final aesthetic and vibe of the compound.
    
    Do NOT give preparation instructions. Do NOT suggest more ingredients. No markdown formatting."""
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
        prompt = f"""[STRUCTURED DATA REQUEST] — RAW STRING ONLY. [NO PREAMBLE].
        
You are a highly creative master mixologist.
Task: Generate a single, highly creative, memorable, and aesthetic name for a {drink_type} beverage.
Ingredients in the mixture: {ingredients_str}.

Constraints:
- Provide ONLY the name, nothing else.
- Maximum 3 words.
- Do not use quotes around the name.
- Do not add any extra text or explanation.
"""
        response = cls.chat(prompt, drink_type=drink_type, mode='creative')
        if not response:
            return "Mystery Mix"
        return response.strip(' "\'')

    @classmethod
    def stream_quick_recommendations(cls, inventory: str, drink_type: str = 'SODA', mode: str = 'creative') -> Generator[Dict[str, Any], None, None]:
        """Stream 5 distinct recipes based on active inventory."""
        drink_type = drink_type.upper()
        
        import random
        seed = random.randint(10000, 99999)
        
        prompt = f"""[QUICK DRINKS REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE]. [SEED: {seed}]
        
Task: Act as a master mixologist. Create exactly 5 distinct, highly creative, and appealing {drink_type} recipes using ONLY the ingredients available in the provided Inventory Registry. If the inventory has fewer than 10 total ingredients, you may generate fewer recipes (minimum 3).

CRITICAL RULE: The recipes MUST be completely different from typical or past responses. Vary the flavor profiles radically (e.g., earthy, ultra-tart, creamy, herbal, spicy, or exotic fruit combinations). Do not rely on the same 5 combinations. Push the boundaries of mixology.

OUTPUT FORMAT:
Output your response as a JSON array of objects.
Each JSON object must have the following structure:
{{
    "name": "Recipe Name",
    "description": "A short, vivid menu description of the drink and its vibe (20-30 words).",
    "ingredients": [
        {{ "name": "Exact Ingredient Name from Inventory", "amount": 100.0 }}
    ]
}}

Rules:
1. USE THE EXACT NOMENCLATURE from the Inventory Registry for ingredient names.
2. For amounts: For SODA/SLUSHIE, use ml (typically summing around 100-160ml for the flavor base). For COFFEE, base coffee beans use grams (default 18.0g), liquids use ml (e.g., milk 50.0ml, syrup 15.0ml).
3. If {drink_type} is COFFEE, ensure you include exactly ONE base coffee bean ingredient and ONE dairy/milk ingredient.

Inventory Registry: See context.
"""
        stream = cls.chat_stream(prompt, context=inventory, drink_type=drink_type, mode=mode)
        
        buffer = ""
        yielded_indices = set()
        
        for event in stream:
            if event.startswith('data: '):
                try:
                    data_str = event[6:].strip()
                    if not data_str or data_str == '[DONE]': continue
                    data_json = json.loads(data_str)
                    chunk = data_json.get('chunk', '')
                    buffer += chunk
                    
                    # Regex to find complete JSON objects inside the array
                    # This finds things that look like {"name": ..., "ingredients": [...]}
                    # We can do a simple parse of all objects in the buffer so far.
                    
                    # To safely parse partial JSON arrays, we can use a regex to find all objects
                    all_objects = re.findall(r'\{\s*"name"\s*:.*?"ingredients"\s*:.*?\]\s*\}', buffer, re.DOTALL)
                    for i, obj_str in enumerate(all_objects):
                        if i not in yielded_indices:
                            try:
                                obj = json.loads(obj_str)
                                if 'name' in obj and 'ingredients' in obj:
                                    yield obj
                                    yielded_indices.add(i)
                            except json.JSONDecodeError:
                                pass
                except json.JSONDecodeError:
                    pass

    @classmethod
    def stream_vibe_drink(cls, vibe_prompt: str, inventory: str, drink_type: str = 'SODA', mode: str = 'creative') -> Generator[Dict[str, Any], None, None]:
        """Stream a single recipe based on a vibe prompt."""
        drink_type = drink_type.upper()
        
        prompt = f"""[VIBE DRINKS REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE].
        
Task: Act as a master mixologist. Create a single, highly creative {drink_type} recipe that captures the essence of the following vibe/feeling: "{vibe_prompt}".
You must use ONLY the ingredients available in the provided Inventory Registry.

OUTPUT FORMAT:
Output exactly ONE JSON object with the following structure:
{{
    "name": "Creative Recipe Name",
    "description": "A vivid explanation (30-40 words) of how this drink captures the requested vibe.",
    "ingredients": [
        {{ "name": "Exact Ingredient Name from Inventory", "amount": 100.0 }}
    ]
}}

Rules:
1. USE THE EXACT NOMENCLATURE from the Inventory Registry.
2. For amounts: For SODA/SLUSHIE, use ml. For COFFEE, base coffee beans use grams, liquids use ml.
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
                                yield obj
                                buffer = "" # Clear buffer once we yield
                    except json.JSONDecodeError:
                        pass
                except json.JSONDecodeError:
                    pass
