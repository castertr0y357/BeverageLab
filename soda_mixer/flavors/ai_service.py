"""Service for interacting with various LLM providers."""

import os
import requests
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional, Union, Generator

from .models import LLMProvider, SystemConfiguration

logger = logging.getLogger(__name__)


class AIAssistant:
    """Service for interacting with various LLM providers."""

    SYSTEM_PROMPT = """You are the Lead Creative Mixologist at the "Beverage Laboratory," a high-end, scientific-themed soda, coffee, and slushie mixing facility. Your goal is to assist users in synthesizing perfect liquid compounds.

Personality:
- Enthusiastic about flavor science.
- Use laboratory terminology (synthesis, compound, reagent, base, stabilizer).
- Value bold, experimental pairings over safe bets, but always anchor them in flavor balance.
- Understand Sweetness, Acidity, Bitterness, Intensity, and Complexity as the core axes of a drink.

Core Synthesis Mode Rules:

1. SODA LAB MODE:
   - Total syrup for a 1.0L batch must not exceed 160ml (proportional for other sizes: 80ml for 0.5L, crisp=105ml, craft=120ml, fountain=140ml).
   - Recommend base flavor anchors (e.g. fruit syrups) and complementary accents.

2. COFFEE LAB MODE (Espresso & Brew Extraction):
   - The dry base coffee beans MUST be 18.0g (weight) representing a double-shot espresso.
   - Liquid dairy and plant milks (type DAIRY) must be 50.0ml (volume).
   - Minor additives, sweet syrups, and creamers (type ADDITIVE) must be 15.0ml (volume).
   - Accents and others must be 15.0ml.
   - Do NOT suggest grams for liquids, and do NOT use ml for coffee beans.
   - Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.

3. CRYO LAB (SLUSHIE) MODE:
   - Total syrup for a 1.0L batch must not exceed 160ml.
   - Recommend amounts based on Ninja Creami displacement limits (e.g., 80.0ml for base, 40.0ml for payloads, 20.0ml for accents).

Output Specifications:
- For general conversation, respond with concise, creative lab reports or conversational guidance (2-3 paragraphs).
- For structured data requests, return ONLY a raw JSON object conforming to the specified JSON schema. Do not include markdown wraps (like ```json) or any conversational preamble.
- Each suggestion "reason" must be a concise, scientific, mixology-focused explanation of MAX 12 words (e.g., "neutralizes bitter espresso phenols").
- The overall "reasoning" must be a concise mixology synthesis analysis of MAX 2 sentences.

Structured Output JSON Schema:
{
    "suggestions": [
        {
            "name": "Ingredient Name",
            "reason": "Scientific flavor/chemistry explanation (max 12 words)",
            "amount": 15.0
        }
    ],
    "rebalancing": {
        "Active Ingredient 1": 18.0,
        "Active Ingredient 2": 50.0
    },
    "seal_recommended": false,
    "reasoning": "Scientific mixology analysis (max 2 sentences)."
}"""
    
    SUGGESTION_EXAMPLE = '[{"name": "Lemon Syrup", "amount": 25.0, "reason": "Acidity balances sweetness"}]'
    
    SURPRISE_MIX_FORMAT = """{
    "design_intent": "Brief overall reasoning...",
    "selection": [
        { "name": "Ingredient Name", "amount": 50.0, "role": "Specific role in mix" },
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
    def _resolve_base_url(cls, provider: LLMProvider, default_url: str = "") -> str:
        """Resolve base URL, translating localhost/127.0.0.1 to host.docker.internal if running in Docker."""
        base_url = provider.base_url or default_url
        if os.path.exists('/.dockerenv'):
            if "localhost" in base_url:
                base_url = base_url.replace("localhost", "host.docker.internal")
            elif "127.0.0.1" in base_url:
                base_url = base_url.replace("127.0.0.1", "host.docker.internal")
        return base_url

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
- Total syrup for a 1.0L batch must not exceed 160ml (proportional for other sizes: 80ml for 0.5L, crisp=105ml, craft=120ml, fountain=140ml).
- Recommend base flavor anchors (e.g. fruit syrups) and complementary accents.
- Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
"""
        elif drink_type == 'COFFEE':
            mode_rules = """
Core Synthesis Mode Rules:
COFFEE LAB MODE (Espresso & Brew Extraction):
- The dry base coffee beans (State: SOLID_EXTRACTABLE) MUST be 18.0g (weight) representing a double-shot espresso.
- Liquid dairy and plant milks (Function: VOLUME_BASE, State: LIQUID) must be 50.0ml (volume).
- Texturizers, creamers, and sauces (Function: TEXTURIZER, State: SAUCE or LIQUID) must be 15.0ml (volume).
- Accents, flavorings, sweeteners, and garnishes must be 15.0ml.
- Do NOT suggest grams for liquids/syrups/sauces, and do NOT use ml for coffee beans.
- Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
"""
        elif drink_type == 'SLUSHIE':
            mode_rules = """
Core Synthesis Mode Rules:
CRYO LAB (SLUSHIE) MODE:
- Total syrup for a 1.0L batch must not exceed 160ml.
- Recommend amounts based on Ninja Creami displacement limits (e.g., 80.0ml for base, 40.0ml for payloads, 20.0ml for accents).
- Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
"""
        else:
            mode_rules = """
Core Synthesis Mode Rules:
1. SODA LAB MODE: Total syrup for a 1.0L batch must not exceed 160ml.
2. COFFEE LAB MODE (Espresso & Brew Extraction): Coffee beans (SOLID_EXTRACTABLE) must be 18.0g, volume bases like dairy/plant milk (VOLUME_BASE, LIQUID) must be 50.0ml, and other flavorings/sweeteners/texturizers must be 15.0ml.
3. CRYO LAB (SLUSHIE) MODE: Total syrup for a 1.0L batch must not exceed 160ml.
- Limit suggested counts strictly based on compatibility rules: recommend between 10 and 15 options (or all available if there are fewer than 10). Prioritize ingredients with the '*FAVORITE*' tag when they fit the flavor profile.
"""

        quality_rules = """
Flavor Clashing & Balance Rules:
- Reason about flavor aesthetics and avoid clashing combinations (e.g., do not pair delicate herbs or florals like lavender with extremely bitter dark roast coffee, and avoid combining highly acidic ingredients with dairy to prevent curdling/clashing taste).

Composition-Wide Harmony:
- Evaluate the entire active mixture as a single cohesive unit. Do not just recommend based on the base flavor; ensure the new recommendation complements, balances, or enhances all selected ingredients in the compound.
"""

        output_specs = """
Output Specifications:
- For general conversation, respond with concise, creative lab reports or conversational guidance (2-3 paragraphs).
- For structured data requests, return ONLY a raw JSON object conforming to the specified JSON schema. Do not include markdown wraps (like ```json) or any conversational preamble.
- Each suggestion "reason" must be a concise, scientific, mixology-focused explanation of MAX 12 words (e.g., "neutralizes bitter espresso phenols").
- The overall "reasoning" must be a concise mixology synthesis analysis of MAX 2 sentences.

Structured Output JSON Schema:
{
    "suggestions": [
        {
            "name": "Ingredient Name",
            "reason": "Scientific flavor/chemistry explanation (max 12 words)",
            "amount": 15.0
        }
    ],
    "rebalancing": {
        "Active Ingredient 1": 18.0,
        "Active Ingredient 2": 50.0
    },
    "seal_recommended": false,
    "reasoning": "Scientific mixology analysis (max 2 sentences)."
}"""

        return base_prompt + mode_rules + quality_rules + output_specs

    @classmethod
    def get_default_provider(cls) -> Optional[LLMProvider]:
        """Get the default LLM provider configured in the system."""
        config = SystemConfiguration.get_config()
        if config.default_llm_provider and config.default_llm_provider.is_enabled:
            return config.default_llm_provider
        
        # Fallback to the first enabled provider if default is missing
        return LLMProvider.objects.filter(is_enabled=True).first()

    @classmethod
    def get_static_ingredients_context(cls, drink_type: Optional[str] = None) -> str:
        """Serialize active inventory ingredients into a stable, sorted, rich text format, filtered by mode."""
        from .models import Ingredient
        ingredients = Ingredient.objects.filter(is_in_inventory=True)
        if drink_type:
            ingredients = ingredients.filter(compatible_systems__icontains=drink_type.upper())
        ingredients = ingredients.order_by('name', 'brand')
        
        registry = []
        for ing in ingredients:
            brand_str = f" [{ing.brand}]" if ing.brand else ""
            notes_str = f" | Profile: {ing.flavor_notes}" if ing.flavor_notes else ""
            ai_notes_str = f" | Sensory: {ing.ai_notes}" if ing.ai_notes else ""
            fav_str = " | *FAVORITE*" if ing.favorite else ""
            state_str = f"State: {ing.physical_state} | Function: {ing.mixology_function}"
            
            if ing.physical_state == 'SOLID_EXTRACTABLE':
                decaf_str = "Decaf" if ing.is_decaf else "Regular"
                registry.append(
                    f"- {ing.name}{brand_str} ({state_str} | Roast: {ing.roast_level} | {decaf_str} | Origin: {ing.origin or 'Unknown'}"
                    f"{notes_str}{ai_notes_str}{fav_str})"
                )
            else:
                registry.append(
                    f"- {ing.name}{brand_str} ({state_str} | Category: {ing.category}"
                    f"{notes_str}{ai_notes_str}{fav_str})"
                )
        return "\n".join(registry)

    @classmethod
    def _mock_chat(cls, user_prompt: str, context: Optional[str] = None) -> str:
        """Return realistic JSON/text payloads in MOCK_MODE."""
        if "[STRUCTURED DATA REQUEST]" in user_prompt:
            if "COFFEE" in user_prompt:
                return json.dumps({
                    "suggestions": [
                        {
                            "name": "Vanilla",
                            "reason": "Adds creamy sweet vanilla notes",
                            "amount": 15.0,
                            "profile": {"intensity": 1, "sweetness": 5, "acidity": 1, "bitterness": 1, "complexity": 2}
                        },
                        {
                            "name": "Caramel Apple",
                            "reason": "Adds buttery caramel notes",
                            "amount": 15.0,
                            "profile": {"intensity": 3, "sweetness": 4, "acidity": 2, "bitterness": 1, "complexity": 3}
                        },
                        {
                            "name": "Mint",
                            "reason": "Provides a clean, cooling accent",
                            "amount": 15.0,
                            "profile": {"intensity": 3, "sweetness": 1, "acidity": 1, "bitterness": 2, "complexity": 2}
                        },
                        {
                            "name": "Cucumber",
                            "reason": "Adds a crisp refreshing undertone",
                            "amount": 15.0,
                            "profile": {"intensity": 2, "sweetness": 1, "acidity": 1, "bitterness": 1, "complexity": 2}
                        },
                        {
                            "name": "Espresso Roast Blend",
                            "reason": "Reinforces bold dark roast flavor",
                            "amount": 18.0,
                            "profile": {"intensity": 5, "sweetness": 2, "acidity": 2, "bitterness": 4, "complexity": 3}
                        },
                        {
                            "name": "Hazelnut",
                            "reason": "Offers sweet nutty complexity",
                            "amount": 15.0,
                            "profile": {"intensity": 2, "sweetness": 4, "acidity": 1, "bitterness": 1, "complexity": 2}
                        },
                        {
                            "name": "Cinnamon",
                            "reason": "Warm baking spice warmth",
                            "amount": 15.0,
                            "profile": {"intensity": 3, "sweetness": 2, "acidity": 1, "bitterness": 2, "complexity": 3}
                        },
                        {
                            "name": "Chocolate Syrup",
                            "reason": "Deep rich cocoa notes",
                            "amount": 15.0,
                            "profile": {"intensity": 4, "sweetness": 4, "acidity": 1, "bitterness": 3, "complexity": 4}
                        },
                        {
                            "name": "Whole Milk",
                            "reason": "Provides rich dairy suspension",
                            "amount": 50.0,
                            "profile": {"intensity": 1, "sweetness": 3, "acidity": 1, "bitterness": 1, "complexity": 2}
                        },
                        {
                            "name": "Heavy Cream",
                            "reason": "Elevates lipid mouthfeel thickness",
                            "amount": 15.0,
                            "profile": {"intensity": 2, "sweetness": 3, "acidity": 1, "bitterness": 1, "complexity": 2}
                        },
                        {
                            "name": "Oat Milk",
                            "reason": "Silky grain-based body profile",
                            "amount": 50.0,
                            "profile": {"intensity": 2, "sweetness": 3, "acidity": 1, "bitterness": 1, "complexity": 2}
                        },
                        {
                            "name": "Honey",
                            "reason": "Nectarous viscosity stabilizer",
                            "amount": 15.0,
                            "profile": {"intensity": 2, "sweetness": 5, "acidity": 2, "bitterness": 1, "complexity": 3}
                        }
                    ],
                    "rebalancing": {
                        "Sumatra Mandheling": 18.0,
                        "Whole Milk": 50.0
                    },
                    "seal_recommended": False,
                    "reasoning": "Standard coffee extraction profile (MOCK_MODE)."
                })
            return json.dumps({
                "suggestions": [
                    {
                        "name": "Lemon Lime",
                        "reason": "Acidity balances sweetness",
                        "amount": 25.0,
                        "profile": {"intensity": 4, "sweetness": 2, "acidity": 5, "bitterness": 1, "complexity": 2}
                    },
                    {
                        "name": "Club Soda",
                        "reason": "Effervescence provides clean background",
                        "amount": 120.0,
                        "profile": {"intensity": 1, "sweetness": 1, "acidity": 2, "bitterness": 1, "complexity": 1}
                    },
                    {
                        "name": "Vanilla",
                        "reason": "Adds smooth vanilla undertones",
                        "amount": 15.0,
                        "profile": {"intensity": 1, "sweetness": 5, "acidity": 1, "bitterness": 1, "complexity": 2}
                    },
                    {
                        "name": "Mint",
                        "reason": "Provides a clean, cooling finish",
                        "amount": 15.0,
                        "profile": {"intensity": 3, "sweetness": 1, "acidity": 1, "bitterness": 2, "complexity": 2}
                    },
                    {
                        "name": "Strawberry",
                        "reason": "Infuses bright berry sweetness",
                        "amount": 20.0,
                        "profile": {"intensity": 2, "sweetness": 4, "acidity": 2, "bitterness": 1, "complexity": 2}
                    },
                    {
                        "name": "Ginger Syrup",
                        "reason": "Zesty heat spice bridge",
                        "amount": 15.0,
                        "profile": {"intensity": 4, "sweetness": 3, "acidity": 2, "bitterness": 2, "complexity": 3}
                    },
                    {
                        "name": "Peach Syrup",
                        "reason": "Fleshy stone fruit sweetness",
                        "amount": 20.0,
                        "profile": {"intensity": 2, "sweetness": 4, "acidity": 2, "bitterness": 1, "complexity": 2}
                    },
                    {
                        "name": "Mango Syrup",
                        "reason": "Rich tropical ester profile",
                        "amount": 25.0,
                        "profile": {"intensity": 3, "sweetness": 4, "acidity": 2, "bitterness": 1, "complexity": 3}
                    },
                    {
                        "name": "Raspberry Syrup",
                        "reason": "Tart red berry acidity",
                        "amount": 15.0,
                        "profile": {"intensity": 3, "sweetness": 3, "acidity": 4, "bitterness": 1, "complexity": 2}
                    },
                    {
                        "name": "Lavender Syrup",
                        "reason": "Soft floral herbal aroma",
                        "amount": 10.0,
                        "profile": {"intensity": 2, "sweetness": 3, "acidity": 1, "bitterness": 2, "complexity": 3}
                    },
                    {
                        "name": "Hibiscus Syrup",
                        "reason": "Cranberry-like botanical tartness",
                        "amount": 15.0,
                        "profile": {"intensity": 3, "sweetness": 2, "acidity": 4, "bitterness": 2, "complexity": 3}
                    },
                    {
                        "name": "Grapefruit Syrup",
                        "reason": "Bitter citrus clean edge",
                        "amount": 20.0,
                        "profile": {"intensity": 4, "sweetness": 2, "acidity": 4, "bitterness": 3, "complexity": 3}
                    }
                ],
                "rebalancing": {},
                "seal_recommended": False,
                "reasoning": "Standard laboratory carbonation enhancement (MOCK_MODE)."
            })
        elif "[AUTONOMOUS SYNTHESIS REQUEST]" in user_prompt:
            if "coffee drink" in user_prompt:
                return json.dumps({
                    "design_intent": "A rich milk-balanced double espresso (MOCK_MODE).",
                    "selection": [
                        { "name": "Espresso", "amount": 18.0, "role": "Base extraction" },
                        { "name": "Whole Milk", "amount": 50.0, "role": "Creamy body" }
                    ]
                })
            return json.dumps({
                "design_intent": "A refreshing carbonated citrus blend (MOCK_MODE).",
                "selection": [
                    { "name": "Lemon Syrup", "amount": 50.0, "role": "Base sweetener" },
                    { "name": "Club Soda", "amount": 150.0, "role": "Carbonation baseline" }
                ]
            })
        elif "FLAVOR SYNTHESIS REPORT" in user_prompt:
            return (
                "The selected ingredients combine to form a highly balanced, refreshing flavor profile (MOCK_MODE). "
                "The acidity of the citrus elements cuts through the sweetness of the syrup base, creating a pleasant and bright flavor synergy.\n\n"
                "Expect a clean opening with a burst of citrus notes, followed by a sweet and textured body. "
                "The finish is crisp and leaves a lingering lime zest aroma on the palate."
            )
        elif "[BATCH CHEMICAL ANALYSIS]" in user_prompt:
            names = re.findall(r'- Name:\s*([^,\n]+)', user_prompt)
            results = []
            for n in names:
                results.append({
                    "name": n.strip(),
                    "intensity": 3.0,
                    "sweetness": 3.0,
                    "acidity": 3.0,
                    "bitterness": 1.0,
                    "complexity": 3.0,
                    "base_suitability": 3.0,
                    "accent_suitability": 3.0,
                    "category": "sweet",
                    "ingredient_type": "SODA_SYRUP",
                    "is_ready_to_drink": False,
                    "is_dry": False,
                    "compatible_systems": "SODA,SLUSHIE",
                    "ai_notes": "Mock notes for batch analysis.",
                    "roast_level": "MEDIUM",
                    "is_decaf": False,
                    "body_intensity": 3,
                    "acidity_score": 3,
                    "bitterness_score": 3,
                    "flavor_notes": "earthy, herbal"
                })
            if not results:
                results.append({
                    "name": "Default Ingredient",
                    "intensity": 3.0,
                    "sweetness": 3.0,
                    "acidity": 3.0,
                    "bitterness": 1.0,
                    "complexity": 3.0,
                    "base_suitability": 3.0,
                    "accent_suitability": 3.0,
                    "category": "sweet",
                    "ingredient_type": "SODA_SYRUP",
                    "is_ready_to_drink": False,
                    "is_dry": False,
                    "compatible_systems": "SODA,SLUSHIE",
                    "ai_notes": "Mock notes for default ingredient.",
                    "roast_level": "MEDIUM",
                    "is_decaf": False,
                    "body_intensity": 3,
                    "acidity_score": 3,
                    "bitterness_score": 3,
                    "flavor_notes": "earthy, herbal"
                })
            return json.dumps(results)
        elif "Analyze this ingredient" in user_prompt:
            return json.dumps({
                "intensity": 3.0,
                "sweetness": 3.0,
                "acidity": 3.0,
                "bitterness": 1.0,
                "complexity": 3.0,
                "base_suitability": 3.0,
                "accent_suitability": 3.0,
                "category": "citrus",
                "ingredient_type": "SODA_SYRUP",
                "is_ready_to_drink": False,
                "is_dry": False,
                "compatible_systems": "SODA,SLUSHIE",
                "ai_notes": "Mock notes for single analysis.",
                "roast_level": "MEDIUM",
                "is_decaf": False,
                "body_intensity": 3,
                "acidity_score": 3,
                "bitterness_score": 3,
                "flavor_notes": "citrus, sweet"
            })
        else:
            return "This is a mock laboratory response from the Beverage Laboratory AI Substrate in offline MOCK_MODE."

    @classmethod
    def chat(cls, user_prompt: str, history: Optional[List[Dict[str, str]]] = None, provider: Optional[LLMProvider] = None, context: Optional[Union[str, List[str]]] = None, drink_type: Optional[str] = None) -> str:
        """
        Send a prompt to the configured LLM provider.
        history: List of previous messages for context.
        context: Optional additional context (e.g. inventory registry).
        """
        if os.environ.get('MOCK_MODE', 'False').lower() in ('true', '1', 't'):
            logger.info("AISynthesis - Info - MOCK_MODE active. Returning mock response.")
            return cls._mock_chat(user_prompt, context)

        if not provider:
            provider = cls.get_default_provider()
        
        if not provider:
            return "Error: No AI Laboratory Assistant is configured or enabled. Please check settings."

        system_content = cls.get_system_prompt(drink_type=drink_type)
        if context:
            if isinstance(context, list):
                context_str = "\n".join(context)
            else:
                context_str = str(context)
            system_content += f"\n\nUSER'S LABORATORY INVENTORY REGISTRY:\n{context_str}"

        messages = [{"role": "system", "content": system_content}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        logger.info(
            f"AISynthesis - Info - Synthesis Request to {provider.name} | "
            f"Model: {provider.default_model} | System Instructions: {len(system_content)} chars | "
            f"Payload: {user_prompt[:250]}{'...' if len(user_prompt) > 250 else ''}"
        )

        try:
            if provider.provider_type == 'OPENAI':
                return cls._call_openai(provider, messages)
            elif provider.provider_type == 'CLAUDE':
                return cls._call_claude(provider, messages)
            elif provider.provider_type == 'GEMINI':
                return cls._call_gemini(provider, messages)
            elif provider.provider_type == 'OLLAMA':
                return cls._call_ollama(provider, messages)
            else:
                # Generic OpenAI-compatible
                return cls._call_openai(provider, messages)
        except Exception as e:
            logger.error(f"AICommunication - Error - Laboratory AI Communication Failure ({provider.name}): {e}")
            return f"Laboratory Error: Failed to reach the assistant ({str(e)})."

    @classmethod
    def chat_stream(cls, user_prompt: str, history: Optional[List[Dict[str, str]]] = None, provider: Optional[LLMProvider] = None, context: Optional[Union[str, List[str]]] = None, drink_type: Optional[str] = None) -> Generator[str, None, None]:
        """Stream a prompt response from the configured LLM provider."""
        if os.environ.get('MOCK_MODE', 'False').lower() in ('true', '1', 't'):
            text = cls.chat(user_prompt, history, provider, context, drink_type=drink_type)
            yield f"data: {json.dumps({'chunk': text})}\n\n"
            return

        if not provider:
            provider = cls.get_default_provider()
        
        if not provider:
            error_chunk = json.dumps({'chunk': "Error: No AI Laboratory Assistant is configured or enabled. Please check settings."})
            yield f"data: {error_chunk}\n\n"
            return

        system_content = cls.get_system_prompt(drink_type=drink_type)
        if context:
            if isinstance(context, list):
                context_str = "\n".join(context)
            else:
                context_str = str(context)
            system_content += f"\n\nUSER'S LABORATORY INVENTORY REGISTRY:\n{context_str}"

        messages = [{"role": "system", "content": system_content}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        try:
            if provider.provider_type == 'OPENAI':
                yield from cls._call_openai_stream(provider, messages)
            elif provider.provider_type == 'CLAUDE':
                yield from cls._call_claude_stream(provider, messages)
            elif provider.provider_type == 'GEMINI':
                yield from cls._call_gemini_stream(provider, messages)
            elif provider.provider_type == 'OLLAMA':
                yield from cls._call_ollama_stream(provider, messages)
            else:
                yield from cls._call_openai_stream(provider, messages)
        except Exception as e:
            logger.error(f"AICommunication - Error - Laboratory AI Communication Failure ({provider.name}): {e}")
            error_chunk = json.dumps({'chunk': f"Laboratory Error: Failed to reach the assistant ({str(e)})."})
            yield f"data: {error_chunk}\n\n"

    @classmethod
    def keep_warm_provider(cls, provider: LLMProvider) -> bool:
        """Send a keep-alive pulse specifically for a given provider configuration."""
        if not provider or provider.provider_type not in ['OLLAMA', 'CUSTOM', 'ANYTHINGLLM']:
            return False

        try:
            if provider.provider_type == 'OLLAMA':
                # Run preheat suggestions cache to keep KV cache hot and VRAM loaded!
                cls.preheat_suggestions_cache(provider)
                return True
            else:
                # Minimal 1-token chat call for generic endpoints
                cls.chat("ping", history=[], provider=provider)
                return True
        except Exception as e:
            logger.error(f"AIKeepWarm - Error - Laboratory Wakeup Failure for {provider.name}: {e}")
            return False

    @classmethod
    def preheat_suggestions_cache(cls, provider: Optional[LLMProvider] = None) -> None:
        """Pre-heat KV cache for suggestions across all three drink modes."""
        if os.environ.get('MOCK_MODE', 'False').lower() in ('true', '1', 't'):
            return

        if not provider:
            provider = cls.get_default_provider()
        if not provider:
            return

        # Loop through all three active system modes to ensure each prefix is pre-cached
        for drink_type in ['SODA', 'COFFEE', 'SLUSHIE']:
            try:
                # Fetch the static ingredients context filtered by mode
                inventory_context = cls.get_static_ingredients_context(drink_type=drink_type)
                
                # Construct standard dummy query matching the active mode parameters
                prompt = f"""[STRUCTURED DATA REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE].
 
Task: Recommending between 10 to 15 compatible ingredients from the Inventory Registry to create/stabilize a drink compound. Prioritize ingredients marked with '*FAVORITE*'.

[DYNAMIC REQUEST PARAMETERS]:
Current Mode: {drink_type} | Mode: safe and balanced
Active Mixture: NONE - Initial Synthesis
Force Type Constraint: None
Exclusion List: None
"""
                cls.chat(prompt, context=inventory_context, provider=provider, drink_type=drink_type)
                logger.info(f"AIKeepWarm - Info - Preheat KV Cache succeeded for mode '{drink_type}' on provider '{provider.name}'")
            except Exception as e:
                logger.error(f"AIKeepWarm - Error - Preheat KV Cache failed for mode '{drink_type}': {e}")

    @classmethod
    def keep_warm(cls) -> bool:
        """
        Send a lightweight keep-alive pulse to local models to keep them in VRAM.
        """
        provider = cls.get_default_provider()
        return cls.keep_warm_provider(provider)

    @classmethod
    def check_status(cls) -> str:
        """
        Actively check if the configured AI provider is reachable and responsive.
        Returns: 'synchronized', 'dormant', or 'no_provider'
        """
        provider = cls.get_default_provider()
        if not provider:
            return 'no_provider'

        try:
            if provider.provider_type == 'OLLAMA':
                base = cls._resolve_base_url(provider, "http://localhost:11434").rstrip('/')
                model = provider.default_model or "mistral"
                r = requests.post(f"{base}/api/show", json={"name": model}, timeout=10)
                if r.status_code == 200:
                    # Also keep warm while we're at it
                    cls.keep_warm()
                    return 'synchronized'
                return 'dormant'
            elif provider.provider_type in ['OPENAI', 'CLAUDE', 'GEMINI', 'CUSTOM', 'ANYTHINGLLM']:
                # For cloud providers, attempt a lightweight model list call to verify the API key works
                models = cls.list_models(provider)
                return 'synchronized' if models else 'dormant'
            else:
                return 'dormant'
        except Exception as e:
            logger.error(f"AIStatusCheck - Error - Laboratory Status Pulse Failure: {e}")
            return 'dormant'

    @classmethod
    def list_models(cls, provider: LLMProvider) -> List[str]:
        """Fetch available models from the provider's API."""
        try:
            if provider.provider_type in ['OPENAI', 'CLAUDE', 'CUSTOM', 'ANYTHINGLLM']:
                return cls._list_openai_models(provider)
            elif provider.provider_type == 'OLLAMA':
                return cls._list_ollama_models(provider)
            elif provider.provider_type == 'GEMINI':
                return cls._list_gemini_models(provider)
            else:
                return []
        except Exception as e:
            logger.error(f"AIModelsFetch - Error - Error fetching models: {e}")
            return []

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
        from .models import Ingredient
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
        from .models import Ingredient
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

    @staticmethod
    def _extract_json(text: str) -> Optional[Any]:
        """Resiliently extract the first JSON object or array from a string."""
        if not text:
            return None
        try:
            # Look for everything between the first { or [ and the last } or ]
            match = re.search(r'([\[\{].*[\]\}])', text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            # Fallback: direct attempt
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _safe_request(method: str, url: str, attempts: int = 3, timeout: int = 30, **kwargs: Any) -> requests.Response:
        """Execute a request with automated retry logic and exponential backoff."""
        from urllib.parse import urlparse
        import socket
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if hostname:
                ip = socket.gethostbyname(hostname)
                if ip == "169.254.169.254" or ip.startswith("169.254."):
                    raise ValueError("SSRF Block: Link-local and metadata IPs are banned.")
        except Exception as e:
            if "SSRF Block" in str(e):
                raise e

        last_error = None
        for i in range(attempts):
            try:
                # Escalating timeout for each retry
                current_timeout = timeout + (i * 15)
                response = requests.request(method, url, timeout=current_timeout, **kwargs)
                response.raise_for_status()
                return response
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                last_error = e
                # Don't sleep on last attempt
                if i < attempts - 1:
                    import time
                    time.sleep(1.5 * (i + 1)) # Exponential backoff: 1.5s, 3s...
                continue
        
        # If we get here, all attempts failed
        raise last_error

    @classmethod
    def _list_openai_models(cls, provider: LLMProvider) -> List[str]:
        url = cls._resolve_base_url(provider, "https://api.openai.com/v1").rstrip('/') + "/models"
        headers = {"Authorization": f"Bearer {provider.api_key}"} if provider.api_key else {}
        if provider.provider_type == 'CLAUDE':
            headers = {
                "x-api-key": provider.api_key,
                "anthropic-version": "2023-06-01"
            }
        
        response = cls._safe_request('GET', url, headers=headers, timeout=10)
        data = response.json()
        return [m['id'] for m in data.get('data', [])]

    @classmethod
    def _list_ollama_models(cls, provider: LLMProvider) -> List[str]:
        url = cls._resolve_base_url(provider, "http://localhost:11434").rstrip('/') + "/api/tags"
        response = cls._safe_request('GET', url, timeout=10)
        data = response.json()
        return [m['name'] for m in data.get('models', [])]

    @classmethod
    def _list_gemini_models(cls, provider: LLMProvider) -> List[str]:
        api_key = provider.api_key
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        response = cls._safe_request('GET', url, timeout=10)
        data = response.json()
        # Filter for models that support generateContent
        return [m['name'].replace('models/', '') for m in data.get('models', []) 
                if 'generateContent' in m.get('supportedGenerationMethods', [])]

    @classmethod
    def _call_openai(cls, provider: LLMProvider, messages: List[Dict[str, str]]) -> str:
        url = cls._resolve_base_url(provider, "https://api.openai.com/v1/chat/completions")
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json"
        }
        model_name = provider.default_model or "gpt-3.5-turbo"
        data = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7
        }
        if model_name.startswith('o1') or model_name.startswith('o3'):
            if getattr(provider, 'enable_thinking', False):
                data["reasoning_effort"] = getattr(provider, 'thinking_effort', 'medium')
            else:
                data["reasoning_effort"] = "low"
        else:
            # Enforce JSON output mode if a structured data query is detected
            user_prompt = messages[-1]['content'] if messages else ""
            is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
            if is_json_request:
                data["response_format"] = {"type": "json_object"}

        response = cls._safe_request('POST', url, headers=headers, json=data, timeout=30)
        result = response.json()
        
        content = result['choices'][0]['message']['content'] if 'choices' in result else ""
        
        logger.info(f"AISynthesis - Info - Raw LLM Signal ({provider.name}): {len(content)} characters received.")
        if not content.strip():
             logger.warning(f"AISynthesis - Warning - Empty signal from {provider.name}! Full response: {result}")
             
        return content

    @classmethod
    def _call_ollama(cls, provider: LLMProvider, messages: List[Dict[str, str]]) -> str:
        # Ollama /api/chat — native format.
        url = cls._resolve_base_url(provider, "http://localhost:11434").rstrip('/') + "/api/chat"
        model_name = provider.default_model or "mistral"
        if getattr(provider, 'enable_thinking', False):
            if "gpt-oss" in model_name.lower():
                think_val = getattr(provider, 'thinking_effort', 'medium')
            else:
                think_val = True
        else:
            think_val = False

        data = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "think": think_val,
            "options": {
                "num_predict": 2048,
                "temperature": 0.5
            }
        }
        user_prompt = messages[-1]['content'] if messages else ""
        is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
        if is_json_request:
            data["format"] = "json"

        logger.warning(f"Ollama Chat - Request payload: {json.dumps(data)}")
        response = cls._safe_request('POST', url, json=data, timeout=120)
        result = response.json()
        
        content = result.get('message', {}).get('content', "")
        
        logger.info(f"AISynthesis - Info - Raw LLM Signal (Ollama): {len(content)} characters received.")
        if not content.strip():
             logger.warning(f"AISynthesis - Warning - Empty signal from Ollama! Full Response: {result}")
             
        return content

    @classmethod
    def _call_claude(cls, provider: LLMProvider, messages: List[Dict[str, str]]) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": provider.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        system = messages[0]['content']
        actual_messages = messages[1:]
        
        model_name = provider.default_model or "claude-3-haiku-20240307"
        
        data = {
            "model": model_name,
            "system": system,
            "messages": actual_messages,
            "max_tokens": 1024
        }
        
        if "claude-3-7" in model_name.lower() or "sonnet" in model_name.lower():
            if getattr(provider, 'enable_thinking', False):
                budget = 1024 if getattr(provider, 'thinking_effort', 'medium') == 'low' else (2048 if getattr(provider, 'thinking_effort', 'medium') == 'medium' else 4096)
                data["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget
                }
                data["max_tokens"] = budget + 1024

        response = cls._safe_request('POST', url, headers=headers, json=data, timeout=30)
        return response.json()['content'][0]['text']

    @classmethod
    def _call_gemini(cls, provider: LLMProvider, messages: List[Dict[str, str]]) -> str:
        api_key = provider.api_key
        model = provider.default_model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        system_text = messages[0]['content'] if messages and messages[0]['role'] == 'system' else ""
        actual_messages = messages[1:] if system_text else messages
        
        contents = []
        for m in actual_messages:
            role = "user" if m['role'] == 'user' else "model"
            contents.append({"role": role, "parts": [{"text": m['content']}]})
            
        data: Dict[str, Any] = {"contents": contents}
        if system_text:
            data["system_instruction"] = {"parts": [{"text": system_text}]}
            
        user_prompt = messages[-1]['content'] if messages else ""
        is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
        
        generation_config = {}
        if is_json_request:
            generation_config["responseMimeType"] = "application/json"
            
        if "thinking" in model.lower():
            if getattr(provider, 'enable_thinking', False):
                budget = 1024 if getattr(provider, 'thinking_effort', 'medium') == 'low' else (2048 if getattr(provider, 'thinking_effort', 'medium') == 'medium' else 4096)
                generation_config["thinkingConfig"] = {"thinkingBudget": budget}
            else:
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
                
        if generation_config:
            data["generationConfig"] = generation_config

        response = cls._safe_request('POST', url, json=data, timeout=30)
        result = response.json()
        
        try:
            content = result['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            content = ""
            
        logger.info(f"AISynthesis - Info - Raw LLM Signal (Gemini): {len(content)} characters received.")
        if not content.strip():
             logger.warning(f"AISynthesis - Warning - Empty signal from Gemini! Full Response: {result}")
             
        return content

    @classmethod
    def _call_openai_stream(cls, provider: LLMProvider, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        url = cls._resolve_base_url(provider, "https://api.openai.com/v1/chat/completions")
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json"
        }
        model_name = provider.default_model or "gpt-3.5-turbo"
        data = {"model": model_name, "messages": messages, "temperature": 0.7, "stream": True}
        if model_name.startswith('o1') or model_name.startswith('o3'):
            if getattr(provider, 'enable_thinking', False):
                data["reasoning_effort"] = getattr(provider, 'thinking_effort', 'medium')
            else:
                data["reasoning_effort"] = "low"
        else:
            user_prompt = messages[-1]['content'] if messages else ""
            is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
            if is_json_request:
                data["response_format"] = {"type": "json_object"}

        response = requests.post(url, headers=headers, json=data, stream=True, timeout=60)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    if data_str == '[DONE]': break
                    try:
                        data_json = json.loads(data_str)
                        if 'choices' in data_json and len(data_json['choices']) > 0:
                            delta = data_json['choices'][0].get('delta', {})
                            if 'content' in delta:
                                yield f"data: {json.dumps({'chunk': delta['content']})}\n\n"
                    except json.JSONDecodeError: pass

    @classmethod
    def _call_ollama_stream(cls, provider: LLMProvider, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        url = cls._resolve_base_url(provider, "http://localhost:11434").rstrip('/') + "/api/chat"
        model_name = provider.default_model or "mistral"
        if getattr(provider, 'enable_thinking', False):
            if "gpt-oss" in model_name.lower():
                think_val = getattr(provider, 'thinking_effort', 'medium')
            else:
                think_val = True
        else:
            think_val = False

        data = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "think": think_val,
            "options": {
                "num_predict": 2048,
                "temperature": 0.5
            }
        }
        user_prompt = messages[-1]['content'] if messages else ""
        is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
        if is_json_request:
            data["format"] = "json"

        logger.warning(f"Ollama Stream Chat - Request payload: {json.dumps(data)}")
        response = requests.post(url, json=data, stream=True, timeout=120)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                try:
                    data_json = json.loads(line.decode('utf-8'))
                    if 'message' in data_json and 'content' in data_json['message']:
                        yield f"data: {json.dumps({'chunk': data_json['message']['content']})}\n\n"
                except json.JSONDecodeError: pass

    @classmethod
    def _call_claude_stream(cls, provider: LLMProvider, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": provider.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        system = messages[0]['content']
        actual_messages = messages[1:]
        
        model_name = provider.default_model or "claude-3-haiku-20240307"
        
        data = {
            "model": model_name,
            "system": system,
            "messages": actual_messages,
            "max_tokens": 1024,
            "stream": True
        }
        
        if "claude-3-7" in model_name.lower() or "sonnet" in model_name.lower():
            if getattr(provider, 'enable_thinking', False):
                budget = 1024 if getattr(provider, 'thinking_effort', 'medium') == 'low' else (2048 if getattr(provider, 'thinking_effort', 'medium') == 'medium' else 4096)
                data["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget
                }
                data["max_tokens"] = budget + 1024

        response = requests.post(url, headers=headers, json=data, stream=True, timeout=60)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    try:
                        data_json = json.loads(data_str)
                        if data_json.get('type') == 'content_block_delta':
                            delta = data_json.get('delta', {})
                            if delta.get('type') == 'text_delta':
                                yield f"data: {json.dumps({'chunk': delta.get('text', '')})}\n\n"
                    except json.JSONDecodeError: pass

    @classmethod
    def _call_gemini_stream(cls, provider: LLMProvider, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        api_key = provider.api_key
        model = provider.default_model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
        system_text = messages[0]['content'] if messages and messages[0]['role'] == 'system' else ""
        actual_messages = messages[1:] if system_text else messages
        contents = [{"role": "user" if m['role'] == 'user' else "model", "parts": [{"text": m['content']}]} for m in actual_messages]
        data = {"contents": contents}
        if system_text: data["system_instruction"] = {"parts": [{"text": system_text}]}
        
        user_prompt = messages[-1]['content'] if messages else ""
        is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
        
        generation_config = {}
        if is_json_request:
            generation_config["responseMimeType"] = "application/json"
            
        if "thinking" in model.lower():
            if getattr(provider, 'enable_thinking', False):
                budget = 1024 if getattr(provider, 'thinking_effort', 'medium') == 'low' else (2048 if getattr(provider, 'thinking_effort', 'medium') == 'medium' else 4096)
                generation_config["thinkingConfig"] = {"thinkingBudget": budget}
            else:
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
                
        if generation_config:
            data["generationConfig"] = generation_config

        response = requests.post(url, json=data, stream=True, timeout=60)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    try:
                        data_json = json.loads(data_str)
                        if 'candidates' in data_json and len(data_json['candidates']) > 0:
                            parts = data_json['candidates'][0].get('content', {}).get('parts', [])
                            if parts:
                                yield f"data: {json.dumps({'chunk': parts[0].get('text', '')})}\n\n"
                    except json.JSONDecodeError: pass
