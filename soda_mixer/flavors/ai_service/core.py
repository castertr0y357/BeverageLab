import os
import requests
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional, Union, Generator

from ..models import LLMProvider, SystemConfiguration

logger = logging.getLogger(__name__)


from .prompts import AIPromptsMixin
from .providers import AIProvidersMixin
from .warming import AIWarmingMixin
from .analysis import AIAnalysisMixin
from .generation import AIGenerationMixin

class AIAssistant(AIPromptsMixin, AIProvidersMixin, AIWarmingMixin, AIAnalysisMixin, AIGenerationMixin):
    @classmethod
    def get_static_ingredients_context(cls, drink_type: Optional[str] = None) -> str:
            """Serialize active inventory ingredients into a stable, sorted, rich text format, filtered by mode."""
            from ..models import Ingredient
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

