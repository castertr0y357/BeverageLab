"""Base recommendation engine class."""

from typing import List, Dict, Any, Optional, Set, Union
from django.db.models import Avg, QuerySet
from ..models import Ingredient, Recipe, RecipeIngredient

CATEGORY_COMPATIBILITY = {
    'citrus': ['berry', 'tropical', 'herbal', 'sweet'],
    'berry': ['citrus', 'tropical', 'herbal', 'sweet'],
    'tropical': ['citrus', 'berry', 'spice', 'herbal'],
    'herbal': ['citrus', 'berry', 'tropical', 'sour', 'dairy'],
    'spice': ['citrus', 'tropical', 'berry', 'coffee', 'dairy'],
    'sweet': ['citrus', 'berry', 'sour', 'herbal', 'coffee', 'dairy'],
    'sour': ['sweet', 'herbal', 'citrus'],
    'artificial': ['citrus', 'berry', 'sweet', 'tropical'],
    'coffee': ['spice', 'sweet', 'herbal', 'dairy'],
    'dairy': ['coffee', 'sweet', 'spice', 'herbal'],
    'neutral': ['citrus', 'berry', 'tropical', 'herbal', 'spice', 'sweet', 'sour', 'artificial', 'coffee', 'dairy'],
}

FLAVOR_AFFINITY_GROUPS = {
    'zesty': ['citrus', 'spice', 'herbal'],
    'creamy': ['sweet', 'coffee', 'tropical'],
    'earthy': ['herbal', 'coffee', 'spice'],
    'floral': ['berry', 'herbal', 'citrus'],
    'warm': ['spice', 'coffee', 'sweet'],
    'tart': ['citrus', 'berry', 'sour'],
}

KEYWORD_TO_GROUP = {
    'ginger': 'zesty',
    'vanilla': 'creamy',
    'chocolate': 'warm',
    'honey': 'creamy',
    'mint': 'herbal',
    'hibiscus': 'floral',
    'lavender': 'floral',
    'cinnamon': 'warm',
    'lime': 'zesty',
    'lemon': 'zesty',
}

_INTENSITY_ADJECTIVES = {
    (1, 2): ['Gentle', 'Soft', 'Mellow', 'Subtle', 'Light', 'Easy'],
    (3, 3): ['Balanced', 'Classic', 'Smooth', 'Crisp', 'Fresh'],
    (4, 5): ['Bold', 'Vivid', 'Intense', 'Zesty', 'Punchy', 'Vibrant'],
}

_CATEGORY_NOUNS = {
    'citrus': ['Citrus Burst', 'Lemon Twist', 'Citrus Wave', 'Sunrise', 'Grove'],
    'berry': ['Berry Splash', 'Berry Bliss', 'Wild Berry', 'Forest Mix', 'Bramble'],
    'tropical': ['Tropical Dream', 'Island Breeze', 'Paradise', 'Tropicana', 'Lagoon'],
    'herbal': ['Garden Fizz', 'Herb Garden', 'Meadow Mist', 'Cool Breeze', 'Fresh Patch'],
    'spice': ['Spice Road', 'Autumn Spice', 'Warm Blend', 'Kick', 'Zest'],
    'sweet': ['Sweet Cloud', 'Sugar Rush', 'Sweet Harmony', 'Candy Pop', 'Velvet'],
    'sour': ['Sour Power', 'Tart Twist', 'Acid Rain', 'Sharp Edge', 'Tangy Drop'],
    'artificial': ['Fun Fusion', 'Cosmic Pop', 'Neon Fizz', 'Electric Mix', 'Galaxy Sip'],
    'coffee': ['Dark Roast', 'Morning Brew', 'Espresso Shot', 'Bean Blend', 'Roast'],
}

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
    finishers: List[str] = ['Fizz', 'Soda', 'Blend', 'Mix', 'Cooler', 'Splash', 'Delight', 'Special']
    
    # Expose configs for customization in subclasses if needed
    category_compatibility = CATEGORY_COMPATIBILITY
    flavor_affinity_groups = FLAVOR_AFFINITY_GROUPS
    keyword_to_group = KEYWORD_TO_GROUP
    intensity_adjectives = _INTENSITY_ADJECTIVES
    category_nouns = _CATEGORY_NOUNS
    profile_category_rules = _PROFILE_CATEGORY_RULES
    ingredient_category_rules = _INGREDIENT_CATEGORY_RULES

    def generate_recipe_name(self, ingredient_ids: Union[List[int], Set[int]]) -> str:
        """
        Generate a creative, deterministic recipe name from a list of ingredient IDs.
        """
        if not ingredient_ids:
            return "Mystery Mix"

        ingredients = list(Ingredient.objects.filter(id__in=ingredient_ids))
        if not ingredients:
            return "Mystery Mix"

        # Determine dominant category (most common)
        category_counts = {}
        for i in ingredients:
            category_counts[i.category] = category_counts.get(i.category, 0) + 1
        dominant_cat = max(category_counts, key=category_counts.get)

        # Average intensity
        avg_intensity = sum(i.intensity for i in ingredients) / len(ingredients)

        # Pick adjective based on intensity
        adjective = ''
        for (low, high), adjs in self.intensity_adjectives.items():
            if low <= avg_intensity <= high:
                adjective = adjs[len(ingredients) % len(adjs)]
                break

        # Pick noun from dominant category
        nouns = self.category_nouns.get(dominant_cat, ['Blend'])
        noun = nouns[sum(i.id for i in ingredients) % len(nouns)]

        # Optionally attach a finisher for variety
        use_finisher = (sum(i.id for i in ingredients) % 3) == 0
        finisher = self.finishers[len(ingredient_ids) % len(self.finishers)] if use_finisher else ''

        parts = [p for p in [adjective, noun, finisher] if p]
        return ' '.join(parts)

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

    def _rank_and_select_candidates(
        self,
        base_ingredients: List[Ingredient],
        system_candidates: QuerySet,
        experimental: bool = False,
        force_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Rank candidate ingredients based on compatibility with selected base ingredients,
        and select recommendations based on inventory size and compatibility scores.
        """
        if force_type:
            system_candidates = system_candidates.filter(ingredient_type=force_type)

        recommendations = []
        for base_ing in base_ingredients:
            compat_cats = self.category_compatibility.get(base_ing.category, [])
            for cand in system_candidates:
                score_data = self._calculate_compatibility_score(
                    base_ing, cand, experimental=experimental, avg_rating=cand.avg_rating
                )
                score = score_data['score']
                reason = score_data['reason']
                
                if not experimental:
                    if cand.category not in compat_cats and cand.category != base_ing.category:
                        score -= 2
                        
                recommendations.append({
                    'ingredient': cand,
                    'score': score,
                    'reason': reason
                })

        # Deduplicate and sort unique candidates by highest score
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec['ingredient'].id not in seen:
                unique_recommendations.append(rec)
                seen.add(rec['ingredient'].id)

        total_available = len(unique_recommendations)
        limit = min(max(10, total_available), 15)
        return unique_recommendations[:limit]

    def get_recommendation(
        self,
        ingredient_ids: List[int],
        experimental: bool = False,
        force_type: Optional[str] = None,
        exclude_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get ingredient recommendations based on selected ingredients.
        """
        if not ingredient_ids:
            return {
                'recommended': self._get_top_recommendations(experimental, exclude_ids=exclude_ids),
                'recipes': [],
                'suggestions': []
            }
        
        selected_ingredients = Ingredient.objects.filter(id__in=ingredient_ids)
        if not selected_ingredients.exists():
            return self.get_recommendation([], experimental, force_type=force_type, exclude_ids=exclude_ids)
            
        system_candidates = Ingredient.objects.filter(is_in_inventory=True).annotate(
            avg_rating=Avg('ingredient_usage__recipe__rating')
        )
        if not experimental:
            system_candidates = system_candidates.filter(compatible_systems__icontains=self.drink_type)
            
        exclude_pool_ids = set(ingredient_ids)
        if exclude_ids:
            candidate_check = system_candidates.exclude(id__in=exclude_pool_ids)
            filtered_candidates = candidate_check.exclude(id__in=exclude_ids)
            if filtered_candidates.exists():
                exclude_pool_ids.update(exclude_ids)
                system_candidates = filtered_candidates
            else:
                system_candidates = candidate_check
        else:
            system_candidates = system_candidates.exclude(id__in=exclude_pool_ids)
        
        top_recommendations = self._rank_and_select_candidates(
            list(selected_ingredients), system_candidates, experimental=experimental, force_type=force_type
        )
        
        recipe_suggestions = self._find_similar_recipes(selected_ingredients)
        
        return {
            'recommended': top_recommendations,
            'recipes': recipe_suggestions,
            'suggestions': list(selected_ingredients)
        }

    def get_tiered_recommendation(
        self,
        base_id: int,
        secondary_id: Optional[int] = None,
        experimental: bool = False,
        force_type: Optional[str] = None,
        exclude_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get tiered recommendations (Secondary or Tertiary) based on selected base and optional secondary.
        """
        if base_id == 0 or base_id == 'virtual_water':
            base_ingredient = Ingredient(
                id=0,
                name="Water",
                category="neutral",
                ingredient_type="OTHER",
                intensity=1,
                sweetness=0,
                acidity=0,
                bitterness=0,
                complexity=0,
                is_ready_to_drink=True
            )
        else:
            base_ingredient = Ingredient.objects.filter(id=base_id, is_in_inventory=True).first()
            
        if not base_ingredient:
            return {'recommended': []}

        system_candidates = Ingredient.objects.filter(is_in_inventory=True).annotate(
            avg_rating=Avg('ingredient_usage__recipe__rating')
        )
        if not experimental:
            system_candidates = system_candidates.filter(compatible_systems__icontains=self.drink_type)
            
        exclude_pool_ids = {base_id}
        if secondary_id:
            exclude_pool_ids.add(secondary_id)
        if exclude_ids:
            candidate_check = system_candidates.exclude(id__in=exclude_pool_ids)
            filtered_candidates = candidate_check.exclude(id__in=exclude_ids)
            if filtered_candidates.exists():
                exclude_pool_ids.update(exclude_ids)
                system_candidates = filtered_candidates
            else:
                system_candidates = candidate_check
        else:
            system_candidates = system_candidates.exclude(id__in=exclude_pool_ids)
        
        if force_type:
            system_candidates = system_candidates.filter(ingredient_type=force_type)

        recommendations = []
        
        if not secondary_id:
            # Looking for Secondary
            compat_cats = self.category_compatibility.get(base_ingredient.category, [])
            for cand in system_candidates:
                score_data = self._calculate_compatibility_score(
                    base_ingredient, cand, experimental=experimental, avg_rating=cand.avg_rating
                )
                score = score_data['score']
                reason = score_data['reason']
                
                if not experimental:
                    if cand.category not in compat_cats and cand.category != base_ingredient.category:
                        score -= 2
                        
                recommendations.append({
                    'ingredient': cand,
                    'score': score,
                    'tier': 'secondary',
                    'reason': reason
                })
                
            recommendations.sort(key=lambda x: x['score'], reverse=True)
            total_available = len(recommendations)
            limit = min(max(10, total_available), 15)
            top_recommendations = recommendations[:limit]
        else:
            # Looking for Tertiary
            sec_ingredient = Ingredient.objects.filter(id=secondary_id).first()
            if not sec_ingredient:
                return {'recommended': []}
                
            base_compat = set(self.category_compatibility.get(base_ingredient.category, []))
            sec_compat = set(self.category_compatibility.get(sec_ingredient.category, []))
            shared_compat = base_compat.intersection(sec_compat)
            
            for cand in system_candidates:
                res1 = self._calculate_compatibility_score(base_ingredient, cand, experimental=experimental, avg_rating=cand.avg_rating)
                res2 = self._calculate_compatibility_score(sec_ingredient, cand, experimental=experimental, avg_rating=cand.avg_rating)
                profile_score = self._calculate_profile_balance(base_ingredient, sec_ingredient, cand)
                
                score = res1['score'] + res2['score'] + profile_score
                reason = res1['reason'] if res1['score'] >= res2['score'] else res2['reason']
                if experimental and (res1.get('bridge') or res2.get('bridge')):
                    reason = f"Bridges {base_ingredient.name} and {sec_ingredient.name} via {res1.get('bridge') or res2.get('bridge')}"
                
                if not experimental:
                    if cand.category not in shared_compat and cand.category != base_ingredient.category and cand.category != sec_ingredient.category:
                        score -= 4
                        
                recommendations.append({
                    'ingredient': cand,
                    'score': score,
                    'tier': 'tertiary',
                    'reason': reason
                })
                
            recommendations.sort(key=lambda x: x['score'], reverse=True)
            total_available = len(recommendations)
            limit = min(max(10, total_available), 15)
            top_recommendations = recommendations[:limit]
                    
        return {'recommended': top_recommendations}

    def _calculate_compatibility_score(self, i1: Ingredient, i2: Ingredient, experimental: bool = False, avg_rating: Optional[float] = 0) -> Dict[str, Any]:
        """
        Calculate compatibility score between two ingredients.
        Returns a dict with 'score', 'reason', and optional 'bridge'.
        """
        score = 0
        reason = f"Shares {i1.category} notes" if i1.category == i2.category else f"Pairs with {i1.name}"
        bridge = None
        
        avg_rating = avg_rating or 0

        # Category compatibility
        if i1.category == i2.category:
            score -= 1
        if i2.category in self.category_compatibility.get(i1.category, []):
            score += 3
            reason = f"Classic {i1.category} + {i2.category} pairing"

        # Intensity balance
        intensity_diff = abs(i1.intensity - i2.intensity)
        score += (5 - intensity_diff) # Reward similar intensity for harmony

        # Keyword Affinity (The Bridge)
        notes1 = set(n.strip().lower() for n in i1.flavor_notes.split(',') if n.strip())
        notes2 = set(n.strip().lower() for n in i2.flavor_notes.split(',') if n.strip())
        shared_notes = notes1.intersection(notes2)
        
        if shared_notes:
            score += len(shared_notes) * 2
            note = list(shared_notes)[0]
            bridge = note
            reason = f"Synergy via shared {note} notes"
        else:
            # Check bridge groups
            group1 = None
            for k, g in self.keyword_to_group.items():
                if k in notes1 or k in i1.name.lower():
                    group1 = g
                    break
            
            group2 = None
            for k, g in self.keyword_to_group.items():
                if k in notes2 or k in i2.name.lower():
                    group2 = g
                    break
            
            if group1 and group2 and group1 == group2:
                score += 3
                bridge = group1
                reason = f"Thematic bridge: {group1.title()}"

        # Taste-First: Rating Bonus
        if avg_rating >= 4:
            score += 4
        elif avg_rating >= 3:
            score += 2

        # Experimental adjustments
        if experimental:
            if i2.category not in self.category_compatibility.get(i1.category, []):
                # Reward contrast/discovery in experimental mode
                if shared_notes or (group1 and group2 and group1 == group2):
                    score += 5
                    reason = f"Experimental bridge: {bridge or 'Contrast'}"
                else:
                    score += 1 # Base experimental score for novel pairings

        # Favorite Boost: Prioritize preferred reagents
        if i2.favorite:
            score += 8
            reason = f"★ Favorite reagent: {reason}"

        return {'score': score, 'reason': reason, 'bridge': bridge}

    def _calculate_profile_balance(self, i1: Ingredient, i2: Ingredient, cand: Ingredient) -> int:
        """Reward candidates that provide missing profile elements."""
        score = 0
        avg_sweet = (i1.sweetness + i2.sweetness) / 2.0
        avg_acid = (i1.acidity + i2.acidity) / 2.0
        
        if avg_sweet > 3.5 and (cand.acidity >= 3 or cand.bitterness >= 3):
            score += 3
        if avg_acid > 3.5 and cand.sweetness >= 3:
            score += 3
            
        return score

    def _get_top_recommendations(self, experimental: bool = False, exclude_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """Get top recommended base ingredients to start a mix."""
        recommendations = []
        
        # Filter by inventory and type if possible
        query = Ingredient.objects.filter(is_in_inventory=True)
        if not experimental:
            query = query.filter(compatible_systems__icontains=self.drink_type)
            
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

    def _find_similar_recipes(self, selected_ingredients: Union[List[Ingredient], QuerySet]) -> List[Dict[str, Any]]:
        """Find recipes that use the selected ingredients."""
        ingredient_ids = [i.id for i in selected_ingredients]
        matching_recipe_ingredients = RecipeIngredient.objects.filter(ingredient_id__in=ingredient_ids)
        
        recipe_scores = {}
        for ri in matching_recipe_ingredients:
            recipe_id = ri.recipe.id
            recipe_scores[recipe_id] = recipe_scores.get(recipe_id, 0) + 1
        
        sorted_recipes = sorted(recipe_scores.items(), key=lambda x: x[1], reverse=True)
        
        similar_recipes = []
        for recipe_id, matches in sorted_recipes[:5]:
            recipe = Recipe.objects.get(id=recipe_id)
            all_ingredients = recipe.recipe_ingredients.all()
            
            ingredients_data = [{
                'id': ri.ingredient.id,
                'name': ri.ingredient.name,
                'amount': ri.amount,
                'intensity': ri.ingredient.intensity,
                'category': ri.ingredient.category
            } for ri in all_ingredients]
            
            similar_recipes.append({
                'id': recipe.id,
                'name': recipe.name,
                'drink_type': recipe.get_drink_type_display(),
                'description': recipe.description,
                'ingredients': ingredients_data,
                'match_count': matches,
                'updated_at': recipe.updated_at
            })
        
        return similar_recipes
