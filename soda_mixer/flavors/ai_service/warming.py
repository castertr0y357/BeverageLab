import os
import requests
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional, Union, Generator

from ..models import LLMProvider, SystemConfiguration

logger = logging.getLogger(__name__)



class AIWarmingMixin:
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

