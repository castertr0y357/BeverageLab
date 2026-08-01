"""Recommendation engine facade routing to specific drink engines."""

from typing import List, Dict, Any, Optional, Set, Union
from django.db.models import QuerySet
from .models import Ingredient, RecipeIngredient
from .engines import get_engine


def suggest_categories(ingredient_ids: Union[List[int], Set[int]]) -> List[str]:
    """
    Return a list of suggested category name strings based on the ingredients chosen.
    """
    return get_engine('SODA').suggest_categories(ingredient_ids)

def calculate_recipe_stats(recipe_ingredients: Union[List[RecipeIngredient], QuerySet]) -> Dict[str, float]:
    """
    Calculate weighted stats for a given mix of RecipeIngredients.
    """
    return get_engine('SODA').calculate_recipe_stats(recipe_ingredients)