import json
import logging
import random
from typing import Dict, Any, List, Set, Union, Optional, Callable
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.db.models import Q
from ...models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, SystemConfiguration, LLMProvider, BackgroundExecutionTask
from ...tasks_registry import submit_task
from ...recommendations import (
    get_recommendation, get_tiered_recommendation,
    generate_recipe_name, suggest_categories, calculate_recipe_stats
)
from ...ai_service import AIAssistant
from .helpers import *

def save_llm_provider_api(request: HttpRequest) -> JsonResponse:
    """Manage multiple LLM providers (Cloud and Local)."""
    if not request.user.is_staff:
        logger.warning(f"LLMProviderManagement - Warning - Unauthorized API attempt to save LLM provider by {request.user}")
        return JsonResponse({'error': 'Staff authentication required.'}, status=403)
        
    try:
        data = json.loads(request.body)
        pk = data.get('id')
        
        if pk:
            provider = get_object_or_404(LLMProvider, pk=pk)
        else:
            provider = LLMProvider()
            
        provider.name = data.get('name', 'New Provider').strip()
        provider.provider_type = data.get('provider_type', 'OPENAI')
        provider.api_key = data.get('api_key', '').strip()
        provider.base_url = data.get('base_url', '').strip()
        provider.default_model = data.get('default_model', '').strip()
        provider.is_enabled = bool(data.get('is_enabled', False))
        
        enable_thinking = data.get('enable_thinking')
        provider.enable_thinking = bool(enable_thinking) if enable_thinking is not None else False
        
        thinking_effort = data.get('thinking_effort')
        provider.thinking_effort = 'medium' if not thinking_effort else str(thinking_effort).strip().lower()
        
        provider.enable_keep_warm = bool(data.get('enable_keep_warm', False))
        
        provider.save()
        
        # If this is set as default
        if data.get('set_default', False):
            config = SystemConfiguration.get_config()
            config.default_llm_provider = provider
            config.save()
            
        logger.info(f"LLMProviderManagement - Info - Saved LLM Provider '{provider.name}' (ID: {provider.id})")
        return JsonResponse({'status': 'success', 'id': provider.id})
    except Exception as e:
        logger.error(f"LLMProviderManagement - Error - Failed to save provider: {e}")
        return JsonResponse({'error': str(e)}, status=400)

def delete_llm_provider_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Remove an LLM provider configuration."""
    if not request.user.is_staff:
        logger.warning(f"LLMProviderManagement - Warning - Unauthorized API attempt to delete LLM provider {pk} by {request.user}")
        return JsonResponse({'error': 'Forbidden'}, status=403)
    provider = get_object_or_404(LLMProvider, pk=pk)
    name = provider.name
    provider.delete()
    logger.info(f"LLMProviderManagement - Info - Deleted LLM Provider '{name}' (ID: {pk})")
    return JsonResponse({'status': 'success'})

def fetch_provider_models_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Fetch available models for a specific AI provider."""
    provider = get_object_or_404(LLMProvider, pk=pk)
    models = AIAssistant.list_models(provider)
    if models:
        logger.info(f"LLMModelDiscovery - Info - Fetched {len(models)} models for provider '{provider.name}'")
        return JsonResponse({'status': 'success', 'models': models})
    else:
        logger.warning(f"LLMModelDiscovery - Warning - Could not fetch models for provider '{provider.name}'")
        return JsonResponse({'status': 'error', 'message': 'Could not fetch models. Check API keys and base URL.'}, status=400)

def discover_provider_models_api(request: HttpRequest) -> JsonResponse:
    """Fetch models for unsaved provider credentials."""
    if not request.user.is_staff:
        logger.warning(f"LLMModelDiscovery - Warning - Unauthorized API attempt to discover models by {request.user}")
        return JsonResponse({'error': 'Staff credentials required.'}, status=403)
        
    try:
        data = json.loads(request.body)
        provider_type = data.get('provider_type')
        api_key = data.get('api_key', '')
        base_url = data.get('base_url', '')
        
        if not provider_type:
            return JsonResponse({'error': 'Provider technology stack required.'}, status=400)
            
        # Create a temporary, unsaved object for the model list call
        temp_provider = LLMProvider(
            provider_type=provider_type,
            api_key=api_key,
            base_url=base_url
        )
        
        models = AIAssistant.list_models(temp_provider)
        if models:
            logger.info(f"LLMModelDiscovery - Info - Discovered {len(models)} models for temporary provider {provider_type}")
            return JsonResponse({'status': 'success', 'models': models})
        else:
            logger.warning(f"LLMModelDiscovery - Warning - Model discovery returned no models or credentials rejected for {provider_type}")
            return JsonResponse({'status': 'error', 'message': 'Discovery Protocol: No models found or credentials rejected.'}, status=400)
    except Exception as e:
        logger.error(f"LLMModelDiscovery - Error - Molecular Sync Failed: {e}")
        return JsonResponse({'error': f"Molecular Sync Failed: {str(e)}"}, status=500)