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
    suggest_categories, calculate_recipe_stats
)
from ...ai_service import AIAssistant
from .helpers import *

def ai_analyze_ingredient_api(request: HttpRequest) -> JsonResponse:
    """Use the LLM to synthesize a chemical flavor profile for a new ingredient."""
    try:
        data = json.loads(request.body)
        name = data.get('name')
        brand = data.get('brand', '')
        description = data.get('description', '')
        
        if not name:
            return JsonResponse({'error': 'Ingredient name required for analysis.'}, status=400)
            
        full_name = f"{brand} {name}" if brand else name
        profile = AIAssistant.analyze_flavor_profile(full_name, description)
        if profile:
            logger.info(f"AIIngredientAnalysis - Info - Analyzed profile for reagent '{name}'")
            return JsonResponse({'status': 'success', 'profile': profile})
        else:
            logger.warning(f"AIIngredientAnalysis - Warning - Chemical analysis failed to yield structured data for '{name}'")
            return JsonResponse({'error': 'Chemical analysis failed to yield structured data.'}, status=500)
    except Exception as e:
        logger.error(f"AIIngredientAnalysis - Error - Failed to analyze ingredient: {e}")
        return JsonResponse({'error': str(e)}, status=500)

def ai_bulk_analyze_api(request: HttpRequest) -> JsonResponse:
    """Perform a batch synthesis of flavor profiles for all reagents in inventory."""
    if not request.user.is_staff:
        logger.warning(f"AIBulkAnalysis - Warning - Unauthorized API attempt to bulk analyze by {request.user}")
        return JsonResponse({'error': 'Staff authentication required.'}, status=403)
        
    task = submit_task("Bulk AI Flavor Analysis", ai_bulk_analyze_task)
    return JsonResponse({'status': 'accepted', 'task_id': str(task.uuid)}, status=202)