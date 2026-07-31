import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from ..models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, MixHistory, MixHistoryIngredient, SystemConfiguration, LLMProvider
from ..recommendations import generate_recipe_name, suggest_categories, get_recommendation, get_tiered_recommendation, calculate_recipe_stats
from ..ai_service import AIAssistant

User = get_user_model()

def _get_sse_data(response) -> dict:
    content = b"".join(response.streaming_content).decode('utf-8')
    for chunk in content.split('\n\n'):
        for line in chunk.split('\n'):
            if line.strip().startswith('data:'):
                data_str = line.replace('data:', '').strip()
                if not data_str: continue
                try:
                    parsed = json.loads(data_str)
                    if parsed.get('status') == 'success':
                        return parsed
                except ValueError:
                    pass
    return {}

class BeverageLabRecommendationTest(TestCase):
    """Test case for the recommendation engine logic."""

    def setUp(self) -> None:
        self.ing1 = Ingredient.objects.create(
            name="Lemon Syrup", category="citrus", intensity=3, sweetness=2, acidity=5, bitterness=1, complexity=2
        )
        self.ing2 = Ingredient.objects.create(
            name="Espresso", category="coffee", intensity=5, sweetness=1, acidity=3, bitterness=4, complexity=4
        )
        self.ing3 = Ingredient.objects.create(
            name="Vanilla Syrup", category="sweet", intensity=2, sweetness=5, acidity=1, bitterness=1, complexity=2
        )

    def test_recipe_name_generator(self) -> None:
        name = generate_recipe_name([self.ing1.id], drink_type="SODA")
        self.assertTrue(any(word in name for word in ["Lemon", "Citrus", "Splash", "Grove", "Sunrise"]))
        
        name_empty = generate_recipe_name([])
        self.assertEqual(name_empty, "Mystery Mix")

    def test_suggest_categories(self) -> None:
        self.ing3.acidity = 2
        self.ing3.save()
        categories = suggest_categories([self.ing1.id, self.ing3.id])
        self.assertIn("Refreshing", categories)

    def test_get_recommendation_empty(self) -> None:
        recs = get_recommendation([], drink_type="SODA")
        self.assertIn("recommended", recs)

    def test_get_recommendation_single(self) -> None:
        recs = get_recommendation([self.ing1.id], drink_type="SODA")
        self.assertIn("recommended", recs)

    def test_get_tiered_recommendation_secondary(self) -> None:
        recs = get_tiered_recommendation(self.ing1.id)
        self.assertIn("recommended", recs)

    def test_get_tiered_recommendation_tertiary(self) -> None:
        recs = get_tiered_recommendation(self.ing1.id, self.ing3.id)
        self.assertIn("recommended", recs)

    def test_get_tiered_recommendation_virtual_water(self) -> None:
        # Base ID = 0 represents virtual water
        recs = get_tiered_recommendation(0)
        self.assertIn("recommended", recs)
        self.assertTrue(len(recs["recommended"]) > 0)
        
        # Test tertiary recommendation with virtual water base
        recs_tertiary = get_tiered_recommendation(0, self.ing3.id)
        self.assertIn("recommended", recs_tertiary)

    def test_calculate_recipe_stats(self) -> None:
        recipe = Recipe.objects.create(name="Test Mix")
        ri1 = RecipeIngredient.objects.create(recipe=recipe, ingredient=self.ing1, amount=10.0)
        ri2 = RecipeIngredient.objects.create(recipe=recipe, ingredient=self.ing3, amount=10.0)
        
        stats = calculate_recipe_stats([ri1, ri2])
        self.assertEqual(stats['sweetness'], 3.5)  # (2 + 5) / 2
        self.assertEqual(stats['acidity'], 3.0)  # (5 + 1) / 2

    def test_get_recommendation_limit_increased_to_10(self) -> None:
        # Create 12 more ingredients to ensure we have enough compatibility options.
        # Make them compatible with SODA.
        ingredients = []
        for i in range(12):
            ing = Ingredient.objects.create(
                name=f"Soda Modifier {i}",
                category="sweet",
                ingredient_type="ADDITIVE",
                intensity=2,
                sweetness=3,
                acidity=1,
                bitterness=1,
                complexity=2,
                is_in_inventory=True,
                compatible_systems="SODA"
            )
            ingredients.append(ing)

        # get_recommendation using self.ing1 (Lemon Syrup, category="citrus", compatible with sweet category additives)
        recs = get_recommendation([self.ing1.id], drink_type="SODA")
        self.assertEqual(len(recs["recommended"]), 15)

        # get_tiered_recommendation should also return up to 15
        tiered_recs = get_tiered_recommendation(self.ing1.id, drink_type="SODA")
        self.assertEqual(len(tiered_recs["recommended"]), 15)

    def test_favorite_ingredient_score_boost_and_prioritization(self) -> None:
        """Verify that marking an ingredient as favorite boosts its score and ranks it at the top."""
        # Create a non-favorite ingredient
        normal_ing = Ingredient.objects.create(
            name="Normal Syrup",
            category="sweet",
            ingredient_type="ADDITIVE",
            intensity=3,
            sweetness=3,
            acidity=2,
            bitterness=1,
            complexity=2,
            is_in_inventory=True,
            compatible_systems="SODA"
        )
        # Create a favorite ingredient with the exact same profile
        favorite_ing = Ingredient.objects.create(
            name="Favorite Syrup",
            category="sweet",
            ingredient_type="ADDITIVE",
            intensity=3,
            sweetness=3,
            acidity=2,
            bitterness=1,
            complexity=2,
            is_in_inventory=True,
            favorite=True,
            compatible_systems="SODA"
        )
        
        # Get standard recommendations starting with Lemon Syrup (self.ing1)
        recs = get_recommendation([self.ing1.id], drink_type="SODA")
        recommended_list = recs["recommended"]
        
        # Find normal and favorite syrup in recommendations
        normal_rec = next(r for r in recommended_list if r["ingredient"].id == normal_ing.id)
        fav_rec = next(r for r in recommended_list if r["ingredient"].id == favorite_ing.id)
        
        # The favorite ingredient should have a score boost (+8) compared to the normal one
        self.assertEqual(fav_rec["score"] - normal_rec["score"], 8)
        
        # Favorite should rank higher/earlier in the list than normal ingredient
        fav_idx = recommended_list.index(fav_rec)
        normal_idx = recommended_list.index(normal_rec)
        self.assertLess(fav_idx, normal_idx)

    def test_multi_ingredient_compatibility(self) -> None:
        """Verify that recommendations evaluate compatibility against all active ingredients."""
        Ingredient.objects.all().update(is_in_inventory=False)
        comp_both = Ingredient.objects.create(
            name="Vanilla Extract",
            category="sweet",
            ingredient_type="ADDITIVE",
            intensity=2,
            sweetness=4,
            acidity=1,
            bitterness=1,
            complexity=2,
            is_in_inventory=True,
            compatible_systems="SODA,COFFEE"
        )
        comp_one = Ingredient.objects.create(
            name="Dark Cocoa",
            category="coffee",
            ingredient_type="ADDITIVE",
            intensity=4,
            sweetness=1,
            acidity=2,
            bitterness=4,
            complexity=3,
            is_in_inventory=True,
            compatible_systems="SODA,COFFEE"
        )
        
        recs = get_recommendation([self.ing1.id, self.ing2.id], drink_type="SODA")
        recommended_list = recs["recommended"]
        
        vanilla_rec = next(r for r in recommended_list if r["ingredient"].id == comp_both.id)
        cocoa_rec = next(r for r in recommended_list if r["ingredient"].id == comp_one.id)
        
        self.assertGreater(vanilla_rec["score"], cocoa_rec["score"])

class BeverageLabRecommendationExclusionTest(TestCase):
    """Test case for recommendation exclusion and fallback logic."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.client.login(username="lab_tech", password="secure_password_123")
        
        # Deactivate all other ingredients from active inventory for deterministic testing
        Ingredient.objects.all().update(is_in_inventory=False)
        
        # Create some ingredients of same system (SODA) and category to ensure compatibility
        self.ing1 = Ingredient.objects.create(
            name="Soda Base Cola",
            ingredient_type="SODA_SYRUP",
            category="citrus",
            intensity=3,
            sweetness=4,
            acidity=2,
            bitterness=1,
            complexity=2,
            is_in_inventory=True,
            compatible_systems="SODA"
        )
        self.ing2 = Ingredient.objects.create(
            name="Vanilla Twist",
            ingredient_type="SODA_SYRUP",
            category="sweet",
            intensity=2,
            sweetness=5,
            acidity=1,
            bitterness=1,
            complexity=2,
            is_in_inventory=True,
            compatible_systems="SODA"
        )
        self.ing3 = Ingredient.objects.create(
            name="Cherry Blast",
            ingredient_type="SODA_SYRUP",
            category="sweet",
            intensity=3,
            sweetness=4,
            acidity=3,
            bitterness=1,
            complexity=3,
            is_in_inventory=True,
            compatible_systems="SODA"
        )

    def test_algorithmic_exclusion(self) -> None:
        # Without exclusions, recommendations should contain both ing2 and ing3
        res = get_recommendation([self.ing1.id], drink_type="SODA")
        recommended_ids = [r['ingredient'].id for r in res['recommended']]
        self.assertIn(self.ing2.id, recommended_ids)
        self.assertIn(self.ing3.id, recommended_ids)

        # With exclusion of ing2, it should only recommend ing3
        res = get_recommendation([self.ing1.id], drink_type="SODA", exclude_ids=[self.ing2.id])
        recommended_ids = [r['ingredient'].id for r in res['recommended']]
        self.assertNotIn(self.ing2.id, recommended_ids)
        self.assertIn(self.ing3.id, recommended_ids)

    def test_algorithmic_exclusion_fallback(self) -> None:
        # If all candidates (ing2 and ing3) are excluded, it should fall back to recommend all candidates
        res = get_recommendation([self.ing1.id], drink_type="SODA", exclude_ids=[self.ing2.id, self.ing3.id])
        recommended_ids = [r['ingredient'].id for r in res['recommended']]
        # Because of fallback, both ingredients should be returned
        self.assertIn(self.ing2.id, recommended_ids)
        self.assertIn(self.ing3.id, recommended_ids)

    def test_tiered_exclusion_secondary(self) -> None:
        res = get_tiered_recommendation(self.ing1.id, drink_type="SODA", exclude_ids=[self.ing2.id])
        recommended_ids = [r['ingredient'].id for r in res['recommended']]
        self.assertNotIn(self.ing2.id, recommended_ids)
        self.assertIn(self.ing3.id, recommended_ids)

    def test_tiered_exclusion_secondary_fallback(self) -> None:
        # Exclude everything, it should fallback and recommend everything
        res = get_tiered_recommendation(self.ing1.id, drink_type="SODA", exclude_ids=[self.ing2.id, self.ing3.id])
        recommended_ids = [r['ingredient'].id for r in res['recommended']]
        self.assertIn(self.ing2.id, recommended_ids)
        self.assertIn(self.ing3.id, recommended_ids)

    def test_get_recommendations_api_exclusion(self) -> None:
        response = self.client.post(
            reverse('get_recommendations_api'),
            data=json.dumps({
                'ingredient_ids': [self.ing1.id],
                'drink_type': 'SODA',
                'exclude_ids': [self.ing2.id]
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        recommended_ids = [r['id'] for r in data['recommended']]
        self.assertNotIn(self.ing2.id, recommended_ids)
        self.assertIn(self.ing3.id, recommended_ids)

    def test_algorithmic_recommendation_scaling_rules(self) -> None:
        # Clear inventory and create a specific number of SODA ingredients to test scaling
        Ingredient.objects.all().update(is_in_inventory=False)
        
        base_ing = Ingredient.objects.create(
            name="Soda Base Cola Temp",
            category="cola",
            ingredient_type="BASE",
            intensity=3,
            sweetness=3,
            acidity=3,
            bitterness=2,
            complexity=3,
            is_ready_to_drink=True,
            is_in_inventory=True,
            compatible_systems="SODA"
        )
        
        # Scenario A: Less than 10 available candidates. All of them should be recommended.
        for i in range(6):
            Ingredient.objects.create(
                name=f"Soda Ext Temp {i}",
                category="sweet",
                ingredient_type="ADDITIVE",
                intensity=2,
                sweetness=4,
                acidity=1,
                bitterness=1,
                complexity=2,
                is_ready_to_drink=True,
                is_in_inventory=True,
                compatible_systems="SODA"
            )
            
        res = get_tiered_recommendation(base_ing.id, drink_type="SODA")
        recommended_ids = [r['ingredient'].id for r in res['recommended']]
        self.assertEqual(len(recommended_ids), 6) # Recommend all 6
        
        # Scenario B: 10 or more available candidates.
        # Add 6 more to make total 12 candidates (excluding base)
        for i in range(6, 12):
            Ingredient.objects.create(
                name=f"Soda Ext Temp {i}",
                category="sweet",
                ingredient_type="ADDITIVE",
                intensity=2,
                sweetness=4,
                acidity=1,
                bitterness=1,
                complexity=2,
                is_ready_to_drink=True,
                is_in_inventory=True,
                compatible_systems="SODA"
            )
            
        res2 = get_tiered_recommendation(base_ing.id, drink_type="SODA")
        recommended_ids2 = [r['ingredient'].id for r in res2['recommended']]
        # Total candidates is 12 (>= 10 and <= 15), so it should recommend exactly 12
        self.assertEqual(len(recommended_ids2), 12)

        # Scenario C: More than 15 candidates.
        # Add 6 more to make total 18 candidates (excluding base)
        for i in range(12, 18):
            Ingredient.objects.create(
                name=f"Soda Ext Temp {i}",
                category="sweet",
                ingredient_type="ADDITIVE",
                intensity=2,
                sweetness=4,
                acidity=1,
                bitterness=1,
                complexity=2,
                is_ready_to_drink=True,
                is_in_inventory=True,
                compatible_systems="SODA"
            )
        res3 = get_tiered_recommendation(base_ing.id, drink_type="SODA")
        recommended_ids3 = [r['ingredient'].id for r in res3['recommended']]
        # Total candidates is 18 (> 15), so it should cap at exactly 15
        self.assertEqual(len(recommended_ids3), 15)

    @patch('requests.post')
    def test_ai_suggest_api_exclusion_and_fallback(self, mock_request: MagicMock) -> None:
        # Set up default LLM provider
        provider = LLMProvider.objects.create(
            name="Mock OpenAI",
            provider_type="OPENAI",
            api_key="mock-key-123",
            default_model="gpt-3.5-turbo",
            is_enabled=True
        )
        config = SystemConfiguration.get_config()
        config.default_llm_provider = provider
        config.save()

        # 1. Normal exclusion request
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "{\\\"suggestions\\\": [{\\\"name\\\": \\\"Cherry Blast\\\", \\\"reason\\\": \\\"Adds flavor\\\", \\\"resonance\\\": 95, \\\"amount\\\": 100.0}], \\\"rebalancing\\\": {}, \\\"seal_recommended\\\": false, \\\"seal_resonance\\\": 0, \\\"reasoning\\\": \\\"Test reason\\\"}"}}]}',
            b'data: [DONE]'
        ]
        mock_request.return_value = mock_response

        # We exclude Vanilla Twist
        response = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': [self.ing1.name],
                'drink_type': 'SODA',
                'exclude': [self.ing2.name]
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = _get_sse_data(response)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['suggestions'][0]['name'], 'Cherry Blast')
        
        # Verify call to AI service has the excluded ingredient in the request context/instructions
        args, kwargs = mock_request.call_args
        user_msg = kwargs['json']['messages'][1]['content']
        self.assertIn("Exclude these previously suggested items: Vanilla Twist", user_msg)

        # 2. Exclude all candidates: Cherry Blast and Vanilla Twist
        # It should fall back, meaning Vanilla Twist and Cherry Blast are still in the context.
        mock_response_fallback = MagicMock()
        mock_response_fallback.status_code = 200
        mock_response_fallback.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "{\\\"suggestions\\\": [{\\\"name\\\": \\\"Vanilla Twist\\\", \\\"reason\\\": \\\"Adds flavor\\\", \\\"resonance\\\": 95, \\\"amount\\\": 100.0}], \\\"rebalancing\\\": {}, \\\"seal_recommended\\\": false, \\\"seal_resonance\\\": 0, \\\"reasoning\\\": \\\"Test reason\\\"}"}}]}',
            b'data: [DONE]'
        ]
        mock_request.return_value = mock_response_fallback

        response_fallback = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': [self.ing1.name],
                'drink_type': 'SODA',
                'exclude': [self.ing2.name, self.ing3.name]
            }),
            content_type="application/json"
        )
        self.assertEqual(response_fallback.status_code, 200)
        data_fallback = _get_sse_data(response_fallback)
        self.assertEqual(data_fallback['status'], 'success')
        self.assertEqual(data_fallback['suggestions'][0]['name'], 'Vanilla Twist')

    @patch('soda_mixer.flavors.ai_service.AIAssistant.suggest_autonomous_stream')
    def test_ai_suggest_api_fallback_to_algorithmic(self, mock_suggest_stream: MagicMock) -> None:
        # Mock suggest_autonomous_stream to return empty list/string representing empty AI response
        mock_suggest_stream.return_value = []

        
        response = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': [self.ing1.name],
                'drink_type': 'SODA',
                'exclude': []
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = _get_sse_data(response)
        
        # Verify it fell back and returned algorithmic recommendations (Vanilla Twist and Cherry Blast)
        self.assertEqual(data['status'], 'success')
        self.assertTrue(len(data['suggestions']) >= 1)
        suggested_names = [s['name'] for s in data['suggestions']]
        self.assertIn("Vanilla Twist", suggested_names)
        self.assertIn("Cherry Blast", suggested_names)

