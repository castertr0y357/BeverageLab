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

class BaseChemistryEngine:
    """Base chemistry engine that provides common utilities for processing ingredients."""
    def __init__(self, ingredients_input: List[Dict[str, Any]]):
        self.ingredients_input = ingredients_input
        self.modifiers = []
        self.bases = []
        self.fillers = []

    def parse_ingredients(self):
        """Pre-process ingredients if needed."""
        pass

    def partition_roles(self):
        """Partition ingredients into roles."""
        pass

    def calculate_metrics(self, output_items: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate weighted average sweetness, acidity, and bitterness scores."""
        total_weights = 0.0
        weighted_sweetness = 0.0
        weighted_acidity = 0.0
        weighted_bitterness = 0.0
        
        for item in output_items:
            vol = item.get('volume_ml', item.get('volume_oz', 0.0))
            if vol <= 0.0:
                continue
                
            orig = next((i for i in self.ingredients_input if i.get('id') == item.get('id')), None)
            if not orig and item.get('id') == 'virtual_water':
                orig = {'sweetness': 1, 'acidity': 1, 'bitterness': 1}
                
            if orig:
                sweet = float(orig.get('sweetness_score', orig.get('sweetness', 3.0)))
                acid = float(orig.get('acidity_score', orig.get('acidity', 2.0)))
                bitter = float(orig.get('bitterness_score', orig.get('bitterness', 1.0)))
                
                weighted_sweetness += sweet * vol
                weighted_acidity += acid * vol
                weighted_bitterness += bitter * vol
                total_weights += vol
                
        if total_weights > 0.0:
            return {
                'sweetness': round(weighted_sweetness / total_weights, 2),
                'acidity': round(weighted_acidity / total_weights, 2),
                'bitterness': round(weighted_bitterness / total_weights, 2)
            }
        else:
            return {
                'sweetness': 3.0,
                'acidity': 2.0,
                'bitterness': 1.0
            }

    def process(self) -> Dict[str, Any]:
        """Main method to be overridden by subclasses."""
        raise NotImplementedError
