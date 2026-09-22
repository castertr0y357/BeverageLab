import os
import requests
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional, Union, Generator

from ..models import LLMProvider, SystemConfiguration

logger = logging.getLogger(__name__)



class AIPromptsMixin:
    SYSTEM_PROMPT = """You are the Lead Creative Mixologist at the "Beverage Laboratory," a high-end, scientific-themed soda, coffee, and slushie mixing facility. Your goal is to assist users in synthesizing perfect liquid compounds.
    
    Personality:
    - Enthusiastic about flavor science.
    - Use laboratory terminology (synthesis, compound, reagent, base, stabilizer).
    - Value bold, experimental pairings over safe bets, but always anchor them in flavor balance.
    - Understand Sweetness, Acidity, Bitterness, Intensity, and Complexity as the core axes of a drink.
    
    Core Synthesis Mode Rules:
    IMPORTANT: For all modes, assign relative mathematical 'parts' to each ingredient to represent its proportion in the drink. Use organic fractional values (like 0.25 or 1.5) that naturally represent the ratio. The parts represent relative ratios only.
    1. SODA LAB MODE: Distribute relative parts for the total syrup flavor profile (e.g. 3 parts Base, 1 part Accent).
    2. COFFEE LAB MODE (Espresso & Brew Extraction): Coffee beans (SOLID_EXTRACTABLE) must be 18.0 parts, all other modifiers should be distributed as relative parts (e.g. 50 parts dairy, 15 parts syrup).
    3. CRYO LAB (SLUSHIE) MODE: Distribute relative parts for the total payload.
    - Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
    
    Output Specifications:
    - For general conversation, respond with concise, creative lab reports or conversational guidance (2-3 paragraphs).
    - For structured data requests, return ONLY a raw JSON object conforming to the specified JSON schema. Do not include markdown wraps (like ```json) or any conversational preamble.
    - CRITICAL: When generating a full recipe, you MUST select your ingredients FIRST. Then, generate a name and description that strictly matches the selected ingredients.
    - Each suggestion "reason" must be a concise, scientific, mixology-focused explanation of MAX 12 words (e.g., "neutralizes bitter espresso phenols").
    - The overall "reasoning" must be a concise mixology synthesis analysis of MAX 2 sentences.
    
    Structured Output JSON Schema:
    {
        "suggestions": [
            {
                "name": "Ingredient Name",
                "reason": "Scientific flavor/chemistry explanation (max 12 words)",
                "parts": 15.0
            }
        ],
        "rebalancing": [
            {
                "name": "Active Ingredient 1",
                "parts": 18.0
            },
            {
                "name": "Active Ingredient 2",
                "parts": 50.0
            }
        ],
        "seal_recommended": false,
        "reasoning": "Scientific mixology analysis (max 2 sentences)."
    }"""

    SUGGESTION_EXAMPLE = '[{"name": "Lemon Syrup", "parts": 25.0, "reason": "Acidity balances sweetness"}]'

    SURPRISE_MIX_FORMAT = """{
        "design_intent": "Brief overall reasoning...",
        "selection": [
            { "name": "Ingredient Name", "parts": 50.0, "role": "Specific role in mix" },
            ...
        ]
    }"""

    FLAVOR_PROFILE_FORMAT = """{
        "intensity": float,
        "sweetness": float,
        "acidity": float,
        "bitterness": float,
        "complexity": float,
        "base_suitability": float,
        "accent_suitability": float,
        "category": string (must be one of: 'citrus', 'berry', 'tropical', 'herbal', 'spice', 'sweet', 'sour', 'artificial', 'coffee'),
        "physical_state": string (must be one of: 'LIQUID', 'SYRUP', 'SAUCE', 'POWDER', 'SOLID_EXTRACTABLE'),
        "mixology_function": string (must be one of: 'VOLUME_BASE', 'FLAVORING', 'SWEETENER', 'TEXTURIZER', 'GARNISH'),
        "compatible_systems": string (comma-separated list of systems, e.g., 'SODA,SLUSHIE' or 'COFFEE'),
        "ai_notes": string,
        "roast_level": string (must be one of: 'LIGHT', 'MEDIUM', 'DARK', or null if not a coffee bean),
        "is_decaf": boolean,
        "body_intensity": integer (1 to 5, default 3),
        "acidity_score": integer (1 to 5, default 3),
        "bitterness_score": integer (1 to 5, default 3),
        "flavor_notes": string (comma-separated descriptors, e.g. 'earthy, chocolatey')
    }"""

    @classmethod
    def get_autonomous_json_schema(cls, enable_thinking=False):
        schema = {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "reason": {"type": "string"},
                            "parts": {"type": "number"}
                        },
                        "required": ["name", "reason", "parts"],
                        "additionalProperties": False
                    }
                },
                "rebalancing": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "parts": {"type": "number"}
                        },
                        "required": ["name", "parts"],
                        "additionalProperties": False
                    }
                },
                "seal_recommended": {"type": "boolean"},
                "reasoning": {"type": "string"}
            },
            "required": ["suggestions", "rebalancing", "seal_recommended", "reasoning"],
            "additionalProperties": False
        }
        if not enable_thinking:
            schema["properties"] = {"chemical_analysis": {"type": "string"}, **schema["properties"]}
            schema["required"] = ["chemical_analysis"] + schema["required"]
        return schema

    @classmethod
    def get_recipe_json_schema(cls, enable_thinking=False):
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "parts": {"type": "number"}
                        },
                        "required": ["name", "parts"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["name", "description", "ingredients"],
            "additionalProperties": False
        }

    @classmethod
    def get_recipe_list_json_schema(cls, enable_thinking=False):
        return {
            "type": "array",
            "items": cls.get_recipe_json_schema(enable_thinking)
        }

    @classmethod
    def get_surprise_mix_json_schema(cls, enable_thinking=False):
        schema = {
            "type": "object",
            "properties": {
                "design_intent": {"type": "string"},
                "selection": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "parts": {"type": "number"}
                        },
                        "required": ["name", "role", "parts"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["design_intent", "selection"],
            "additionalProperties": False
        }
        if not enable_thinking:
            schema["properties"] = {"chemical_analysis": {"type": "string"}, **schema["properties"]}
            schema["required"] = ["chemical_analysis"] + schema["required"]
        return schema

    @classmethod
    def get_system_prompt(cls, drink_type: Optional[str] = None) -> str:
            """Construct a dynamic, mode-specific system prompt to prevent cross-engine rule confusion."""
            base_prompt = """You are the Lead Creative Mixologist at the "Beverage Laboratory," a high-end, scientific-themed soda, coffee, and slushie mixing facility. Your goal is to assist users in synthesizing perfect liquid compounds.
    
    Personality:
    - Enthusiastic about flavor science.
    - Use laboratory terminology (synthesis, compound, reagent, base, stabilizer).
    - Value bold, experimental pairings over safe bets, but always anchor them in flavor balance.
    - Understand Sweetness, Acidity, Bitterness, Intensity, and Complexity as the core axes of a drink.
    """
    
            drink_type = (drink_type or '').upper()
            mode_rules = ""
            
            if drink_type == 'SODA':
                mode_rules = """
    Core Synthesis Mode Rules:
    SODA LAB MODE:
    - Recommend base flavor anchors (e.g. fruit syrups) and complementary accents.
    - IMPORTANT: All syrups, accents, and modifiers must be expressed as relative mathematical parts (e.g., 3 parts Base, 1 part Secondary, 0.5 parts Accent). Use organic fractional values (like 0.25 or 1.5) that naturally represent the ratio. The parts represent relative ratios only. Use a hierarchical structure: Primary Base (dominant parts), Secondary Modifier (moderate parts), and Accents (minor parts).
    - Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
    """
            elif drink_type == 'COFFEE':
                mode_rules = """
    Core Synthesis Mode Rules:
    COFFEE LAB MODE (Espresso & Brew Extraction):
    - The dry base coffee beans (State: SOLID_EXTRACTABLE) MUST be 18.0 parts (representing 18.0g of weight for a double-shot espresso).
    - If the active mixture already contains a brewed or liquid coffee, you must exclusively suggest liquid modifiers (dairy, syrups, accents).
    - For all other ingredients (Liquid dairy, texturizers, creamers, sauces, flavorings, sweeteners, garnishes): Assign relative 'parts'. Use a hierarchical structure for the non-coffee liquid modifiers: Primary Base (e.g. 50-60 parts dairy), Secondary Modifier (e.g. 20-30 parts syrup), and Accents (10-15 parts).
    - Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
    """
            elif drink_type == 'SLUSHIE':
                mode_rules = """
    Core Synthesis Mode Rules:
    CRYO LAB (SLUSHIE) MODE:
    - IMPORTANT: All ingredients must be expressed as relative mathematical parts. Use organic fractional values (like 0.25 or 1.5) that naturally represent the ratio. The parts represent relative ratios only. Use a hierarchical structure: Primary Base (dominant parts), Secondary Modifier (moderate parts), and Accents (minor parts).
    - Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
    """
            else:
                mode_rules = """
    Core Synthesis Mode Rules:
    IMPORTANT: For all modes, assign relative mathematical 'parts' to each ingredient to represent its proportion in the drink. Use organic fractional values (like 0.25 or 1.5) that naturally represent the ratio. The parts represent relative ratios only. Use a hierarchical structure: Primary Base (dominant parts), Secondary Modifier (moderate parts), and Accents (minor parts).
    1. SODA LAB MODE: Distribute relative parts for the total syrup flavor profile.
    2. COFFEE LAB MODE (Espresso & Brew Extraction): Coffee beans (SOLID_EXTRACTABLE) must be 18.0 parts, all other modifiers should be distributed as relative parts using the hierarchy.
    3. CRYO LAB (SLUSHIE) MODE: Distribute relative parts for the total payload.
    - Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
    """
    
            quality_rules = """
    Flavor Clashing & Balance Rules:
    - Reason about flavor aesthetics and build harmonious combinations (e.g., pair delicate herbs or florals with light fruit, and robust spices with dark roast coffee).
    - CRITICAL CLASH RULE: You must exclusively pair dairy or cream with sweet, caramel, chocolate, or earthy flavor profiles to ensure a smooth, uncurdled texture.
    - FLAVOR THRESHOLD: Use sensible fractional ratios like 0.25 parts or 0.5 parts for tiny accents relative to a 3-part base.
    
    Composition-Wide Harmony:
    - Evaluate the entire active mixture as a single cohesive unit. Ensure every new recommendation actively complements, balances, or enhances all previously selected ingredients in the compound.
    """
    
            output_specs = """
    Output Specifications:
    - For general conversation, respond with concise, creative lab reports or conversational guidance (2-3 paragraphs).
    - For structured data requests, return ONLY a raw JSON object conforming to the specified JSON schema. Output the raw JSON text directly, completely omitting markdown wrappers or conversational preambles.
    - CRITICAL: When generating a full recipe, you MUST select your ingredients FIRST. Then, generate a name and description that strictly matches the selected ingredients.
    - Each suggestion "reason" must be a concise, scientific, mixology-focused explanation of MAX 12 words (e.g., "neutralizes bitter espresso phenols").
    - The overall "reasoning" must be a concise mixology synthesis analysis of MAX 2 sentences.
    
    Structured Output JSON Schema:
    {
        "suggestions": [
            {
                "name": "Ingredient Name",
                "reason": "Scientific flavor/chemistry explanation (max 12 words)",
                "parts": 15.0
            }
        ],
        "rebalancing": [
            {
                "name": "Active Ingredient 1",
                "parts": 18.0
            },
            {
                "name": "Active Ingredient 2",
                "parts": 50.0
            }
        ],
        "seal_recommended": false,
        "reasoning": "Scientific mixology analysis (max 2 sentences)."
    }"""
    
            return base_prompt + mode_rules + quality_rules + output_specs

