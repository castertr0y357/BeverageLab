import os
import requests
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional, Union, Generator

from ..models import LLMProvider, SystemConfiguration

logger = logging.getLogger(__name__)



class AIAnalysisMixin:
    @classmethod
    def analyze_flavor_profile(cls, name: str, description: str) -> Optional[Dict[str, float]]:
            """Analyze a flavor and return its chemical profile as JSON."""
            prompt = f"""
            Analyze this ingredient:
            Name: {name}
            Description: {description}
    
            Return ONLY a JSON object with values for these metrics:
            - intensity (value from 1.0 to 5.0)
            - sweetness (value from 1.0 to 5.0)
            - acidity (value from 1.0 to 5.0)
            - bitterness (value from 1.0 to 5.0)
            - complexity (value from 1.0 to 5.0)
            - base_suitability (how well it serves as a dominant, high-volume base ingredient, from 1.0 to 5.0)
            - accent_suitability (how well it serves as a low-volume accent / high-impact nuance, from 1.0 to 5.0)
            - category (must be one of: 'citrus', 'berry', 'tropical', 'herbal', 'spice', 'sweet', 'sour', 'artificial', 'coffee')
            - ingredient_type (must be one of: 'SODA_SYRUP', 'COFFEE_BEAN', 'DAIRY', 'ADDITIVE', 'OTHER')
            - is_ready_to_drink (boolean, true if it is a ready-to-drink liquid like juice, milk, tea, or soda base; false for concentrated syrups, beans, or powders)
            - is_dry (boolean, true if it is a dry/powdered ingredient like sugar, powder, coffee beans; false for liquid ingredients like syrups, juice, milk, water)
            - compatible_systems (comma-separated list of systems it fits physically and flavor-wise, from: 'SODA', 'COFFEE', 'SLUSHIE' - e.g., 'SODA,SLUSHIE' or 'COFFEE')
            - ai_notes (a short paragraph of relevant notes about this ingredient's flavor profile, pairings, and mixology recommendations)
            - roast_level (string, must be 'LIGHT', 'MEDIUM', or 'DARK', or null if not a coffee bean)
            - is_decaf (boolean, true if decaf coffee, false otherwise)
            - body_intensity (integer, 1 to 5, default 3)
            - acidity_score (integer, 1 to 5, default 3)
            - bitterness_score (integer, 1 to 5, default 3)
            - flavor_notes (string, comma-separated flavor descriptors e.g. 'herbal, earthy, chocolate, nutty')
    
            OUTPUT FORMAT: A raw JSON object. [NO MARKDOWN] [NO PREAMBLE].
            Example: {cls.FLAVOR_PROFILE_FORMAT}
            Base your analysis on chemical flavor profiles.
            """
            response = cls.chat(prompt)
            # Resilient JSON extraction
            return cls._extract_json(response)

    @classmethod
    def bulk_analyze_flavor_profiles(cls, ingredients_data: List[Dict[str, str]]) -> Optional[List[Dict[str, Any]]]:
            """
            Analyze a list of ingredients in a single batch.
            ingredients_data: List of {'name': str, 'description': str}
            """
            ing_text = "\n".join([f"- Name: {ing['name']}, Description: {ing['description']}" for ing in ingredients_data])
            prompt = f"""
            [BATCH CHEMICAL ANALYSIS]
            Analyze the following reagents and synthesize their flavor profiles.
            
            Ingredients to analyze:
            {ing_text}
            
            For each, return values for:
            - intensity (value from 1.0 to 5.0)
            - sweetness (value from 1.0 to 5.0)
            - acidity (value from 1.0 to 5.0)
            - bitterness (value from 1.0 to 5.0)
            - complexity (value from 1.0 to 5.0)
            - base_suitability (how well it serves as a dominant, high-volume base ingredient, from 1.0 to 5.0)
            - accent_suitability (how well it serves as a low-volume accent / high-impact nuance, from 1.0 to 5.0)
            - category (must be one of: 'citrus', 'berry', 'tropical', 'herbal', 'spice', 'sweet', 'sour', 'artificial', 'coffee')
            - ingredient_type (must be one of: 'SODA_SYRUP', 'COFFEE_BEAN', 'DAIRY', 'ADDITIVE', 'OTHER')
            - is_ready_to_drink (boolean, true if it is a ready-to-drink liquid like juice, milk, tea, or soda base; false for concentrated syrups, beans, or powders)
            - is_dry (boolean, true if it is a dry/powdered ingredient like sugar, powder, coffee beans; false for liquid ingredients like syrups, juice, milk, water)
            - compatible_systems (comma-separated list of compatible systems from: 'SODA', 'COFFEE', 'SLUSHIE')
            - ai_notes (a short paragraph of relevant notes about this ingredient's flavor profile, pairings, and mixology recommendations)
            - roast_level (string, 'LIGHT', 'MEDIUM', 'DARK', or null if not a coffee bean)
            - is_decaf (boolean, true if decaf coffee, false otherwise)
            - body_intensity (integer, 1 to 5, default 3)
            - acidity_score (integer, 1 to 5, default 3)
            - bitterness_score (integer, 1 to 5, default 3)
            - flavor_notes (string, comma-separated flavor descriptors e.g. 'herbal, earthy, chocolate, nutty')
            
            OUTPUT FORMAT: A raw JSON array of objects. [NO MARKDOWN] [NO PREAMBLE].
            Example: [{{ "name": "Lemon", "intensity": 4.5, "sweetness": 2.0, "acidity": 5.0, "bitterness": 1.5, "complexity": 1.5, "base_suitability": 4.5, "accent_suitability": 2.0, "category": "citrus", "ingredient_type": "SODA_SYRUP", "is_ready_to_drink": false, "is_dry": false, "compatible_systems": "SODA,SLUSHIE", "ai_notes": "Bright, tart citrus that cuts through heavy syrups and adds freshness.", "roast_level": null, "is_decaf": false, "body_intensity": 3, "acidity_score": 3, "bitterness_score": 3, "flavor_notes": "citrus, sweet" }}]
            """
            response = cls.chat(prompt)
            return cls._extract_json(response)

