"""Base recommendation engine class."""

from typing import List, Dict, Any, Optional, Set, Union
from django.db.models import Avg, QuerySet
from ..models import Ingredient, Recipe, RecipeIngredient

_PROFILE_CATEGORY_RULES = [
    (lambda stats: stats['sweetness'] > 3.5 and stats['acidity'] < 3, 'Sweet'),
    (lambda stats: stats['acidity'] > 3.5 and stats['sweetness'] < 3.5, 'Sour & Tangy'),
    (lambda stats: stats['acidity'] > 3 and stats['sweetness'] > 3, 'Refreshing'),
    (lambda stats: stats['bitterness'] > 3, 'Bold'),
    (lambda stats: stats['sweetness'] <= 2 and stats['acidity'] <= 2, 'Mellow'),
]

_INGREDIENT_CATEGORY_RULES = {
    'herbal': 'Refreshing',
    'tropical': 'Summer',
    'spice': 'Autumn',
    'citrus': 'Citrus Lover',
    'berry': 'Berry Life',
    'sweet': 'Sweet Tooth',
    'sour': 'Sour & Tangy',
    'coffee': 'Caffeine Lab',
}


class BaseEngine:
    """Base class for all recommendation and configuration engines."""
    
    drink_type: str = 'SODA'
    
    # Expose configs for customization in subclasses if needed
    profile_category_rules = _PROFILE_CATEGORY_RULES
    ingredient_category_rules = _INGREDIENT_CATEGORY_RULES

    def suggest_categories(self, ingredient_ids: Union[List[int], Set[int]]) -> List[str]:
        """
        Return a list of suggested category name strings based on the ingredients chosen.
        """
        ingredients = list(Ingredient.objects.filter(id__in=ingredient_ids))
        if not ingredients:
            return []

        count = len(ingredients)
        stats = {
            'sweetness': sum(i.sweetness for i in ingredients) / count,
            'acidity': sum(i.acidity for i in ingredients) / count,
            'bitterness': sum(i.bitterness for i in ingredients) / count,
        }

        suggestions = set()

        # Profile-based rules
        for rule_fn, cat_name in self.profile_category_rules:
            try:
                if rule_fn(stats):
                    suggestions.add(cat_name)
            except Exception:
                pass

        # Ingredient-category based rules
        for i in ingredients:
            if i.category in self.ingredient_category_rules:
                suggestions.add(self.ingredient_category_rules[i.category])

        return sorted(suggestions)

    def calculate_recipe_stats(self, recipe_ingredients: Union[List[RecipeIngredient], QuerySet]) -> Dict[str, float]:
        """
        Calculate weighted stats for a given mix of RecipeIngredients.
        """
        total_vol = sum(ri.amount for ri in recipe_ingredients)
        if total_vol == 0:
            return {'sweetness': 0, 'acidity': 0, 'bitterness': 0}
            
        sweet = sum(ri.ingredient.sweetness * ri.amount for ri in recipe_ingredients) / total_vol
        acid = sum(ri.ingredient.acidity * ri.amount for ri in recipe_ingredients) / total_vol
        bitter = sum(ri.ingredient.bitterness * ri.amount for ri in recipe_ingredients) / total_vol
        
        return {
            'sweetness': round(sweet, 1),
            'acidity': round(acid, 1),
            'bitterness': round(bitter, 1)
        }
