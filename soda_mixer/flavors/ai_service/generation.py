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
            tone = "safe and balanced" if mode == 'standard' else "bold and experimental"
            
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
    Current Mode: {drink_type} | Mode: {tone}
    Active Mixture: {current_compound_str}
    Force Type Constraint: {force_type or 'None'}{force_rule}
    Exclusion List: {exclude_str}
    
    Instruction: Analyze the active mixture '{current_compound_str}' and evaluate how all of its ingredients interact. Recommend items that complement the overall taste profile of the entire active mixture, not just the base ingredient. Avoid recommending items that clash with any part of the active mixture.
    """
            if retry_note:
                prompt += f"\n[RETRY COMMAND]: {retry_note}\n"
    
            response = cls.chat(prompt, context=inventory, drink_type=drink_type)
            return cls._extract_json(response)

    @classmethod
    def suggest_autonomous_stream(cls, ingredients: List[str], mode: str = 'standard', drink_type: str = 'SODA', inventory: Optional[str] = None, exclude: Optional[List[str]] = None, retry_note: Optional[str] = None, force_type: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
            """
            Streaming version of suggest_autonomous. Yields individual parsed suggestion objects as they arrive, 
            and then yields a final 'complete' object containing the full structured response (rebalancing, reasoning).
            """
            drink_type = drink_type.upper()
            tone = "safe and balanced" if mode == 'standard' else "bold and experimental"
            
            if not inventory:
                inventory = cls.get_static_ingredients_context(drink_type=drink_type)
    
            current_compound_details = []
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
    Current Mode: {drink_type} | Mode: {tone}
    Active Mixture: {current_compound_str}
    Force Type Constraint: {force_type or 'None'}{force_rule}
    Exclusion List: {exclude_str}
    
    Instruction: Analyze the active mixture '{current_compound_str}' and evaluate how all of its ingredients interact. Recommend items that complement the overall taste profile of the entire active mixture, not just the base ingredient. Avoid recommending items that clash with any part of the active mixture.
    """
            if retry_note:
                prompt += f"\n[RETRY COMMAND]: {retry_note}\n"
    
            stream = cls.chat_stream(prompt, context=inventory, drink_type=drink_type)
            
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
            tone = "safe and balanced" if mode == 'standard' else "bold and experimental"
            drink_label = {'SODA': 'soda', 'COFFEE': 'coffee drink', 'SLUSHIE': 'slushie'}.get(drink_type, 'drink')
            count_limit = "BETWEEN 2 and 4" if drink_type != 'COFFEE' else "BETWEEN 3 and 5"
    
            if drink_type == 'COFFEE':
                rules = """Rules:
    1. USE THE EXACT NOMENCLATURE from the Inventory Registry.
    2. Select a base (e.g. coffee bean) and complementary reagents.
    3. Provide a suggested 'amount'. The base coffee beans MUST default to 18.0 (representing 18.0g weight in grams). Dairy/milks (type DAIRY) must default to 50.0 (representing 50.0ml volume in milliliters), and other minor additives/syrups/accents (type ADDITIVE) must default to 15.0 (representing 15.0ml volume in milliliters). Do NOT prescribe grams for liquids, and do NOT use 100.0 or 50.0 for coffee beans.
    4. Provide a 'design_intent' (overall reasoning for the pairing, max 20 words).
    5. For each ingredient, provide a specific 'role' (max 8 words).
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
    5. For each ingredient, provide a specific 'role' (max 8 words)."""
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
    5. For each ingredient, provide a specific 'role' (max 8 words)."""
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
    Lab Mode: {tone}
    """
            response = cls.chat(prompt, context=inventory, drink_type=drink_type)
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
    
    Write a concise 2-paragraph lab report:
    Paragraph 1 — FLAVOR SYNERGY: Why do these ingredients work together? Reference specific flavor science (acidity, sweetness, bitterness, intensity balance, complementary/contrasting notes).
    Paragraph 2 — EXPECTED TASTE: What will this drink taste like? Describe the opening, body, and finish. Keep it vivid and specific.
    
    Do NOT give preparation instructions. Do NOT suggest more ingredients. No markdown formatting."""
            return cls.chat(prompt, drink_type=drink_type)

    @classmethod
    def synthesize_flavor_summary_stream(cls, ingredients: List[Dict[str, Any]], drink_type: str = 'SODA') -> Generator[str, None, None]:
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
            
            prompt = f"""FLAVOR SYNTHESIS REPORT
    
    Finalized {drink_label} compound:
    {ingredient_list}
    
    Write a concise 2-paragraph lab report:
    Paragraph 1 — FLAVOR SYNERGY: Why do these ingredients work together? Reference specific flavor science (acidity, sweetness, bitterness, intensity balance, complementary/contrasting notes).
    Paragraph 2 — EXPECTED TASTE: What will this drink taste like? Describe the opening, body, and finish. Keep it vivid and specific.
    
    Do NOT give preparation instructions. Do NOT suggest more ingredients. No markdown formatting."""
            yield from cls.chat_stream(prompt, drink_type=drink_type)

