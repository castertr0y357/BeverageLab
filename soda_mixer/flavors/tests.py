"""Comprehensive test suite for BeverageLab flavors application."""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import Ingredient, Recipe, RecipeIngredient, RecipeCategory, MixHistory, MixHistoryIngredient, SystemConfiguration, LLMProvider
from .recommendations import generate_recipe_name, suggest_categories, get_recommendation, get_tiered_recommendation, calculate_recipe_stats
from .ai_service import AIAssistant

User = get_user_model()


class BeverageLabModelTest(TestCase):
    """Test case for database models and properties."""

    def setUp(self) -> None:
        self.category = RecipeCategory.objects.create(name="Fruity", color="bg-pink")
        self.ingredient = Ingredient.objects.create(
            name="Mango Syrup",
            ingredient_type="SODA_SYRUP",
            category="tropical",
            intensity=3,
            sweetness=4,
            acidity=2,
            bitterness=1,
            complexity=3,
            is_in_inventory=True
        )
        self.recipe = Recipe.objects.create(
            name="Mango Bliss",
            drink_type="SODA",
            description="Pure tropical vibes",
            rating=5
        )
        self.recipe.categories.add(self.category)

    def test_recipe_category_creation(self) -> None:
        self.assertEqual(str(self.category), "Fruity")
        self.assertEqual(self.category.color, "bg-pink")

    def test_ingredient_creation(self) -> None:
        self.assertEqual(str(self.ingredient), "Mango Syrup")
        self.assertEqual(self.ingredient.category, "tropical")
        self.assertTrue(self.ingredient.is_in_inventory)

    def test_recipe_creation(self) -> None:
        self.assertEqual(str(self.recipe), "SODA: Mango Bliss")
        self.assertEqual(self.recipe.water_temp_f, None)
        
        self.recipe.water_temp_c = 95.0
        self.recipe.save()
        self.assertEqual(self.recipe.water_temp_f, 203.0)

    def test_recipe_ingredient_effective_profile(self) -> None:
        ri = RecipeIngredient.objects.create(
            recipe=self.recipe,
            ingredient=self.ingredient,
            amount=50.0,
            notes="Extra sweet"
        )
        
        profile = ri.effective_profile
        self.assertEqual(profile['sweetness'], 4)
        self.assertFalse(profile['is_synthesized'])

        # Apply synthesized overrides
        ri.sweetness = 5
        ri.save()
        profile_overridden = ri.effective_profile
        self.assertEqual(profile_overridden['sweetness'], 5)
        self.assertTrue(profile_overridden['is_synthesized'])

    def test_mix_history_and_ingredient(self) -> None:
        mix = MixHistory.objects.create(drink_type="SODA")
        mhi = MixHistoryIngredient.objects.create(
            mix=mix,
            ingredient=self.ingredient,
            amount=30.0,
            intensity=2
        )
        self.assertIn("Man", str(mix))
        self.assertEqual(mhi.effective_profile['intensity'], 2)
        self.assertEqual(mhi.effective_profile['sweetness'], 4)  # falls back to ingredient sweetness

    def test_system_configuration_singleton(self) -> None:
        config1 = SystemConfiguration.get_config()
        config1.mealie_url = "https://mealie.local"
        config1.save()
        
        config2 = SystemConfiguration.get_config()
        self.assertEqual(config2.mealie_url, "https://mealie.local")
        self.assertEqual(SystemConfiguration.objects.count(), 1)


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

    def test_calculate_recipe_stats(self) -> None:
        recipe = Recipe.objects.create(name="Test Mix")
        ri1 = RecipeIngredient.objects.create(recipe=recipe, ingredient=self.ing1, amount=10.0)
        ri2 = RecipeIngredient.objects.create(recipe=recipe, ingredient=self.ing3, amount=10.0)
        
        stats = calculate_recipe_stats([ri1, ri2])
        self.assertEqual(stats['sweetness'], 3.5)  # (2 + 5) / 2
        self.assertEqual(stats['acidity'], 3.0)  # (5 + 1) / 2


class BeverageLabViewsTest(TestCase):
    """Integration tests for application views and AJAX endpoints."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.staff_user = User.objects.create_user(username="director", password="secure_password_123", is_staff=True)
        
        self.ing = Ingredient.objects.create(
            name="Club Soda", ingredient_type="OTHER", category="sweet", intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1
        )
        self.recipe = Recipe.objects.create(name="Simple Soda", drink_type="SODA")
        self.ri = RecipeIngredient.objects.create(recipe=self.recipe, ingredient=self.ing, amount=200.0)

    def test_unauthenticated_user_redirect(self) -> None:
        # LaboratoryAccessMiddleware redirects unauthenticated requests
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_authenticated_user_home(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_ingredient_list_view(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        # Create additional ingredients to test alphabetical sorting across categories
        ing_apple = Ingredient.objects.create(
            name="Apple Juice", ingredient_type="OTHER", category="sweet", intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1
        )
        ing_lemon = Ingredient.objects.create(
            name="Zesty Lemon", ingredient_type="OTHER", category="citrus", intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1
        )
        
        response = self.client.get(reverse('ingredient_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Club Soda")
        
        # Verify alphabetical ordering by name across all categories
        names = [ing.name for ing in response.context['ingredients']]
        self.assertEqual(names, sorted(names))

    def test_mix_history_list_view(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        # Create a mix history entry
        mix = MixHistory.objects.create(drink_type="SODA")
        from .models import MixHistoryIngredient
        MixHistoryIngredient.objects.create(
            mix=mix,
            ingredient=self.ing,
            amount=150.0
        )
        response = self.client.get(reverse('mix_history_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Club Soda")
        self.assertContains(response, "Soda Lab")


    def test_add_ingredient_post(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(reverse('add_ingredient'), {
            'name': 'Ginger Beer',
            'ingredient_type': 'SODA_SYRUP',
            'category': 'spice',
            'intensity': 4,
            'sweetness': 3,
            'acidity': 2,
            'bitterness': 1,
            'complexity': 3,
            'ai_notes': 'Spicy carbonated beverage'
        })
        self.assertEqual(response.status_code, 302)
        ginger_beer = Ingredient.objects.get(name="Ginger Beer")
        self.assertEqual(ginger_beer.ai_notes, 'Spicy carbonated beverage')

    def test_edit_ingredient_unauthorized(self) -> None:
        # Non-staff cannot edit
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(reverse('edit_ingredient', args=[self.ing.id]), {
            'name': 'Super Soda'
        })
        self.assertEqual(response.status_code, 302)
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.name, "Club Soda")

    def test_edit_ingredient_authorized(self) -> None:
        self.client.login(username="director", password="secure_password_123")
        response = self.client.post(reverse('edit_ingredient', args=[self.ing.id]), {
            'name': 'Sparkling Water',
            'intensity': 2,
            'sweetness': 1,
            'acidity': 1,
            'bitterness': 1,
            'complexity': 1,
            'ai_notes': 'Crisp and bubbly'
        })
        self.assertEqual(response.status_code, 302)
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.name, "Sparkling Water")
        self.assertEqual(self.ing.ai_notes, "Crisp and bubbly")

    def test_delete_ingredient_authorized(self) -> None:
        self.client.login(username="director", password="secure_password_123")
        response = self.client.post(reverse('delete_ingredient', args=[self.ing.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Ingredient.objects.filter(id=self.ing.id).exists())

    def test_ajax_toggle_inventory(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(
            reverse('toggle_inventory_api', args=[self.ing.id]),
            data=json.dumps({'is_in_inventory': False}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.ing.refresh_from_db()
        self.assertFalse(self.ing.is_in_inventory)

    def test_ajax_rate_recipe(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(
            reverse('rate_recipe_api', args=[self.recipe.id]),
            data=json.dumps({'rating': 4}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.rating, 4)

    def test_ajax_save_and_promote_mix_history(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        
        # 1. Save mix to history
        response_save = self.client.post(
            reverse('save_mix_to_history_api'),
            data=json.dumps({
                'drink_type': 'SODA',
                'ingredients': [{'id': self.ing.id, 'amount': 150.0}]
            }),
            content_type="application/json"
        )
        self.assertEqual(response_save.status_code, 200)
        mix_id = response_save.json()['mix_id']
        self.assertTrue(MixHistory.objects.filter(id=mix_id).exists())

        # 2. Promote to Recipe
        response_promote = self.client.post(
            reverse('promote_mix_to_recipe_api', args=[mix_id]),
            data=json.dumps({
                'name': 'Promoted Elixir',
                'description': 'From ad-hoc history'
            }),
            content_type="application/json"
        )
        self.assertEqual(response_promote.status_code, 200)
        recipe_id = response_promote.json()['recipe_id']
        self.assertTrue(Recipe.objects.filter(id=recipe_id).exists())

    @patch('requests.request')
    def test_ai_suggest_api_force_type(self, mock_request: MagicMock) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
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

        Ingredient.objects.create(
            name="Whole Milk",
            ingredient_type="DAIRY",
            category="sweet",
            intensity=2,
            sweetness=3,
            acidity=1,
            bitterness=1,
            complexity=2,
            is_in_inventory=True
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Whole Milk", "reason": "Adds body", "resonance": 90, "amount": 50.0}]}'}}]
        }
        mock_request.return_value = mock_response

        response = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': ['Espresso Beans'],
                'drink_type': 'COFFEE',
                'force_type': 'DAIRY'
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['suggestions'][0]['name'], 'Whole Milk')
        
        args, kwargs = mock_request.call_args
        self.assertIn("MANDATORY RULE: You must ONLY suggest new ingredients of type 'DAIRY'", kwargs['json']['messages'][1]['content'])

    def test_save_llm_provider_api_thinking(self) -> None:
        self.client.login(username="director", password="secure_password_123")
        url = reverse('save_llm_provider_api')
        payload = {
            'name': 'New Ollama Substrate',
            'provider_type': 'OLLAMA',
            'base_url': 'http://localhost:11434',
            'default_model': 'gemma4:12b',
            'is_enabled': True,
            'enable_thinking': False,
            'thinking_effort': 'low'
        }
        response = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        
        provider = LLMProvider.objects.get(id=data['id'])
        self.assertEqual(provider.name, 'New Ollama Substrate')
        self.assertEqual(provider.enable_thinking, False)
        self.assertEqual(provider.thinking_effort, 'low')

    @patch('requests.request')
    def test_ai_bulk_analyze_view_api(self, mock_request: MagicMock) -> None:
        self.client.login(username="director", password="secure_password_123")
        # Configure LLM provider
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

        self.ing.intensity = 3
        self.ing.sweetness = 3
        self.ing.acidity = 3
        self.ing.bitterness = 1
        self.ing.complexity = 3
        self.ing.is_in_inventory = True
        self.ing.save()
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '[{"name": "Club Soda", "intensity": 1, "sweetness": 1, "acidity": 1, "bitterness": 1, "complexity": 1, "base_suitability": 1.0, "accent_suitability": 3.5, "ai_notes": "Sparkling water notes"}]'}}]
        }
        mock_request.return_value = mock_response

        response = self.client.post(reverse('ai_bulk_analyze_api'))
        self.assertEqual(response.status_code, 200)
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.intensity, 1)
        self.assertEqual(self.ing.base_suitability, 1.0)
        self.assertEqual(self.ing.accent_suitability, 3.5)
        self.assertEqual(self.ing.ai_notes, "Sparkling water notes")

    @patch('requests.request')
    def test_ai_bulk_analyze_captures_uninitialized_suitability(self, mock_request: MagicMock) -> None:
        self.client.login(username="director", password="secure_password_123")
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

        # Non-default stats, but default suitability (3.0, 3.0)
        self.ing.intensity = 4
        self.ing.sweetness = 4
        self.ing.acidity = 2
        self.ing.bitterness = 2
        self.ing.complexity = 4
        self.ing.base_suitability = 3.0
        self.ing.accent_suitability = 3.0
        self.ing.is_in_inventory = True
        self.ing.save()
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '[{"name": "Club Soda", "intensity": 4, "sweetness": 4, "acidity": 2, "bitterness": 2, "complexity": 4, "base_suitability": 1.5, "accent_suitability": 4.2, "ai_notes": "Custom base suitability notes"}]'}}]
        }
        mock_request.return_value = mock_response

        response = self.client.post(reverse('ai_bulk_analyze_api'))
        self.assertEqual(response.status_code, 200)
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.base_suitability, 1.5)
        self.assertEqual(self.ing.accent_suitability, 4.2)
        self.assertEqual(self.ing.ai_notes, "Custom base suitability notes")

    def test_home_page_renders_empty_mode_message_element(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="emptyModeMessage"')
        self.assertContains(response, 'id="stepHeader"')


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
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Lime", "reason": "tartness", "resonance": 90, "amount": 20.0}]}'}}]
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
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Espresso Bean", "reason": "strong base", "resonance": 95, "amount": 18.0}]}'}}]
        }
        mock_request.return_value = mock_response

        res = AIAssistant.suggest_autonomous(["Whole Milk"], mode="standard", drink_type="COFFEE")
        self.assertIsNotNone(res)
        self.assertEqual(res['suggestions'][0]['name'], "Espresso Bean")
        self.assertEqual(res['suggestions'][0]['amount'], 18.0)

    @patch.dict('os.environ', {'MOCK_MODE': 'True'})
    def test_ai_suggest_autonomous_mock_coffee(self) -> None:
        res = AIAssistant.suggest_autonomous(["Espresso"], mode="standard", drink_type="COFFEE")
        self.assertIsNotNone(res)
        self.assertEqual(res['suggestions'][0]['name'], "Espresso")
        self.assertEqual(res['suggestions'][0]['amount'], 18.0)
        self.assertEqual(res['rebalancing']['Espresso'], 18.0)

    @patch('requests.request')
    def test_ai_suggest_autonomous_force_type(self, mock_request: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Whole Milk", "reason": "creamy", "resonance": 92, "amount": 50.0}]}'}}]
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


class BeverageLabSettingsTest(TestCase):
    """Test case for settings and environment variable bindings."""

    def test_csrf_trusted_origins_loaded(self) -> None:
        import os
        from django.conf import settings
        expected = []

        raw_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
        if raw_csrf:
            for origin in raw_csrf.split(','):
                origin = origin.strip()
                if origin:
                    expected.append(origin)

        service_url = os.environ.get('SERVICE_URL_WEB', '').strip()
        if service_url:
            expected.append(service_url)
            if service_url.startswith('http://'):
                expected.append(service_url.replace('http://', 'https://'))
            elif service_url.startswith('https://'):
                expected.append(service_url.replace('https://', 'http://'))

        service_fqdn = os.environ.get('SERVICE_FQDN_WEB', '').strip()
        if service_fqdn:
            expected.append(f"http://{service_fqdn}")
            expected.append(f"https://{service_fqdn}")

        for host in os.environ.get('ALLOWED_HOSTS', '*').split(','):
            host = host.strip()
            if host and host != '*':
                if host.startswith('.'):
                    host = host[1:]
                expected.append(f"http://{host}")
                expected.append(f"https://{host}")

        expected = list(set(expected))
        self.assertCountEqual(settings.CSRF_TRUSTED_ORIGINS, expected)

    def test_custom_csrf_middleware_trusts_same_host_mismatched_scheme(self) -> None:
        from django.test import RequestFactory
        from soda_mixer.flavors.middleware import LaboratoryCsrfMiddleware

        factory = RequestFactory()
        # Browser sends secure Origin header matching host (mismatched scheme)
        request = factory.post('/', HTTP_HOST='beveragelab.castertr0y357.net', HTTP_ORIGIN='https://beveragelab.castertr0y357.net')
        middleware = LaboratoryCsrfMiddleware(lambda r: None)
        self.assertTrue(middleware._origin_verified(request))

        # Browser sends Origin header with different host
        request_attacker = factory.post('/', HTTP_HOST='beveragelab.castertr0y357.net', HTTP_ORIGIN='https://attacker.com')
        self.assertFalse(middleware._origin_verified(request_attacker))


class BeverageLabBrandTrackingTest(TestCase):
    """Test case for ingredient brand tracking features."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.staff_user = User.objects.create_user(username="director", password="secure_password_123", is_staff=True)

    def test_unique_together_constraint(self) -> None:
        # Create ingredient with brand Monin
        Ingredient.objects.create(name="Vanilla Syrup", brand="Monin", category="sweet")
        
        # We should be able to create another with brand Torani
        ing_torani = Ingredient.objects.create(name="Vanilla Syrup", brand="Torani", category="sweet")
        self.assertEqual(ing_torani.brand, "Torani")

        # But trying to create a duplicate (name, brand) should raise IntegrityError
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Ingredient.objects.create(name="Vanilla Syrup", brand="Monin", category="sweet")

    def test_get_display_name_helper(self) -> None:
        from .views.ai import get_display_name, get_multibrand_names_in_inventory
        
        ing_monin = Ingredient.objects.create(name="Vanilla Syrup", brand="Monin", category="sweet", is_in_inventory=True)
        
        # When only one brand is available, it should NOT show the brand on the synthesis page
        multibrand = get_multibrand_names_in_inventory()
        self.assertNotIn("vanilla syrup", multibrand)
        self.assertEqual(get_display_name(ing_monin, multibrand), "Vanilla Syrup")

        # Add another brand
        ing_torani = Ingredient.objects.create(name="Vanilla Syrup", brand="Torani", category="sweet", is_in_inventory=True)
        
        # Now multiple brands are available, so it SHOULD show the brand
        multibrand = get_multibrand_names_in_inventory()
        self.assertIn("vanilla syrup", multibrand)
        self.assertEqual(get_display_name(ing_monin, multibrand), "Vanilla Syrup (Monin)")
        self.assertEqual(get_display_name(ing_torani, multibrand), "Vanilla Syrup (Torani)")

    def test_add_ingredient_with_brand(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(reverse('add_ingredient'), {
            'name': 'Lavender Syrup',
            'brand': 'Monin',
            'ingredient_type': 'SODA_SYRUP',
            'category': 'floral',
            'intensity': 3,
            'sweetness': 3,
            'acidity': 1,
            'bitterness': 1,
            'complexity': 2
        })
        self.assertEqual(response.status_code, 302)
        
        ing = Ingredient.objects.get(name="Lavender Syrup")
        self.assertEqual(ing.brand, "Monin")

    def test_edit_ingredient_with_brand(self) -> None:
        ing = Ingredient.objects.create(name="Peach Syrup", brand="Torani", category="fruit")
        self.client.login(username="director", password="secure_password_123")
        response = self.client.post(reverse('edit_ingredient', args=[ing.id]), {
            'name': 'Peach Syrup',
            'brand': 'Monin',
            'intensity': 3,
            'sweetness': 3,
            'acidity': 2,
            'bitterness': 1,
            'complexity': 2
        })
        self.assertEqual(response.status_code, 302)
        
        ing.refresh_from_db()
        self.assertEqual(ing.brand, "Monin")

    def test_ingredient_list_shows_brand_badge_only_when_multibrand(self) -> None:
        # 1. Create a unique flavor
        unique_ing = Ingredient.objects.create(name="Apple Syrup", brand="Monin", category="fruit")
        
        # 2. Create duplicate flavor name with different brands
        dupe_ing1 = Ingredient.objects.create(name="Ginger Syrup", brand="Monin", category="spice")
        dupe_ing2 = Ingredient.objects.create(name="Ginger Syrup", brand="Torani", category="spice")
        
        # 3. Request the ingredient list page
        self.client.login(username="director", password="secure_password_123")
        response = self.client.get(reverse('ingredient_list'))
        self.assertEqual(response.status_code, 200)
        
        # Check context attributes
        ingredients = {ing.id: ing for ing in response.context['ingredients']}
        
        # Unique flavor should NOT show brand badge
        self.assertIn(unique_ing.id, ingredients)
        self.assertFalse(ingredients[unique_ing.id].show_brand)
        
        # Duplicate flavors SHOULD show brand badge
        self.assertIn(dupe_ing1.id, ingredients)
        self.assertTrue(ingredients[dupe_ing1.id].show_brand)
        self.assertIn(dupe_ing2.id, ingredients)
        self.assertTrue(ingredients[dupe_ing2.id].show_brand)


class BeverageLabCoffeeScalingTest(TestCase):
    """Test case for Coffee Lab shot scaling logic."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.bean = Ingredient.objects.create(
            name="Espresso Bean",
            ingredient_type="COFFEE_BEAN",
            category="coffee",
            intensity=4,
            sweetness=2,
            acidity=3,
            bitterness=4,
            complexity=4
        )

    def test_save_coffee_mix_history_scaled(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        # 1-shot scale (0.5x of 18g = 9g)
        response = self.client.post(
            reverse('save_mix_to_history_api'),
            data=json.dumps({
                'drink_type': 'COFFEE',
                'ingredients': [{'id': self.bean.id, 'amount': 9.0}]
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        mix_id = response.json()['mix_id']
        mix = MixHistory.objects.get(id=mix_id)
        self.assertEqual(mix.drink_type, 'COFFEE')
        self.assertEqual(mix.mix_ingredients.first().amount, 9.0)

    def test_create_coffee_recipe_scaled(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(reverse('create_recipe'), {
            'name': 'Espresso Double Shot',
            'drink_type': 'COFFEE',
            f'amount_{self.bean.id}': 18.0,
            f'notes_{self.bean.id}': '2-shot scale'
        })
        self.assertEqual(response.status_code, 302)
        recipe = Recipe.objects.get(name='Espresso Double Shot')
        self.assertEqual(recipe.drink_type, 'COFFEE')
        ri = recipe.recipe_ingredients.first()
        self.assertEqual(ri.ingredient, self.bean)
        self.assertEqual(ri.amount, 18.0)


class BeverageLabCoffeeSanitizationTest(TestCase):
    """Test case for coffee amount sanitization rules."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.client.login(username="lab_tech", password="secure_password_123")
        self.bean = Ingredient.objects.create(
            name="Espresso Beans",
            brand="Monin",
            ingredient_type="COFFEE_BEAN",
            category="coffee",
            is_in_inventory=True
        )
        self.creamer = Ingredient.objects.create(
            name="Whole Milk",
            brand="Local Dairy",
            ingredient_type="DAIRY",
            category="sweet",
            is_in_inventory=True
        )
        self.syrup = Ingredient.objects.create(
            name="Caramel Syrup",
            brand="Torani",
            ingredient_type="OTHER",
            category="sweet",
            is_in_inventory=True
        )

    def test_sanitize_coffee_amount(self) -> None:
        from .views.ai import sanitize_coffee_amount
        self.assertEqual(sanitize_coffee_amount(self.bean, 100.0), 18.0)
        self.assertEqual(sanitize_coffee_amount(self.creamer, 50.0), 50.0)
        self.assertEqual(sanitize_coffee_amount(self.syrup, 25.0), 15.0)
        sugar = Ingredient.objects.create(
            name="Honey",
            ingredient_type="ADDITIVE",
            category="sweet",
            is_in_inventory=True
        )
        self.assertEqual(sanitize_coffee_amount(sugar, 25.0), 15.0)

    @patch('soda_mixer.flavors.ai_service.AIAssistant.suggest_autonomous')
    def test_ai_suggest_api_coffee_sanitization(self, mock_suggest: MagicMock) -> None:
        mock_suggest.return_value = {
            "suggestions": [
                {
                    "name": "Whole Milk (Local Dairy)",
                    "reason": "Creams it up",
                    "resonance": 95,
                    "amount": 100.0,
                    "profile": {"intensity": 2, "sweetness": 2, "acidity": 1, "bitterness": 1, "complexity": 1}
                }
            ],
            "rebalancing": {
                "Espresso Beans (Monin)": 100.0
            },
            "seal_recommended": False,
            "seal_resonance": 80,
            "reasoning": "Test suggestion rebalancing."
        }

        response = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': ['Espresso Beans (Monin)'],
                'drink_type': 'COFFEE',
                'mode': 'standard'
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify suggestions amount is coerced to 50.0 (Whole Milk is DAIRY)
        self.assertEqual(data['suggestions'][0]['amount'], 50.0)
        # Verify rebalancing amount is coerced to 18.0 (Espresso Beans is COFFEE_BEAN)
        self.assertEqual(data['rebalancing']['Espresso Beans (Monin)'], 18.0)

    @patch('soda_mixer.flavors.ai_service.AIAssistant.suggest_autonomous')
    def test_ai_suggest_api_coffee_rebalancing_unmatched_key_dropped(self, mock_suggest: MagicMock) -> None:
        """Unrecognized rebalancing keys must be dropped to prevent raw AI values leaking."""
        mock_suggest.return_value = {
            "suggestions": [
                {
                    "name": "Whole Milk (Local Dairy)",
                    "reason": "Creams it up",
                    "resonance": 95,
                    "amount": 100.0,
                    "profile": {"intensity": 2, "sweetness": 2, "acidity": 1, "bitterness": 1, "complexity": 1}
                }
            ],
            "rebalancing": {
                "Espresso Roast Supreme": 100.0,
                "Unknown Bean Variety": 50.0
            },
            "seal_recommended": False,
            "seal_resonance": 80,
            "reasoning": "Test unmatched rebalancing keys."
        }

        response = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': ['Espresso Beans (Monin)'],
                'drink_type': 'COFFEE',
                'mode': 'standard'
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Unmatched rebalancing keys should be dropped entirely
        self.assertEqual(data['rebalancing'], {})

    @patch('soda_mixer.flavors.ai_service.AIAssistant.suggest_autonomous')
    def test_ai_suggest_api_force_type_filtering(self, mock_suggest: MagicMock) -> None:
        """Verify that suggestions not matching the force_type are programmatically filtered out."""
        Ingredient.objects.create(
            name="Vanilla Syrup",
            brand="Monin",
            ingredient_type="ADDITIVE",
            category="sweet",
            is_in_inventory=True
        )

        mock_suggest.return_value = {
            "suggestions": [
                {
                    "name": "Whole Milk (Local Dairy)",
                    "reason": "Creams it up",
                    "resonance": 95,
                    "amount": 50.0,
                    "profile": {"intensity": 2, "sweetness": 2, "acidity": 1, "bitterness": 1, "complexity": 1}
                },
                {
                    "name": "Vanilla Syrup (Monin)",
                    "reason": "Adds vanilla sweetness",
                    "resonance": 90,
                    "amount": 15.0,
                    "profile": {"intensity": 3, "sweetness": 4, "acidity": 1, "bitterness": 1, "complexity": 2}
                }
            ],
            "rebalancing": {},
            "seal_recommended": False,
            "seal_resonance": 80,
            "reasoning": "Test force_type filtering."
        }

        response = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': ['Espresso Beans (Monin)'],
                'drink_type': 'COFFEE',
                'force_type': 'DAIRY'
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify only Whole Milk (DAIRY) is returned, and Vanilla Syrup (ADDITIVE) is filtered out
        suggestions = data['suggestions']
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['name'], 'Whole Milk')



class BeverageLabIcedCoffeeTest(TestCase):
    """Test case for iced coffee recipe logic and details page rendering."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.client.login(username="lab_tech", password="secure_password_123")
        self.bean = Ingredient.objects.create(
            name="Espresso Beans",
            brand="Monin",
            ingredient_type="COFFEE_BEAN",
            category="coffee",
            is_in_inventory=True
        )
        self.creamer = Ingredient.objects.create(
            name="Whole Milk",
            brand="Local Dairy",
            ingredient_type="DAIRY",
            category="sweet",
            is_in_inventory=True
        )

    def test_create_iced_coffee_recipe(self) -> None:
        response = self.client.post(reverse('create_recipe'), {
            'name': 'Iced Vanilla Latte',
            'drink_type': 'COFFEE',
            'coffee_style': 'iced',
            'coffee_base_type': 'standard_brew',
            'drink_size_oz': '12',
            f'amount_{self.bean.id}': 18.0,
            f'amount_{self.creamer.id}': 36.0,  # 60ml * 0.6 = 36ml
        })
        self.assertEqual(response.status_code, 302)
        recipe = Recipe.objects.get(name='Iced Vanilla Latte')
        self.assertEqual(recipe.coffee_style, 'iced')
        self.assertEqual(recipe.coffee_base_type, 'standard_brew')
        self.assertEqual(recipe.drink_size_oz, 12.0)
        
        # Verify detail page renders successfully
        detail_url = reverse('recipe_detail', args=[recipe.id])
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Iced')
        self.assertContains(detail_response, 'Ice')
        self.assertContains(detail_response, 'iceDetailVolume')

    def test_random_pairing_api_coffee_secondary_dairy(self) -> None:
        """Verify that Coffee Lab random pairing selects DAIRY as the secondary ingredient (index 1)."""
        Ingredient.objects.create(
            name="Vanilla Syrup",
            brand="Monin",
            ingredient_type="ADDITIVE",
            category="sweet",
            is_in_inventory=True
        )

        response = self.client.post(
            reverse('random_pairing_api'),
            data=json.dumps({
                'drink_type': 'COFFEE',
                'mode': 'standard'
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        ingredients = data['ingredients']
        # The first ingredient should be the coffee bean (index 0)
        self.assertEqual(ingredients[0]['type'], 'COFFEE_BEAN')
        # The secondary ingredient must be DAIRY (index 1)
        self.assertEqual(ingredients[1]['type'], 'DAIRY')
        # There should be between 3 and 5 ingredients
        self.assertIn(len(ingredients), [3, 4, 5])


class BeverageLabBatchSizesTest(TestCase):
    """Test case for soda and slushie batch sizes and scaling logic."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.client.login(username="lab_tech", password="secure_password_123")
        self.syrup = Ingredient.objects.create(
            name="Lemon Syrup",
            brand="Monin",
            ingredient_type="SODA_SYRUP",
            category="citrus",
            is_in_inventory=True
        )

    def test_create_soda_recipe_12oz(self) -> None:
        response = self.client.post(reverse('create_recipe'), {
            'name': 'Soda 12oz Test',
            'drink_type': 'SODA',
            'drink_size_oz': '12.0',
            f'amount_{self.syrup.id}': 50.0,
        })
        self.assertEqual(response.status_code, 302)
        recipe = Recipe.objects.get(name='Soda 12oz Test')
        self.assertEqual(recipe.drink_type, 'SODA')
        self.assertEqual(recipe.drink_size_oz, 12.0)

        # Verify detail page renders with 12oz details
        detail_url = reverse('recipe_detail', args=[recipe.id])
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, '12oz')
        self.assertContains(detail_response, 'scale12oz')

    def test_create_slushie_recipe_16oz(self) -> None:
        response = self.client.post(reverse('create_recipe'), {
            'name': 'Slushie 16oz Test',
            'drink_type': 'SLUSHIE',
            'drink_size_oz': '16.0',
            f'amount_{self.syrup.id}': 80.0,
        })
        self.assertEqual(response.status_code, 302)
        recipe = Recipe.objects.get(name='Slushie 16oz Test')
        self.assertEqual(recipe.drink_type, 'SLUSHIE')
        self.assertEqual(recipe.drink_size_oz, 16.0)

        # Verify detail page renders
        detail_url = reverse('recipe_detail', args=[recipe.id])
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, '16oz')
        self.assertContains(detail_response, 'scale16oz')

    def test_create_slushie_recipe_64oz(self) -> None:
        response = self.client.post(reverse('create_recipe'), {
            'name': 'Slushie 64oz Test',
            'drink_type': 'SLUSHIE',
            'drink_size_oz': '64.0',
            f'amount_{self.syrup.id}': 320.0,
        })
        self.assertEqual(response.status_code, 302)
        recipe = Recipe.objects.get(name='Slushie 64oz Test')
        self.assertEqual(recipe.drink_type, 'SLUSHIE')
        self.assertEqual(recipe.drink_size_oz, 64.0)

        # Verify detail page renders
        detail_url = reverse('recipe_detail', args=[recipe.id])
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, '64oz')
        self.assertContains(detail_response, 'scale64oz')


class BeverageLabRecipeListFilterSortTest(TestCase):
    """Test case for filtering and sorting on the recipe list page."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.client.login(username="lab_tech", password="secure_password_123")

        # Create some recipes
        self.recipe_soda = Recipe.objects.create(name="Alpha Soda", drink_type="SODA")
        self.recipe_coffee = Recipe.objects.create(name="Gamma Coffee", drink_type="COFFEE")
        self.recipe_slushie = Recipe.objects.create(name="Beta Slushie", drink_type="SLUSHIE")

    def test_filter_by_drink_type(self) -> None:
        url = reverse('recipe_list')
        
        # Filter: Soda only
        response = self.client.get(url, {'drink_type': 'SODA'})
        self.assertEqual(response.status_code, 200)
        recipes = list(response.context['recipes'])
        self.assertEqual(len(recipes), 1)
        self.assertEqual(recipes[0].name, "Alpha Soda")

        # Filter: Coffee only
        response = self.client.get(url, {'drink_type': 'COFFEE'})
        self.assertEqual(response.status_code, 200)
        recipes = list(response.context['recipes'])
        self.assertEqual(len(recipes), 1)
        self.assertEqual(recipes[0].name, "Gamma Coffee")

    def test_sort_alphabetically(self) -> None:
        url = reverse('recipe_list')

        # Sort: A-Z
        response = self.client.get(url, {'sort': 'name'})
        self.assertEqual(response.status_code, 200)
        recipes = list(response.context['recipes'])
        self.assertEqual(recipes[0].name, "Alpha Soda")
        self.assertEqual(recipes[1].name, "Beta Slushie")
        self.assertEqual(recipes[2].name, "Gamma Coffee")

        # Sort: Z-A
        response = self.client.get(url, {'sort': '-name'})
        self.assertEqual(response.status_code, 200)
        recipes = list(response.context['recipes'])
        self.assertEqual(recipes[0].name, "Gamma Coffee")
        self.assertEqual(recipes[1].name, "Beta Slushie")
        self.assertEqual(recipes[2].name, "Alpha Soda")

    def test_sort_by_date_created(self) -> None:
        url = reverse('recipe_list')

        # Sort: Oldest First (created_at)
        response = self.client.get(url, {'sort': 'created_at'})
        self.assertEqual(response.status_code, 200)
        recipes = list(response.context['recipes'])
        self.assertEqual(recipes[0].name, "Alpha Soda")
        self.assertEqual(recipes[1].name, "Gamma Coffee")
        self.assertEqual(recipes[2].name, "Beta Slushie")

        # Sort: Newest First (-created_at)
        response = self.client.get(url, {'sort': '-created_at'})
        self.assertEqual(response.status_code, 200)
        recipes = list(response.context['recipes'])
        self.assertEqual(recipes[0].name, "Beta Slushie")
        self.assertEqual(recipes[1].name, "Gamma Coffee")
        self.assertEqual(recipes[2].name, "Alpha Soda")


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
        self.assertEqual(response.status_code, 200)
        
        self.ing_soda.refresh_from_db()
        self.assertEqual(self.ing_soda.category, "sweet")
        self.assertEqual(self.ing_soda.ingredient_type, "SODA_SYRUP")
        self.assertEqual(self.ing_soda.compatible_systems, "SODA,SLUSHIE")

    def test_recommendation_filtering_by_system_compatibility(self) -> None:
        # Clear seeded ingredients to have a clean slate for recommendations test
        Ingredient.objects.all().delete()
        
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

        # Standard mode recommendations in Coffee drink lab should only return Coffee system compatible ingredients
        recs_std = get_recommendation([self.ing_coffee.id], drink_type="COFFEE", experimental=False)
        rec_ingredients_std = [r['ingredient'] for r in recs_std['recommended']]
        for ing in rec_ingredients_std:
            self.assertIn("COFFEE", ing.compatible_systems)

        # Experimental mode bypasses system compatibility filters
        recs_exp = get_recommendation([self.ing_coffee.id], drink_type="COFFEE", experimental=True)
        rec_ingredients_exp = [r['ingredient'] for r in recs_exp['recommended']]
        # Should be able to find self.ing_soda (compatible only with SODA) in results
        self.assertTrue(any(ing.id == self.ing_soda.id for ing in rec_ingredients_exp))

