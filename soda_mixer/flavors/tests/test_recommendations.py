import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from ..models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, MixHistory, MixHistoryIngredient, SystemConfiguration, LLMProvider
from ..recommendations import suggest_categories, calculate_recipe_stats
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

    @patch('soda_mixer.flavors.ai_service.AIAssistant.chat')
    def test_recipe_name_generator(self, mock_chat) -> None:
        mock_chat.return_value = "Citrus Sunrise"
        name = AIAssistant.generate_recipe_name([self.ing1.name], drink_type="SODA")
        self.assertEqual(name, "Citrus Sunrise")
        
        name_empty = AIAssistant.generate_recipe_name([])
        self.assertEqual(name_empty, "Mystery Mix")

    def test_suggest_categories(self) -> None:
        self.ing3.acidity = 2
        self.ing3.save()
        categories = suggest_categories([self.ing1.id, self.ing3.id])
        self.assertIn("Refreshing", categories)

    def test_calculate_recipe_stats(self) -> None:
        recipe = Recipe.objects.create(name="Test Mix")
        ri1 = RecipeIngredient.objects.create(recipe=recipe, ingredient=self.ing1, amount=10.0)
        ri2 = RecipeIngredient.objects.create(recipe=recipe, ingredient=self.ing3, amount=10.0)
        
        stats = calculate_recipe_stats([ri1, ri2])
        self.assertEqual(stats['sweetness'], 3.5)  # (2 + 5) / 2
        self.assertEqual(stats['acidity'], 3.0)  # (5 + 1) / 2


class BeverageLabRecommendationExclusionTest(TestCase):
    """Test case for AI suggestion exclusion logic."""

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

    def test_get_recommendations_api_deprecated(self) -> None:
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
        self.assertEqual(data['recommended'], [])

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
