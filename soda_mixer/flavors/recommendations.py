"""Recommendation engine facade routing to specific drink engines."""

from typing import List, Dict, Any, Optional, Set, Union
from django.db.models import QuerySet
from .models import Ingredient, RecipeIngredient
from .engines import get_engine

def generate_recipe_name(ingredient_ids: Union[List[int], Set[int]], drink_type: str = 'SODA') -> str:
    """
    Generate a creative, deterministic recipe name from a list of ingredient IDs.
    Delegates to the appropriate drink-type engine.
    """
    return get_engine(drink_type).generate_recipe_name(ingredient_ids)

def suggest_categories(ingredient_ids: Union[List[int], Set[int]]) -> List[str]:
    """
    Return a list of suggested category name strings based on the ingredients chosen.
    """
    return get_engine('SODA').suggest_categories(ingredient_ids)

def get_recommendation(
    ingredient_ids: List[int],
    drink_type: str = 'SODA',
    experimental: bool = False,
    force_type: Optional[str] = None,
    exclude_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Get ingredient recommendations based on selected ingredients.
    Delegates to the appropriate drink-type engine.
    """
    return get_engine(drink_type).get_recommendation(
        ingredient_ids=ingredient_ids,
        experimental=experimental,
        force_type=force_type,
        exclude_ids=exclude_ids
    )

def get_tiered_recommendation(
    base_id: int,
    secondary_id: Optional[int] = None,
    drink_type: str = 'SODA',
    experimental: bool = False,
    force_type: Optional[str] = None,
    exclude_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Get tiered recommendations (Secondary or Tertiary) based on selected base and optional secondary.
    Delegates to the appropriate drink-type engine.
    """
    return get_engine(drink_type).get_tiered_recommendation(
        base_id=base_id,
        secondary_id=secondary_id,
        experimental=experimental,
        force_type=force_type,
        exclude_ids=exclude_ids
    )

def calculate_recipe_stats(recipe_ingredients: Union[List[RecipeIngredient], QuerySet]) -> Dict[str, float]:
    """
    Calculate weighted stats for a given mix of RecipeIngredients.
    """
    return get_engine('SODA').calculate_recipe_stats(recipe_ingredients)