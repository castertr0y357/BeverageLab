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

    SYSTEM_PROMPT = """
    You are the Lead Creative Mixologist at the "Beverage Laboratory," a high-end, 
    scientific-themed soda and coffee mixing facility. Your goal is to assist users 
    in synthesizing perfect liquid compounds.

    Personality:
    - You are enthusiastic about flavor science.
    - You use laboratory terminology (synthesis, compound, reagent, base, stabilizer).
    - You are a "Creative Mixologist"—you value bold, experimental pairings over 
      safe bets, but you always anchor them in flavor balance.
    - You understand Sweetness, Acidity, Bitterness, Intensity, and Complexity as the core axes 
      of a drink.
    - Complexity measures the depth and "layers" of a flavor (1: simple/one-note, 5: deep/multi-layered).

    Context:
    - You have access to a user's current inventory and their high-rated recipes.
    - Users will send you their "Current Compound" (selected ingredients).
    - You should suggest additional reagents to "Bridge" or "Stabilize" the mix (usually 1-3 more items).
    - Suggest specific ml/g or "parts" ratios. Some mixes benefit from a 1:1 parity, while others need small "flavor notes" to add complexity without overpowering.
    - Explain the flavor science: why does the acidity of Lemon balance the bitterness of Espresso?

    Guidelines:
    - Keep responses concise (2-3 short paragraphs).
    - Be supportive of "Experimental Mode" requests.
    """
    
    SUGGESTION_EXAMPLE = '[{"name": "Lemon Syrup", "amount": 25.0, "reason": "Acidity balances sweetness", "profile": {"intensity": 4, "sweetness": 2, "acidity": 5, "bitterness": 1, "complexity": 2}}]'
    
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
    "ai_notes": string
}"""

    @classmethod
    def get_default_provider(cls) -> Optional[LLMProvider]:
        """Get the default LLM provider configured in the system."""
        config = SystemConfiguration.get_config()
        if config.default_llm_provider and config.default_llm_provider.is_enabled:
            return config.default_llm_provider
        
        # Fallback to the first enabled provider if default is missing
        return LLMProvider.objects.filter(is_enabled=True).first()

    @classmethod
    def _mock_chat(cls, user_prompt: str, context: Optional[str] = None) -> str:
        """Return realistic JSON/text payloads in MOCK_MODE."""
        if "[STRUCTURED DATA REQUEST]" in user_prompt:
            return json.dumps({
                "suggestions": [
                    {
                        "name": "Lemon Syrup",
                        "reason": "Acidity balances sweetness",
                        "resonance": 85,
                        "amount": 25.0,
                        "profile": {"intensity": 4, "sweetness": 2, "acidity": 5, "bitterness": 1, "complexity": 2}
                    },
                    {
                        "name": "Club Soda",
                        "reason": "Effervescence provides clean background",
                        "resonance": 90,
                        "amount": 120.0,
                        "profile": {"intensity": 1, "sweetness": 1, "acidity": 2, "bitterness": 1, "complexity": 1}
                    }
                ],
                "rebalancing": {},
                "seal_recommended": False,
                "seal_resonance": 75,
                "reasoning": "Standard laboratory carbonation enhancement (MOCK_MODE)."
            })
        elif "[AUTONOMOUS SYNTHESIS REQUEST]" in user_prompt:
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
                    "ai_notes": "Mock notes for batch analysis."
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
                    "ai_notes": "Mock notes for default ingredient."
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
                "ai_notes": "Mock notes for single analysis."
            })
        else:
            return "This is a mock laboratory response from the Beverage Laboratory AI Substrate in offline MOCK_MODE."

    @classmethod
    def chat(cls, user_prompt: str, history: Optional[List[Dict[str, str]]] = None, provider: Optional[LLMProvider] = None, context: Optional[str] = None) -> str:
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

        system_content = cls.SYSTEM_PROMPT
        if context:
            system_content += f"\n\nUSER'S LABORATORY INVENTORY REGISTRY:\n{context}"

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
    def chat_stream(cls, user_prompt: str, history: Optional[List[Dict[str, str]]] = None, provider: Optional[LLMProvider] = None, context: Optional[str] = None) -> Generator[str, None, None]:
        """Stream a prompt response from the configured LLM provider."""
        if os.environ.get('MOCK_MODE', 'False').lower() in ('true', '1', 't'):
            text = cls.chat(user_prompt, history, provider, context)
            yield f"data: {json.dumps({'chunk': text})}\n\n"
            return

        if not provider:
            provider = cls.get_default_provider()
        
        if not provider:
            error_chunk = json.dumps({'chunk': "Error: No AI Laboratory Assistant is configured or enabled. Please check settings."})
            yield f"data: {error_chunk}\n\n"
            return

        system_content = cls.SYSTEM_PROMPT
        if context:
            system_content += f"\n\nUSER'S LABORATORY INVENTORY REGISTRY:\n{context}"

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
    def keep_warm(cls) -> bool:
        """
        Send a lightweight keep-alive pulse to local models to keep them in VRAM.
        Uses Ollama's /api/show endpoint — returns model metadata instantly with
        zero token generation, so it never blocks the Ollama request queue.
        """
        provider = cls.get_default_provider()
        if not provider or provider.provider_type not in ['OLLAMA', 'CUSTOM', 'ANYTHINGLLM']:
            return False

        try:
            if provider.provider_type == 'OLLAMA':
                base = (provider.base_url or "http://localhost:11434").rstrip('/')
                model = provider.default_model or "mistral"
                # /api/generate with no prompt forces Ollama to seize VRAM 
                # and hold the model memory-resident for the keep_alive duration.
                response = requests.post(
                    f"{base}/api/generate",
                    json={"model": model, "keep_alive": "15m"},
                    timeout=30
                )
                return response.status_code == 200
            else:
                # For custom/AnythingLLM, minimal 1-token chat call
                cls.chat("ping", history=[], provider=provider)
                return True
        except Exception as e:
            logger.error(f"AIKeepWarm - Error - Laboratory Wakeup Failure for {provider.name}: {e}")
            return False

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
                base = (provider.base_url or "http://localhost:11434").rstrip('/')
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
    def suggest_autonomous(cls, ingredients: List[str], mode: str = 'standard', inventory: Optional[str] = None, exclude: Optional[List[str]] = None, retry_note: Optional[str] = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        Generate multiple proactive suggestions as a structured JSON array.
        Returns 3 specific ingredient recommendations from the inventory.
        """
        tone = "safe and balanced" if mode == 'standard' else "bold and experimental"
        exclude_context = f" Exclude these previously suggested items: {', '.join(exclude)}." if exclude else ""
        retry_context = f"\n\n[RETRY COMMAND]: {retry_note}\n" if retry_note else ""
        
        prompt = f"""[STRUCTURED DATA REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE].{retry_context}

Current Compound: {', '.join(ingredients)}
Lab Mode: {tone}{exclude_context}

Task: Identify 3 to 5 ingredients from the Inventory Registry below that pair well with the current mix AND determine if it should be "sealed".

Rules:
1. USE THE EXACT NOMENCLATURE from the Inventory Registry for suggestions.
2. Provide a 'seal_recommended' boolean and a 'seal_resonance' (0-100). Set seal_recommended to TRUE if the compound is complete.
3. REBALANCING: For every ingredient already in the 'Current Compound', prescribe an optimal 'amount' (ml for Soda/Slushie, g for Coffee) based on holistic balance.
4. For new suggestions, provide a specific 'amount' and a "Chemical Profile Overload" (intensity, sweetness, acidity, bitterness, complexity) on a scale of 1-5.
5. Aim for molecular balance: Total syrup for a 1.0L batch MUST NOT exceed 160ml. Scale proportions accordingly (e.g. 80ml Base + 40ml Payload + 20ml Accent + 20ml Deep Accent = 160ml).

JSON OUTPUT FORMAT:
{{
    "suggestions": [
        {{ "name": "Ingredient Name", "reason": "...", "resonance": 85, "amount": 25.0, "profile": {{...}} }},
        ...
    ],
    "rebalancing": {{
        "Existing Ingredient Name": 100.0
    }},
    "seal_recommended": true/false,
    "seal_resonance": 95,
    "reasoning": "Brief overview of the balance strategy"
}}

Inventory Registry for Selection:
"""
        response = cls.chat(prompt, context=inventory)
        return cls._extract_json(response)

    @classmethod
    def synthesize_surprise_mix(cls, inventory: Optional[str] = None, mode: str = 'standard', drink_type: str = 'SODA') -> Optional[Dict[str, Any]]:
        """
        Autonomous Synthesis: Select a cohesive set of ingredients from the inventory.
        Soda/Slushie: 3 ingredients.
        Coffee: 3-5 ingredients, including a stabilizer.
        """
        tone = "safe and balanced" if mode == 'standard' else "bold and experimental"
        drink_label = {'SODA': 'soda', 'COFFEE': 'coffee drink', 'SLUSHIE': 'slushie'}.get(drink_type, 'drink')
        
        count_limit = "BETWEEN 2 and 4" if drink_type != 'COFFEE' else "BETWEEN 3 and 5"
        extra_rules = ""
        if drink_type == 'COFFEE':
            extra_rules = "5. MANDATORY: For Coffee Lab synthesis, include exactly one 'Additive' or 'Creamer' as a final stabilizer."

        prompt = f"""[AUTONOMOUS SYNTHESIS REQUEST] — RAW JSON DATA ONLY. [NO PREAMBLE].
        
Task: Select {count_limit} ingredients from the Inventory Registry below to create a cohesive {drink_label} compound.
Lab Mode: {tone}

Rules:
1. USE THE EXACT NOMENCLATURE from the Inventory Registry.
2. Select a base (e.g. coffee/syrup) and complementary reagents.
3. Provide a suggested 'amount' (ml or g) for each. Use 1:1 ratios for balance or small amounts for "flavor notes".
4. Provide a 'design_intent' (overall reasoning for the pairing, max 20 words).
5. For each ingredient, provide a specific 'role' (max 8 words).
{extra_rules}

OUTPUT FORMAT: A raw JSON object.
{cls.SURPRISE_MIX_FORMAT}

Inventory Registry for Selection:
"""
        response = cls.chat(prompt, context=inventory)
        return cls._extract_json(response)

    @classmethod
    def synthesize_flavor_summary(cls, ingredients: List[Dict[str, Any]], drink_type: str = 'SODA') -> str:
        """
        Given a finalized set of selected ingredients, produce a brief
        synthesis report: why they work together and what to expect. Plain text, no JSON.
        """
        drink_label = {'SODA': 'soda', 'COFFEE': 'coffee drink', 'SLUSHIE': 'slushie'}.get(drink_type, 'drink')
        ingredient_list = ', '.join(f"{i['name']} (Intensity {i.get('intensity', '?')}/5)" for i in ingredients)
        
        prompt = f"""FLAVOR SYNTHESIS REPORT

Finalized {drink_label} compound: {ingredient_list}

Write a concise 2-paragraph lab report:
Paragraph 1 — FLAVOR SYNERGY: Why do these ingredients work together? Reference specific flavor science (acidity, sweetness, bitterness, intensity balance, complementary/contrasting notes).
Paragraph 2 — EXPECTED TASTE: What will this drink taste like? Describe the opening, body, and finish. Keep it vivid and specific.

Do NOT give preparation instructions. Do NOT suggest more ingredients. No markdown formatting."""
        return cls.chat(prompt)

    @classmethod
    def analyze_flavor_profile(cls, name: str, description: str) -> Optional[Dict[str, float]]:
        """Analyze a flavor and return its chemical profile as JSON."""
        prompt = f"""
        Analyze this ingredient:
        Name: {name}
        Description: {description}

        Return ONLY a JSON object with values from 1.0 to 5.0 (decimals allowed) for these metrics:
        - intensity
        - sweetness
        - acidity
        - bitterness
        - complexity
        - base_suitability (how well it serves as a dominant, high-volume base ingredient)
        - accent_suitability (how well it serves as a low-volume accent / high-impact nuance)
        - ai_notes (a short paragraph of relevant notes about this ingredient's flavor profile, pairings, and mixology recommendations)

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
        
        For each, return values from 1.0 to 5.0 (decimals allowed) for:
        - intensity
        - sweetness
        - acidity
        - bitterness
        - complexity
        - base_suitability (how well it serves as a dominant, high-volume base ingredient)
        - accent_suitability (how well it serves as a low-volume accent / high-impact nuance)
        - ai_notes (a short paragraph of relevant notes about this ingredient's flavor profile, pairings, and mixology recommendations)
        
        OUTPUT FORMAT: A raw JSON array of objects. [NO MARKDOWN] [NO PREAMBLE].
        Example: [{{ "name": "Lemon", "intensity": 4.5, "sweetness": 2.0, "acidity": 5.0, "bitterness": 1.5, "complexity": 1.5, "base_suitability": 4.5, "accent_suitability": 2.0, "ai_notes": "Bright, tart citrus that cuts through heavy syrups and adds freshness." }}]
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
                    time.sleep(1.5 * (i + 1)) # Exponential backoff: 1.5s, 3s...
                continue
        
        # If we get here, all attempts failed
        raise last_error

    @classmethod
    def _list_openai_models(cls, provider: LLMProvider) -> List[str]:
        url = (provider.base_url or "https://api.openai.com/v1").rstrip('/') + "/models"
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
        url = (provider.base_url or "http://localhost:11434").rstrip('/') + "/api/tags"
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
        url = provider.base_url or "https://api.openai.com/v1/chat/completions"
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
            if getattr(provider, 'enable_thinking', True):
                data["reasoning_effort"] = getattr(provider, 'thinking_effort', 'medium')
            else:
                data["reasoning_effort"] = "low"
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
        url = (provider.base_url or "http://localhost:11434").rstrip('/') + "/api/chat"
        model_name = provider.default_model or "mistral"
        if getattr(provider, 'enable_thinking', True):
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
                "num_predict": 2048
            }
        }
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
        
        data = {
            "model": provider.default_model or "claude-3-haiku-20240307",
            "system": system,
            "messages": actual_messages,
            "max_tokens": 1024
        }
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
        url = provider.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json"
        }
        model_name = provider.default_model or "gpt-3.5-turbo"
        data = {"model": model_name, "messages": messages, "temperature": 0.7, "stream": True}
        if model_name.startswith('o1') or model_name.startswith('o3'):
            if getattr(provider, 'enable_thinking', True):
                data["reasoning_effort"] = getattr(provider, 'thinking_effort', 'medium')
            else:
                data["reasoning_effort"] = "low"
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
        url = (provider.base_url or "http://localhost:11434").rstrip('/') + "/api/chat"
        model_name = provider.default_model or "mistral"
        if getattr(provider, 'enable_thinking', True):
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
                "num_predict": 2048
            }
        }
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
        data = {"model": provider.default_model or "claude-3-haiku-20240307", "system": system, "messages": actual_messages, "max_tokens": 1024, "stream": True}
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
