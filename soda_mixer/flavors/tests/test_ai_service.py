import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

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

class BeverageLabAIAssistantTest(TestCase):
    """Test case for the AIAssistant integrations via Mocking."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.provider = LLMProvider.objects.create(
            name="Mock OpenAI",
            provider_type="OPENAI",
            api_key="mock-key-123",
            default_model="gpt-3.5-turbo",
            is_enabled=True
        )
        self.config = SystemConfiguration.get_config()
        self.config.default_llm_provider = self.provider
        self.config.save()

    @patch('requests.request')
    def test_ai_status_check(self, mock_request: MagicMock) -> None:
        # Mock requests for model discovery list
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt-3.5-turbo"}]}
        mock_request.return_value = mock_response

        status = AIAssistant.check_status()
        self.assertEqual(status, 'synchronized')

    @patch('requests.request')
    def test_ai_chat(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Molecular compound balanced."}}]
        }
        mock_request.return_value = mock_response

        response = AIAssistant.chat("Create a soda mix suggestion")
        self.assertEqual(response, "Molecular compound balanced.")

    @patch('requests.request')
    def test_ai_suggest_autonomous(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Lime", "reason": "tartness", "amount": 20.0}], "rebalancing": {}, "seal_recommended": false, "reasoning": "Test reason"}'}}]
        }
        mock_request.return_value = mock_response

        res = AIAssistant.suggest_autonomous(["Club Soda"], mode="standard")
        self.assertIsNotNone(res)
        self.assertEqual(res['suggestions'][0]['name'], "Lime")

    @patch('requests.request')
    def test_ai_suggest_autonomous_coffee(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Espresso Bean", "reason": "strong base", "amount": 18.0}]}'}}]
        }
        mock_request.return_value = mock_response

        res = AIAssistant.suggest_autonomous(["Whole Milk"], mode="standard", drink_type="COFFEE")
        self.assertIsNotNone(res)
        self.assertEqual(res['suggestions'][0]['name'], "Espresso Bean")
        self.assertEqual(res['suggestions'][0]['amount'], 18.0)

    @patch.dict('os.environ', {'MOCK_MODE': 'True'})
    def test_ai_suggest_autonomous_mock_coffee(self) -> None:
        res = AIAssistant.suggest_autonomous(["Sumatra Mandheling"], mode="standard", drink_type="COFFEE")
        self.assertIsNotNone(res)
        self.assertEqual(res['suggestions'][0]['name'], "Vanilla")
        self.assertEqual(res['suggestions'][0]['amount'], 15.0)
        self.assertEqual(res['rebalancing']['Sumatra Mandheling'], 18.0)

    @patch('requests.request')
    def test_ai_suggest_autonomous_force_type(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Whole Milk", "reason": "creamy", "amount": 50.0}]}'}}]
        }
        mock_request.return_value = mock_response

        res = AIAssistant.suggest_autonomous(["Espresso Beans"], mode="standard", drink_type="COFFEE", force_type="ADDITIVE")
        self.assertIsNotNone(res)
        self.assertEqual(res['suggestions'][0]['name'], "Whole Milk")
        
        args, kwargs = mock_request.call_args
        self.assertIn("MANDATORY RULE: You must ONLY suggest new ingredients of type 'ADDITIVE'", kwargs['json']['messages'][1]['content'])

    @patch('requests.request')
    def test_ai_analyze_flavor_profile(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"intensity": 4.0, "sweetness": 2.0, "acidity": 5.0, "bitterness": 1.0, "complexity": 3.0, "base_suitability": 4.5, "accent_suitability": 1.5}'}}]
        }
        mock_request.return_value = mock_response

        res = AIAssistant.analyze_flavor_profile("Sour Lemon", "Very sour")
        self.assertIsNotNone(res)
        self.assertEqual(res['base_suitability'], 4.5)
        self.assertEqual(res['accent_suitability'], 1.5)

    @patch('requests.request')
    def test_ollama_thinking_parameter_true(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "Molecular compound balanced."}}
        mock_request.return_value = mock_response

        # Setup Ollama provider with think enabled (default is True)
        provider = LLMProvider.objects.create(
            name="Mock Ollama",
            provider_type="OLLAMA",
            base_url="http://localhost:11434",
            default_model="gemma4:12b",
            is_enabled=True,
            enable_thinking=True
        )

        response = AIAssistant.chat("Create a soda mix suggestion", provider=provider)
        self.assertEqual(response, "Molecular compound balanced.")
        
        # Verify request payload contains think: True
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs['json']['think'], True)

    @patch('requests.request')
    def test_ollama_thinking_parameter_false(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "Molecular compound balanced."}}
        mock_request.return_value = mock_response

        # Setup Ollama provider with think disabled
        provider = LLMProvider.objects.create(
            name="Mock Ollama",
            provider_type="OLLAMA",
            base_url="http://localhost:11434",
            default_model="gemma4:12b",
            is_enabled=True,
            enable_thinking=False
        )

        response = AIAssistant.chat("Create a soda mix suggestion", provider=provider)
        self.assertEqual(response, "Molecular compound balanced.")
        
        # Verify request payload contains think: False
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs['json']['think'], False)

    @patch('requests.request')
    def test_ollama_thinking_effort_gpt_oss(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "Molecular compound balanced."}}
        mock_request.return_value = mock_response

        # Setup Ollama provider with gpt-oss model and think enabled
        provider = LLMProvider.objects.create(
            name="Mock Ollama GPT-OSS",
            provider_type="OLLAMA",
            base_url="http://localhost:11434",
            default_model="gpt-oss:8b",
            is_enabled=True,
            enable_thinking=True,
            thinking_effort="low"
        )

        response = AIAssistant.chat("Create a soda mix suggestion", provider=provider)
        self.assertEqual(response, "Molecular compound balanced.")
        
        # Verify request payload contains think: "low"
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs['json']['think'], "low")

    @patch('requests.request')
    def test_openai_reasoning_effort_o3_mini(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Molecular compound balanced."}}]
        }
        mock_request.return_value = mock_response

        # Setup OpenAI provider with o3-mini model
        provider = LLMProvider.objects.create(
            name="Mock OpenAI Reasoner",
            provider_type="OPENAI",
            api_key="mock-key",
            default_model="o3-mini",
            is_enabled=True,
            enable_thinking=True,
            thinking_effort="high"
        )

        response = AIAssistant.chat("Create a soda mix suggestion", provider=provider)
        self.assertEqual(response, "Molecular compound balanced.")
        
        # Verify request payload contains reasoning_effort: "high"
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs['json']['reasoning_effort'], "high")

class BeverageLabAIProfileCompatibilityTest(TestCase):
    """Test case for AI single-ingredient/bulk suggestion profile populate and compatibility filters."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.staff_user = User.objects.create_user(username="director", password="secure_password_123", is_staff=True)
        self.client.login(username="lab_tech", password="secure_password_123")
        
        # Configure LLM provider
        self.provider = LLMProvider.objects.create(
            name="Mock OpenAI",
            provider_type="OPENAI",
            api_key="mock-key-123",
            default_model="gpt-3.5-turbo",
            is_enabled=True
        )
        self.config = SystemConfiguration.get_config()
        self.config.default_llm_provider = self.provider
        self.config.save()

        # Create test ingredients
        self.ing_soda = Ingredient.objects.create(
            name="Soda Syrup Cola",
            ingredient_type="SODA_SYRUP",
            category="sweet",
            is_in_inventory=True,
            compatible_systems="SODA"
        )
        self.ing_coffee = Ingredient.objects.create(
            name="Coffee Bean Kenya",
            ingredient_type="COFFEE_BEAN",
            category="coffee",
            is_in_inventory=True,
            compatible_systems="COFFEE"
        )
        self.ing_slushie = Ingredient.objects.create(
            name="Slushie Syrup Blue Raspberry",
            ingredient_type="SODA_SYRUP",
            category="berry",
            is_in_inventory=True,
            compatible_systems="SLUSHIE"
        )

    @patch('requests.request')
    def test_single_ingredient_analysis_returns_compatibility(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"intensity": 4.0, "sweetness": 3.0, "acidity": 2.0, "bitterness": 1.0, "complexity": 3.0, "base_suitability": 4.0, "accent_suitability": 2.0, "category": "citrus", "ingredient_type": "SODA_SYRUP", "compatible_systems": "SODA,SLUSHIE", "ai_notes": "Bright citrus flavor"}'
                }
            }]
        }
        mock_request.return_value = mock_response

        response = self.client.post(
            reverse('ai_analyze_ingredient_api'),
            data=json.dumps({'name': 'Citrus Splash', 'description': 'Zesty citrus'}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['profile']['category'], 'citrus')
        self.assertEqual(data['profile']['ingredient_type'], 'SODA_SYRUP')
        self.assertEqual(data['profile']['compatible_systems'], 'SODA,SLUSHIE')

    @patch('requests.request')
    def test_bulk_analyze_saves_compatibility_type_category(self, mock_request: MagicMock) -> None:
        self.client.login(username="director", password="secure_password_123")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '[{"name": "Soda Syrup Cola", "intensity": 4, "sweetness": 4, "acidity": 2, "bitterness": 1, "complexity": 3, "base_suitability": 4.0, "accent_suitability": 2.0, "category": "sweet", "ingredient_type": "SODA_SYRUP", "compatible_systems": "SODA,SLUSHIE", "ai_notes": "Classic cola taste"}]'
                }
            }]
        }
        mock_request.return_value = mock_response

        # Verify initial values
        self.assertEqual(self.ing_soda.compatible_systems, "SODA")
        
        response = self.client.post(reverse('ai_bulk_analyze_api'))
        self.assertEqual(response.status_code, 202)
        
        from ..views.ai import ai_bulk_analyze_task
        ai_bulk_analyze_task(update_progress=lambda *args, **kwargs: None)
        
        self.ing_soda.refresh_from_db()
        self.assertEqual(self.ing_soda.category, "sweet")
        self.assertEqual(self.ing_soda.ingredient_type, "SODA_SYRUP")
        self.assertEqual(self.ing_soda.compatible_systems, "SODA,SLUSHIE")



    def test_ready_to_drink_attributes_and_recipe_property(self) -> None:
        """Verify is_ready_to_drink field on Ingredient and has_ready_to_drink property on Recipe."""
        ing_rtd = Ingredient.objects.create(
            name="Apple Juice",
            ingredient_type="OTHER",
            category="sweet",
            is_ready_to_drink=True,
            is_in_inventory=True
        )
        ing_not_rtd = Ingredient.objects.create(
            name="Toasted Marshmallow Syrup",
            ingredient_type="ADDITIVE",
            category="sweet",
            is_ready_to_drink=False,
            is_in_inventory=True
        )
        
        recipe = Recipe.objects.create(
            name="Slushie test recipe",
            drink_type="SLUSHIE",
            drink_size_oz=16.0
        )
        RecipeIngredient.objects.create(recipe=recipe, ingredient=ing_not_rtd, amount=20.0)
        
        # Initially, recipe should not have ready-to-drink ingredients
        self.assertFalse(recipe.has_ready_to_drink)
        
        # Add ready-to-drink ingredient
        RecipeIngredient.objects.create(recipe=recipe, ingredient=ing_rtd, amount=100.0)
        
        # Recipe should now have ready-to-drink ingredient
        self.assertTrue(recipe.has_ready_to_drink)

    @patch('requests.request')
    def test_bulk_analyze_saves_is_ready_to_drink(self, mock_request: MagicMock) -> None:
        """Verify that bulk AI analysis updates the is_ready_to_drink attribute."""
        self.client.login(username="director", password="secure_password_123")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '[{"name": "Apple Juice", "intensity": 3, "sweetness": 4, "acidity": 2, "bitterness": 1, "complexity": 2, "base_suitability": 4.5, "accent_suitability": 1.5, "category": "sweet", "ingredient_type": "OTHER", "is_ready_to_drink": true, "compatible_systems": "SLUSHIE", "ai_notes": "Perfect slushie base"}]'
                }
            }]
        }
        mock_request.return_value = mock_response

        # Clear existing to prevent duplicate key
        Ingredient.all_objects.filter(name="Apple Juice").delete()

        ing = Ingredient.objects.create(
            name="Apple Juice",
            ingredient_type="OTHER",
            is_ready_to_drink=False,
            is_in_inventory=True
        )

        response = self.client.post(reverse('ai_bulk_analyze_api'))
        self.assertEqual(response.status_code, 202)
        
        from ..views.ai import ai_bulk_analyze_task
        ai_bulk_analyze_task(update_progress=lambda *args, **kwargs: None)
        
        ing.refresh_from_db()
        self.assertTrue(ing.is_ready_to_drink)

    def test_ingredient_is_dry_attribute(self) -> None:
        """Verify is_dry attribute handling in database creation, views, and serialization."""
        self.client.login(username="director", password="secure_password_123")
        
        # Test creating ingredient with is_dry=True via POST
        response = self.client.post(reverse('add_ingredient'), {
            'name': 'Powdered Cane Sugar',
            'brand': 'Lab Brand',
            'ingredient_type': 'ADDITIVE',
            'category': 'sweet',
            'is_dry': 'on'
        })
        self.assertEqual(response.status_code, 302)
        ing = Ingredient.objects.get(name='Powdered Cane Sugar')
        self.assertTrue(ing.is_dry)

        # Test editing ingredient with is_dry=False via POST
        response = self.client.post(reverse('edit_ingredient', args=[ing.uuid]), {
            'name': 'Powdered Cane Sugar',
            'brand': 'Lab Brand',
            'ingredient_type': 'ADDITIVE',
            'category': 'sweet',
            # is_dry not passed => becomes False
        })
        self.assertEqual(response.status_code, 302)
        ing.refresh_from_db()
        self.assertFalse(ing.is_dry)

    @patch('requests.request')
    def test_bulk_analyze_saves_is_dry(self, mock_request: MagicMock) -> None:
        """Verify that bulk AI analysis updates the is_dry attribute."""
        self.client.login(username="director", password="secure_password_123")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '[{"name": "Powdered Cane Sugar", "intensity": 3, "sweetness": 5, "acidity": 1, "bitterness": 1, "complexity": 1, "base_suitability": 1.0, "accent_suitability": 3.0, "category": "sweet", "ingredient_type": "ADDITIVE", "is_ready_to_drink": false, "is_dry": true, "compatible_systems": "SODA,SLUSHIE", "ai_notes": "Sweet granular sugar"}]'
                }
            }]
        }
        mock_request.return_value = mock_response

        # Clear existing to prevent duplicate key
        Ingredient.all_objects.filter(name="Powdered Cane Sugar").delete()

        ing = Ingredient.objects.create(
            name="Powdered Cane Sugar",
            ingredient_type="ADDITIVE",
            is_dry=False,
            is_in_inventory=True
        )

        response = self.client.post(reverse('ai_bulk_analyze_api'))
        self.assertEqual(response.status_code, 202)
        
        from ..views.ai import ai_bulk_analyze_task
        ai_bulk_analyze_task(update_progress=lambda *args, **kwargs: None)
        
        ing.refresh_from_db()
        self.assertTrue(ing.is_dry)

