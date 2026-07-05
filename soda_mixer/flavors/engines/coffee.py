"""Coffee recommendation engine subclass."""

from typing import List, Dict, Any, Optional
from django.db.models import Avg
from .base import BaseEngine
from ..models import Ingredient

class CoffeeEngine(BaseEngine):
    """Engine specific to Coffee Laboratory."""
    
    drink_type: str = 'COFFEE'
    finishers = ['Brew', 'Drip', 'Extraction', 'Press', 'Roast', 'Synergy', 'Laboratory']

    def _get_top_recommendations(self, experimental: bool = False, exclude_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """Get top recommended coffee base ingredients to start a mix."""
        recommendations = []
        
        query = Ingredient.objects.filter(is_in_inventory=True)
        if not experimental:
            # For coffee standard mode, base ingredients must be coffee beans
            query = query.filter(compatible_systems__icontains=self.drink_type, ingredient_type='COFFEE_BEAN')
            
        if exclude_ids:
            filtered_query = query.exclude(id__in=exclude_ids)
            if filtered_query.exists():
                query = filtered_query
            
        # Get a diverse, dynamic set of up to 15 ingredients to serve as bases, prioritizing favorites
        limit = min(max(10, query.count()), 15)
        diverse_bases = query.order_by('-favorite', '?')[:limit]
        
        for ingredient in diverse_bases:
            recommendations.append({
                'ingredient': ingredient,
                'score': 5,
                'reason': "Excellent Base Component"
            })
        
        return recommendations

    def get_recommendation(
        self,
        ingredient_ids: List[int],
        experimental: bool = False,
        force_type: Optional[str] = None,
        exclude_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get recommendations for Coffee, applying the Espresso Synergy bonus (+5) for Coffee Beans.
        """
        result = super().get_recommendation(ingredient_ids, experimental, force_type, exclude_ids)
        
        # Apply Espresso Synergy bonus (+5) if candidate is COFFEE_BEAN
        for rec in result.get('recommended', []):
            if rec['ingredient'].ingredient_type == 'COFFEE_BEAN':
                rec['score'] += 5
                
        # Re-sort recommended list as scores have been modified
        result['recommended'].sort(key=lambda x: x['score'], reverse=True)
        return result

    def get_tiered_recommendation(
        self,
        base_id: int,
        secondary_id: Optional[int] = None,
        experimental: bool = False,
        force_type: Optional[str] = None,
        exclude_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get tiered recommendations for Coffee, applying the Espresso Synergy bonus (+5) for Coffee Beans.
        """
        result = super().get_tiered_recommendation(base_id, secondary_id, experimental, force_type, exclude_ids)
        
        # Apply Espresso Synergy bonus (+5) to secondary recommendations if candidate is COFFEE_BEAN
        if not secondary_id:
            for rec in result.get('recommended', []):
                if rec['ingredient'].ingredient_type == 'COFFEE_BEAN':
                    rec['score'] += 5
            # Re-sort
            result['recommended'].sort(key=lambda x: x['score'], reverse=True)
            
        return result
