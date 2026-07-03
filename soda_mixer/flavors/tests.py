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


def _get_sse_data(response) -> dict:
    content = b"".join(response.streaming_content).decode('utf-8')
    for line in content.split('\n\n'):
        if line.strip().startswith('data:'):
            parsed = json.loads(line.replace('data:', '').strip())
            if parsed.get('status') == 'success':
                return parsed
    return {}


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
        self.assertEqual(len(recs["recommended"]), 10)

        # get_tiered_recommendation should also return up to 10
        tiered_recs = get_tiered_recommendation(self.ing1.id, drink_type="SODA")
        self.assertEqual(len(tiered_recs["recommended"]), 10)


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

    def test_ingredient_list_system_filtering(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        # Create ingredients with specific compatible_systems
        ing_soda = Ingredient.objects.create(
            name="Soda Ingredient Only", ingredient_type="OTHER", category="sweet",
            intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1,
            compatible_systems="SODA"
        )
        ing_coffee = Ingredient.objects.create(
            name="Coffee Ingredient Only", ingredient_type="OTHER", category="coffee",
            intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1,
            compatible_systems="COFFEE"
        )
        ing_slushie = Ingredient.objects.create(
            name="Cryo Ingredient Only", ingredient_type="OTHER", category="tropical",
            intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1,
            compatible_systems="SLUSHIE"
        )

        # Filter by soda system
        response = self.client.get(reverse('ingredient_list'), {'system': 'soda'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Soda Ingredient Only")
        self.assertNotContains(response, "Coffee Ingredient Only")
        self.assertNotContains(response, "Cryo Ingredient Only")

        # Filter by coffee system
        response = self.client.get(reverse('ingredient_list'), {'system': 'coffee'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coffee Ingredient Only")
        self.assertNotContains(response, "Soda Ingredient Only")
        self.assertNotContains(response, "Cryo Ingredient Only")

        # Filter by cryo system
        response = self.client.get(reverse('ingredient_list'), {'system': 'cryo'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cryo Ingredient Only")
        self.assertNotContains(response, "Soda Ingredient Only")
        self.assertNotContains(response, "Coffee Ingredient Only")

    def test_ingredient_list_categories_filtered_by_system(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        # Ensure we have clean test data for this test case
        from .models import MixHistoryIngredient, RecipeIngredient
        MixHistoryIngredient.objects.all().delete()
        RecipeIngredient.objects.all().delete()
        Ingredient.objects.all().delete()
        
        # Create categories and ingredients with specific compatible_systems
        Ingredient.objects.create(
            name="Soda Ingredient", ingredient_type="OTHER", category="citrus",
            intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1,
            compatible_systems="SODA"
        )
        Ingredient.objects.create(
            name="Coffee Ingredient", ingredient_type="OTHER", category="coffee",
            intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1,
            compatible_systems="COFFEE"
        )

        # Get list with system=soda, categories should only contain "citrus" (since coffee isn't compatible with SODA)
        response = self.client.get(reverse('ingredient_list'), {'system': 'soda'})
        self.assertEqual(response.status_code, 200)
        categories = [cat[0] for cat in response.context['categories']]
        self.assertIn("citrus", categories)
        self.assertNotIn("coffee", categories)

        # Get list with system=coffee, categories should only contain "coffee"
        response = self.client.get(reverse('ingredient_list'), {'system': 'coffee'})
        self.assertEqual(response.status_code, 200)
        categories = [cat[0] for cat in response.context['categories']]
        self.assertIn("coffee", categories)
        self.assertNotIn("citrus", categories)

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
        response = self.client.post(reverse('edit_ingredient', args=[self.ing.uuid]), {
            'name': 'Super Soda'
        })
        self.assertEqual(response.status_code, 302)
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.name, "Club Soda")

    def test_edit_ingredient_authorized(self) -> None:
        self.client.login(username="director", password="secure_password_123")
        response = self.client.post(reverse('edit_ingredient', args=[self.ing.uuid]), {
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
        response = self.client.post(reverse('delete_ingredient', args=[self.ing.uuid]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Ingredient.objects.filter(id=self.ing.id).exists())

    def test_ajax_toggle_inventory(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(
            reverse('toggle_inventory_api', args=[self.ing.uuid]),
            data=json.dumps({'is_in_inventory': False}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.ing.refresh_from_db()
        self.assertFalse(self.ing.is_in_inventory)

    def test_ajax_rate_recipe(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(
            reverse('rate_recipe_api', args=[self.recipe.uuid]),
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
        self.assertTrue(MixHistory.objects.filter(uuid=mix_id).exists())

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
        self.assertTrue(Recipe.objects.filter(uuid=recipe_id).exists())

    def test_get_recommendations_api_virtual_water(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.post(
            reverse('get_recommendations_api'),
            data=json.dumps({
                'ingredient_ids': ['virtual_water'],
                'drink_type': 'SLUSHIE'
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('recommended', data)

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
        data = _get_sse_data(response)
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

    def test_save_llm_provider_api_keep_warm(self) -> None:
        self.client.login(username="director", password="secure_password_123")
        url = reverse('save_llm_provider_api')
        payload = {
            'name': 'New Ollama Substrate',
            'provider_type': 'OLLAMA',
            'base_url': 'http://localhost:11434',
            'default_model': 'gemma4:12b',
            'is_enabled': True,
            'enable_thinking': False,
            'thinking_effort': 'low',
            'enable_keep_warm': True
        }
        response = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        
        provider = LLMProvider.objects.get(id=data['id'])
        self.assertEqual(provider.enable_keep_warm, True)

    @patch('requests.request')
    def test_keep_warm_provider_ollama(self, mock_request: MagicMock) -> None:
        provider = LLMProvider.objects.create(
            name="Ollama Keep Warm Test",
            provider_type="OLLAMA",
            base_url="http://localhost:11434",
            default_model="mistral",
            is_enabled=True,
            enable_keep_warm=True
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "ok"}
        }
        mock_request.return_value = mock_response

        from .ai_service import AIAssistant
        success = AIAssistant.keep_warm_provider(provider)
        self.assertTrue(success)
        
        args, kwargs = mock_request.call_args
        self.assertIn("NONE - Initial Synthesis", kwargs['json']['messages'][1]['content'])
        self.assertEqual(kwargs['json']['model'], 'mistral')

    @patch('requests.request')
    def test_preheat_suggestions_cache(self, mock_request: MagicMock) -> None:
        provider = LLMProvider.objects.create(
            name="Mock Ollama Preheat",
            provider_type="OLLAMA",
            base_url="http://localhost:11434",
            default_model="mistral",
            is_enabled=True
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "ok"}
        }
        mock_request.return_value = mock_response

        from .ai_service import AIAssistant
        AIAssistant.preheat_suggestions_cache(provider)
        
        args, kwargs = mock_request.call_args
        self.assertIn("NONE - Initial Synthesis", kwargs['json']['messages'][1]['content'])
        self.assertEqual(kwargs['json']['model'], 'mistral')

    @patch('soda_mixer.flavors.ai_service.AIAssistant.preheat_suggestions_cache')
    def test_ingredient_change_triggers_preheat_signal(self, mock_preheat: MagicMock) -> None:
        # Save an ingredient to trigger signal receiver
        self.ing.is_in_inventory = True
        self.ing.save()
        
        self.assertTrue(mock_preheat.called)

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
        self.assertEqual(response.status_code, 202)
        
        from .views.ai import ai_bulk_analyze_task
        ai_bulk_analyze_task(update_progress=lambda *args, **kwargs: None)
        
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
        self.assertEqual(response.status_code, 202)
        
        from .views.ai import ai_bulk_analyze_task
        ai_bulk_analyze_task(update_progress=lambda *args, **kwargs: None)
        
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

    @patch('requests.request')
    def test_ai_suggest_api_streams_progress(self, mock_request: MagicMock) -> None:
        """Verify that ai_suggest_api returns a StreamingHttpResponse with progress event payloads."""
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

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Club Soda", "reason": "Adds fizz", "resonance": 95, "amount": 100.0}]}'}}]
        }
        mock_request.return_value = mock_response

        response = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': ['Espresso Beans'],
                'drink_type': 'COFFEE',
            }),
            content_type="application/json"
        )
        
        # Verify it returns a streaming response
        self.assertTrue(response.streaming)
        self.assertEqual(response['Content-Type'], 'text/event-stream')

        # Decode streamed content chunks
        content = b"".join(response.streaming_content).decode('utf-8')
        lines = [line.strip() for line in content.split('\n\n') if line.strip()]

        # Parse messages
        progress_msgs = []
        success_data = None
        for line in lines:
            if line.startswith('data:'):
                parsed = json.loads(line.replace('data:', '').strip())
                if parsed.get('status') == 'progress':
                    progress_msgs.append(parsed.get('message'))
                elif parsed.get('status') == 'success':
                    success_data = parsed

        # Assert progress messages are sent in order
        self.assertIn("Scanning current compound registry...", progress_msgs)
        self.assertIn("Locating matching flavor affinity groups...", progress_msgs)
        self.assertIn("Querying Mixology Oracle...", progress_msgs)
        self.assertIn("Sanitizing extraction volumes & balancing ratios...", progress_msgs)

        # Assert final success payload contains suggestions
        self.assertIsNotNone(success_data)
        self.assertEqual(success_data['status'], 'success')
        self.assertEqual(success_data['suggestions'][0]['name'], 'Club Soda')


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
        response = self.client.post(reverse('edit_ingredient', args=[ing.uuid]), {
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
        mix = MixHistory.objects.get(uuid=mix_id)
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
        data = _get_sse_data(response)
        
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
        data = _get_sse_data(response)

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
        data = _get_sse_data(response)
        
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
        detail_url = reverse('recipe_detail', args=[recipe.uuid])
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
        detail_url = reverse('recipe_detail', args=[recipe.uuid])
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
        detail_url = reverse('recipe_detail', args=[recipe.uuid])
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
        detail_url = reverse('recipe_detail', args=[recipe.uuid])
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
        self.assertEqual(response.status_code, 202)
        
        from .views.ai import ai_bulk_analyze_task
        ai_bulk_analyze_task(update_progress=lambda *args, **kwargs: None)
        
        self.ing_soda.refresh_from_db()
        self.assertEqual(self.ing_soda.category, "sweet")
        self.assertEqual(self.ing_soda.ingredient_type, "SODA_SYRUP")
        self.assertEqual(self.ing_soda.compatible_systems, "SODA,SLUSHIE")

    def test_recommendation_filtering_by_system_compatibility(self) -> None:
        # Clear seeded ingredients to have a clean slate for recommendations test
        Ingredient.all_objects.all().delete()
        
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
        
        from .views.ai import ai_bulk_analyze_task
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
        
        from .views.ai import ai_bulk_analyze_task
        ai_bulk_analyze_task(update_progress=lambda *args, **kwargs: None)
        
        ing.refresh_from_db()
        self.assertTrue(ing.is_dry)


class BeverageLabCoffeeChemistryTest(TestCase):
    """Test suite for the new Coffee Chemistry Engine API."""

    def setUp(self) -> None:
        from django.contrib.auth.models import User
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.client.login(username="lab_tech", password="secure_password_123")

    def test_empty_ingredients(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': []
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Fail", data['recipe_validation'])
        self.assertEqual(data['ingredients']['coffee_base_mix'], [])

    def test_single_base_metrics(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Kenya AA',
                        'ingredient_type': 'COFFEE_BEAN',
                        'body_intensity': 3.0,
                        'acidity_score': 5.0,
                        'bitterness_score': 2.0,
                        'flavor_notes': ['citrus', 'blackcurrant'],
                        'is_decaf': False,
                        'amount': 18.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        metrics = data['aggregate_base_metrics']
        self.assertEqual(metrics['calculated_body'], 3.0)
        self.assertEqual(metrics['calculated_acidity'], 5.0)
        self.assertEqual(metrics['calculated_bitterness'], 2.0)
        self.assertEqual(metrics['combined_notes'], ['blackcurrant', 'citrus'])

    def test_multi_base_metrics(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Coffee A',
                        'ingredient_type': 'COFFEE_BEAN',
                        'body_intensity': 4.0,
                        'acidity_score': 2.0,
                        'bitterness_score': 3.0,
                        'flavor_notes': ['chocolate'],
                        'ratio': 1.0
                    },
                    {
                        'name': 'Coffee B',
                        'ingredient_type': 'COFFEE_BEAN',
                        'body_intensity': 2.0,
                        'acidity_score': 4.0,
                        'bitterness_score': 3.0,
                        'flavor_notes': ['floral'],
                        'ratio': 3.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        metrics = data['aggregate_base_metrics']
        # Weighted body = (1*4 + 3*2) / 4 = 2.5
        # Weighted acidity = (1*2 + 3*4) / 4 = 3.5
        # Weighted bitterness = (1*3 + 3*3) / 4 = 3.0
        self.assertEqual(metrics['calculated_body'], 2.5)
        self.assertEqual(metrics['calculated_acidity'], 3.5)
        self.assertEqual(metrics['calculated_bitterness'], 3.0)
        self.assertEqual(metrics['combined_notes'], ['chocolate', 'floral'])

    def test_body_dilution_dairy_penalty(self) -> None:
        # Low body (2.5) triggers body dilution -> dairy threshold penalized by 10%
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 10.0,
                'ingredients': [
                    {
                        'name': 'Light Blend',
                        'ingredient_type': 'COFFEE_BEAN',
                        'body_intensity': 2.5,
                        'amount': 18.0
                    },
                    {
                        'name': 'Oat Milk',
                        'ingredient_type': 'DAIRY',
                        'amount': 5.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Warning", data['recipe_validation'])
        # Hot coffee (espresso base default): budget 10.0oz
        # Espresso base = 1.8oz (2 shots at 0.9oz for 10oz size)
        # Modifiers = 0.0oz
        # Dairy volume = 10.0 - 1.8 - 0.0 = 8.2oz
        self.assertEqual(data['ingredients']['dairy_or_filler']['volume_oz'], 8.2)

    def test_flavor_clashing_and_renaming(self) -> None:
        # Earthy + Citrus clashing
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Coffee A',
                        'ingredient_type': 'COFFEE_BEAN',
                        'flavor_notes': ['earthy'],
                        'amount': 18.0
                    },
                    {
                        'name': 'Coffee B',
                        'ingredient_type': 'COFFEE_BEAN',
                        'flavor_notes': ['citrus'],
                        'amount': 18.0
                    },
                    {
                        'name': 'Caramel Sauce',
                        'ingredient_type': 'ADDITIVE',
                        'amount': 1.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Warning", data['recipe_validation'])
        self.assertIn("High-acidity blend may clash", data['recipe_validation'])
        # Carriage check: caramel modifier renamed to "Vanilla Syrup (Dominant)" or neutral equivalent
        mods = data['ingredients']['modifiers']
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]['name'], "Vanilla Syrup (Dominant)")

    def test_pure_espresso_short_milk_budget(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Pure Espresso / Short Milk',
                'cup_size_oz': 8.0,
                'ingredients': [
                    {
                        'name': 'Espresso Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'body_intensity': 4.5,
                        'amount': 18.0
                    },
                    {
                        'name': 'Whole Milk',
                        'ingredient_type': 'DAIRY',
                        'amount': 4.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['ice_volume_oz'], 0.0)
        self.assertEqual(data['liquid_budget_oz'], 8.0)
        # Short milk with dairy (espresso base):
        # Coffee base volume = 1 shot * 0.9 = 0.9oz
        # Dairy volume = 8.0 - 0.9 = 7.1oz
        self.assertEqual(data['ingredients']['coffee_base_mix'][0]['volume_oz'], 0.9)
        self.assertEqual(data['ingredients']['dairy_or_filler']['volume_oz'], 7.1)

    def test_iced_coffee_espresso_budget_and_thermal_dilution(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Iced Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Espresso Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'body_intensity': 4.0,
                        'amount': 18.0
                    },
                    {
                        'name': 'Whole Milk',
                        'ingredient_type': 'DAIRY'
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Iced Coffee: 40% ice, 60% liquid
        self.assertEqual(data['ice_volume_oz'], 4.8)
        self.assertEqual(data['liquid_budget_oz'], 7.2)
        # Espresso base: 12oz size maps directly to 2 shots * 0.9 = 1.8oz
        self.assertEqual(data['ingredients']['coffee_base_mix'][0]['volume_oz'], 1.8)
        # Secondary liquid before melt-tax dilution: 7.2 - 1.8 = 5.4oz
        # Melt-tax dilution: 5.4 * 0.9 = 4.86oz
        self.assertEqual(data['ingredients']['dairy_or_filler']['volume_oz'], 4.86)
        
        # Verify Ice Melt Water is in base_modifiers
        base_mods = data['ingredients']['base_modifiers']
        self.assertEqual(len(base_mods), 1)
        self.assertEqual(base_mods[0]['name'], "Ice Melt Water")
        self.assertEqual(base_mods[0]['volume_oz'], 0.54)

    def test_hot_coffee_standard_brew_budget(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 16.0,
                'ingredients': [
                    {
                        'name': 'Drip Blend',
                        'ingredient_type': 'COFFEE_BEAN',
                        'coffee_base_type': 'standard_brew',
                        'amount': 18.0,
                        'body_intensity': 4.0
                    },
                    {
                        'name': 'Whole Milk',
                        'ingredient_type': 'DAIRY'
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['ice_volume_oz'], 0.0)
        self.assertEqual(data['liquid_budget_oz'], 16.0)
        # Standard Brew: 70% of total cup size (16oz) = 11.2oz
        self.assertEqual(data['ingredients']['coffee_base']['volume_oz'], 11.2)
        self.assertEqual(data['ingredients']['coffee_base_mix'][0]['volume_oz'], 11.2)
        # Secondary liquid: 16.0 - 11.2 = 4.8oz
        self.assertEqual(data['ingredients']['payload_filler']['volume_oz'], 4.8)
        self.assertEqual(data['ingredients']['dairy_or_filler']['volume_oz'], 4.8)

    def test_iced_coffee_standard_brew_budget(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Iced Coffee',
                'cup_size_oz': 10.0,
                'ingredients': [
                    {
                        'name': 'Brew Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'coffee_base_type': 'standard_brew',
                        'amount': 18.0,
                        'body_intensity': 4.0
                    },
                    {
                        'name': 'Oat Milk',
                        'ingredient_type': 'DAIRY'
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Iced Coffee: 40% ice = 4.0oz, 60% liquid = 6.0oz
        self.assertEqual(data['ice_volume_oz'], 4.0)
        self.assertEqual(data['liquid_budget_oz'], 6.0)
        # Standard Brew: 70% of liquid budget (6oz) = 4.2oz
        self.assertEqual(data['ingredients']['coffee_base']['volume_oz'], 4.2)
        self.assertEqual(data['ingredients']['coffee_base_mix'][0]['volume_oz'], 4.2)
        # Secondary liquid: 6.0 - 4.2 = 1.8oz
        self.assertEqual(data['ingredients']['payload_filler']['volume_oz'], 1.8)
        self.assertEqual(data['ingredients']['dairy_or_filler']['volume_oz'], 1.8)

    def test_modifier_hierarchy(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Dark Roast',
                        'ingredient_type': 'COFFEE_BEAN',
                        'flavor_notes': ['chocolate'],
                        'amount': 18.0
                    },
                    {
                        'name': 'Caramel Syrup',
                        'ingredient_type': 'ADDITIVE',
                        'amount': 1.0
                    },
                    {
                        'name': 'Strawberry Syrup',
                        'ingredient_type': 'ADDITIVE',
                        'amount': 0.5
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        mods = data['ingredients']['modifiers']
        # Total modifier budget: 1.0 + 0.5 = 1.5oz.
        # Over 1 modifier cap: reduced to 10% of liquid budget (12.0 * 0.10 = 1.2oz).
        # Caramel Syrup matches Dark Roast (chocolate) perfectly -> Dominant (60% of 1.2 = 0.72oz)
        # Strawberry Syrup is Accent (40% of 1.2 = 0.48oz)
        caramel_mod = next(m for m in mods if "Caramel" in m['name'])
        strawberry_mod = next(m for m in mods if "Strawberry" in m['name'])
        self.assertIn("Dominant", caramel_mod['name'])
        self.assertIn("Accent", strawberry_mod['name'])
        self.assertEqual(caramel_mod['volume_oz'], 0.72)
        self.assertEqual(strawberry_mod['volume_oz'], 0.48)

    def test_hot_coffee_espresso_water_dilution(self) -> None:
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'espresso_hot_mode': 'water',
                'americano_style': True,
                'ingredients': [
                    {
                        'name': 'Espresso Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'amount': 18.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # 12oz cup size = 2 shots = 1.8oz espresso base
        self.assertEqual(data['hot_water_volume_oz'], 1.8)
        base_mix = data['ingredients']['coffee_base_mix']
        self.assertEqual(len(base_mix), 2)
        bean_part = next(c for c in base_mix if c['name'] == 'Espresso Bean')
        water_part = next(c for c in base_mix if c['name'] == 'Hot Water')
        self.assertEqual(bean_part['volume_oz'], 1.8)
        self.assertEqual(water_part['volume_oz'], 1.8)

    def test_cold_sugar_tax_modifier_cap_expansion(self) -> None:
        # Iced coffee should expand cap by absolute +2% of liquid budget.
        # Target cup: 10.0oz. Liquid budget = 6.0oz.
        # Single modifier: default cap 15% -> expanded to 17% (6.0 * 0.17 = 1.02oz).
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Iced Coffee',
                'cup_size_oz': 10.0,
                'ingredients': [
                    {
                        'name': 'Drip Blend',
                        'ingredient_type': 'COFFEE_BEAN',
                        'coffee_base_type': 'standard_brew',
                        'amount': 18.0
                    },
                    {
                        'name': 'Vanilla Syrup',
                        'ingredient_type': 'ADDITIVE',
                        'amount': 2.0  # exceeding cap
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        mods = data['ingredients']['modifiers']
        self.assertEqual(mods[0]['volume_oz'], 1.02)

    def test_viscosity_protection_warning(self) -> None:
        # Coffee bitterness >= 4 and all modifiers are syrups -> warning.
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Standard Brew Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Bitter Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'bitterness_score': 4,
                        'amount': 18.0
                    },
                    {
                        'name': 'Vanilla Syrup',
                        'ingredient_type': 'ADDITIVE',
                        'amount': 1.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Warning", data['recipe_validation'])
        self.assertIn("watery mouthfeel", data['recipe_validation'])

    def test_fat_buffer_sensory_warning(self) -> None:
        # Bitterness >= 4 and low-fat payload (skim milk = 1) -> warning.
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Bitter Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'bitterness_score': 4,
                        'amount': 18.0
                    },
                    {
                        'name': 'Skim Milk',
                        'ingredient_type': 'DAIRY',
                        'fat_content_score': 1
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Warning", data['recipe_validation'])
        self.assertIn("properly mask coffee bitterness", data['recipe_validation'])

    def test_ph_curdling_protection_failure(self) -> None:
        # Hot drink + Dairy payload + high acidity (acidity >= 4) -> Fail curdling risk.
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Acidic Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'acidity_score': 4,
                        'amount': 18.0
                    },
                    {
                        'name': 'Whole Milk',
                        'ingredient_type': 'DAIRY'
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Fail", data['recipe_validation'])
        self.assertIn("milk curdling risk", data['recipe_validation'])

    def test_preparation_steps_solubility(self) -> None:
        # Verify preparation steps are returned
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Hot Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Espresso Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'amount': 18.0
                    },
                    {
                        'name': 'Cocoa Powder',
                        'ingredient_type': 'ADDITIVE',
                        'is_dry': True,
                        'amount': 10.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        steps = data['preparation_steps']
        self.assertEqual(len(steps), 3)
        self.assertIn("Step 1", steps[0])
        self.assertIn("Step 2", steps[1])
        self.assertIn("agitate and dissolve the powder", steps[1])
        self.assertIn("Step 3", steps[2])

    def test_autonomic_mouthfeel_correction_protocol(self) -> None:
        # Bitter base (bitterness_score = 5) + thin syrup (Vanilla Syrup, no 'sauce') + Whole Milk
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Iced Coffee',
                'cup_size_oz': 12.0,
                'ingredients': [
                    {
                        'name': 'Dark Bitter Roast',
                        'ingredient_type': 'COFFEE_BEAN',
                        'body_intensity': 3.0,
                        'acidity_score': 2.0,
                        'bitterness_score': 5.0,
                        'flavor_notes': ['smoky', 'charred'],
                        'amount': 18.0
                    },
                    {
                        'name': 'Vanilla Syrup',
                        'ingredient_type': 'ADDITIVE',
                        'sweetness_score': 4.0,
                        'amount': 15.0
                    },
                    {
                        'name': 'Whole Milk',
                        'ingredient_type': 'DAIRY',
                        'amount': 100.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Validation should be clean / clear of thin or low-fat warnings
        self.assertNotIn("watery mouthfeel", data['recipe_validation'])
        self.assertNotIn("Low-fat payload", data['recipe_validation'])
        
        # Check payload_filler properties
        pf = data['ingredients']['payload_filler']
        self.assertTrue(pf.get('is_corrected'))
        self.assertEqual(pf.get('primary_name'), 'Whole Milk')
        self.assertEqual(pf.get('texturizer_name'), 'Heavy Cream')
        
        # Check volumetric preservation: primary + texturizer = total volume
        total_vol = pf.get('volume_oz')
        pri_vol = pf.get('primary_volume_oz')
        tex_vol = pf.get('texturizer_volume_oz')
        self.assertAlmostEqual(pri_vol + tex_vol, total_vol, places=2)
        self.assertAlmostEqual(pri_vol, total_vol * 0.8, places=2)
        self.assertAlmostEqual(tex_vol, total_vol * 0.2, places=2)

    def test_manual_texturizer_role_collision_override(self) -> None:
        # Iced 20oz Espresso (12oz budget)
        # Espresso Bean at idx 0 (COFFEE_BEAN)
        # Whole Milk at idx 1 (DAIRY) -> Payload
        # Heavy Cream at idx 2 (DAIRY) -> Accent/Deep Accent (processed as modifier)
        # Vanilla Syrup at idx 3 (ADDITIVE)
        # Mint Syrup at idx 4 (ADDITIVE)
        response = self.client.post(
            reverse('coffee_chemistry_api'),
            data=json.dumps({
                'drink_category': 'Iced Coffee',
                'cup_size_oz': 20.0,
                'espresso_hot_mode': 'shots',
                'americano_style': False,
                'ingredients': [
                    {
                        'id': 101,
                        'name': 'Espresso Bean',
                        'ingredient_type': 'COFFEE_BEAN',
                        'amount': 36.0,
                        'body_intensity': 4.0
                    },
                    {
                        'id': 102,
                        'name': 'Whole Milk',
                        'ingredient_type': 'DAIRY',
                        'amount': 150.0
                    },
                    {
                        'id': 103,
                        'name': 'Heavy Cream',
                        'ingredient_type': 'DAIRY',
                        'amount': 60.0
                    },
                    {
                        'id': 104,
                        'name': 'Vanilla Syrup',
                        'ingredient_type': 'ADDITIVE',
                        'amount': 18.0
                    },
                    {
                        'id': 105,
                        'name': 'Mint Syrup',
                        'ingredient_type': 'ADDITIVE',
                        'amount': 12.0
                    }
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify warnings are suppressed
        self.assertEqual(data['recipe_validation'], 'Pass')
        
        # Verify split is NOT active (is_corrected is False)
        pf = data['ingredients']['payload_filler']
        self.assertFalse(pf.get('is_corrected', False))
        
        # Verify Heavy Cream is returned as a modifier in flavor_modifiers, not split in pf
        flavor_mods = data['ingredients']['flavor_modifiers']
        heavy_cream_mod = next((m for m in flavor_mods if 'Heavy Cream' in m['name']), None)
        self.assertIsNotNone(heavy_cream_mod)
        self.assertEqual(heavy_cream_mod['id'], 103)
        
        # Verify liquid budget totals strictly to 12.0 oz
        coffee_vol = data['ingredients']['coffee_base']['volume_oz']  # 4 shots = 3.6oz
        hot_water_vol = data.get('hot_water_volume_oz', 0.0)
        ice_melt_vol = next((m['volume_oz'] for m in data['ingredients']['base_modifiers'] if m['name'] == 'Ice Melt Water'), 0.0)
        
        # Whole milk volume
        whole_milk_vol = data['ingredients']['payload_filler']['volume_oz']
        
        # Sum of flavor modifiers
        mods_total_vol = sum(m['volume_oz'] for m in flavor_mods)
        
        total_vol = coffee_vol + hot_water_vol + ice_melt_vol + whole_milk_vol + mods_total_vol
        self.assertAlmostEqual(total_vol, 12.0, places=2)


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

    @patch('requests.request')
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
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Cherry Blast", "reason": "Adds flavor", "resonance": 95, "amount": 100.0}]}'}}]
        }
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
        self.assertIn("Exclude these previously suggested items: Vanilla Twist.", user_msg)

        # 2. Exclude all candidates: Cherry Blast and Vanilla Twist
        # It should fall back, meaning Vanilla Twist and Cherry Blast are still in the context.
        mock_response_fallback = MagicMock()
        mock_response_fallback.status_code = 200
        mock_response_fallback.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"name": "Vanilla Twist", "reason": "Adds flavor", "resonance": 95, "amount": 100.0}]}'}}]
        }
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


class SodaChemistryEngineTest(TestCase):
    """Test cases for the V2.5 Soda Synthesis chemistry calculation rules."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="soda_tech", password="secure_password_123")
        self.client.login(username="soda_tech", password="secure_password_123")

    def test_soda_chemistry_craft_default(self) -> None:
        # Test 1.0L scale default CRAFT budget = 120ml
        response = self.client.post(
            reverse('soda_chemistry_api'),
            data=json.dumps({
                'sweetness_style': 'CRAFT',
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Watermelon Syrup', 'type': 'SODA_SYRUP', 'intensity': 2, 'acidity': 2, 'bitterness': 1},
                    {'name': 'Coconut Syrup', 'type': 'SODA_SYRUP', 'intensity': 3, 'acidity': 1, 'bitterness': 1},
                    {'name': 'Ginger Syrup', 'type': 'SODA_SYRUP', 'intensity': 5, 'acidity': 3, 'bitterness': 2}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['recipe_validation'], 'Pass')
        metrics = data['drink_metrics']
        self.assertEqual(metrics['water_volume_ml'], 840.0)
        self.assertEqual(metrics['total_syrup_volume_ml'], 120.0)
        self.assertEqual(metrics['maximum_syrup_limit_ml'], 160.0)
        
        # Check potency allocation (65% / 25% / 10% split)
        modifiers = data['ingredients']['modifiers']
        self.assertEqual(len(modifiers), 3)
        watermelon = next(m for m in modifiers if 'Watermelon' in m['name'])
        coconut = next(m for m in modifiers if 'Coconut' in m['name'])
        ginger = next(m for m in modifiers if 'Ginger' in m['name'])
        self.assertAlmostEqual(watermelon['volume_ml'], 72.0)  # Primary Base: 60% of 120
        self.assertAlmostEqual(coconut['volume_ml'], 39.0)     # Blender: (40% - 7.5%) of 120 = 32.5% of 120
        self.assertAlmostEqual(ginger['volume_ml'], 9.0)       # Accent: 7.5% of 120

        # Check prep steps
        steps = data['preparation_steps']
        self.assertEqual(len(steps), 4)
        self.assertIn("exactly 840ml of cold water", steps[1])

    def test_soda_chemistry_crisp_0_5L(self) -> None:
        # Test 0.5L scale CRISP budget = 105ml / 2 = 52.5ml
        response = self.client.post(
            reverse('soda_chemistry_api'),
            data=json.dumps({
                'sweetness_style': 'CRISP',
                'bottle_scale': 0.5,
                'ingredients': [
                    {'name': 'Peach Syrup', 'type': 'SODA_SYRUP', 'intensity': 2, 'acidity': 2, 'bitterness': 1},
                    {'name': 'Vanilla Syrup', 'type': 'SODA_SYRUP', 'intensity': 3, 'acidity': 1, 'bitterness': 1}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        metrics = data['drink_metrics']
        self.assertEqual(metrics['water_volume_ml'], 420.0)
        self.assertAlmostEqual(metrics['total_syrup_volume_ml'], 52.5)

        # Delicate and blender are present (60% / 40% split)
        modifiers = data['ingredients']['modifiers']
        peach = next(m for m in modifiers if 'Peach' in m['name'])
        vanilla = next(m for m in modifiers if 'Vanilla' in m['name'])
        self.assertAlmostEqual(peach['volume_ml'], 31.5)  # 60% of 52.5 = 31.5
        self.assertAlmostEqual(vanilla['volume_ml'], 21.0)  # 40% of 52.5 = 21.0

        steps = data['preparation_steps']
        self.assertIn("exactly 420ml of cold water", steps[1])

    def test_soda_chemistry_sweetness_penalty(self) -> None:
        # Test sweetness penalty: Lime Syrup has high acidity (acidity_score = 5)
        response = self.client.post(
            reverse('soda_chemistry_api'),
            data=json.dumps({
                'sweetness_style': 'FOUNTAIN',
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Watermelon Syrup', 'type': 'SODA_SYRUP', 'intensity': 2, 'acidity': 2, 'bitterness': 1},
                    {'name': 'Lime Syrup', 'type': 'SODA_SYRUP', 'intensity': 4, 'acidity_score': 5, 'bitterness': 1}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        analysis = data['extraction_analysis']
        # Fountain baseline sweetness is 5.0. Lime is in the accent pool with acidity >= 4, so penalty is applied: 5.0 - 0.5 = 4.5.
        self.assertEqual(analysis['sweetness'], 4.5)

    def test_soda_chemistry_12oz_overflow(self) -> None:
        # Test 12oz Glass scale = 0.355. Water = 840 * 0.355 = 298.2ml. Max syrup = 160 * 0.355 = 56.8ml.
        # sweetness_style = FOUNTAIN (140 * 0.355 = 49.7ml)
        response = self.client.post(
            reverse('soda_chemistry_api'),
            data=json.dumps({
                'sweetness_style': 'FOUNTAIN',
                'bottle_scale': 0.355,
                'ingredients': [
                    {'name': 'Watermelon Syrup', 'type': 'SODA_SYRUP', 'intensity': 2, 'acidity': 2, 'bitterness': 1}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        metrics = data['drink_metrics']
        self.assertEqual(metrics['water_volume_ml'], 298.2)
        self.assertEqual(metrics['total_syrup_volume_ml'], 49.7)
        self.assertEqual(data['recipe_validation'], 'Pass')

    def test_soda_chemistry_primary_flavor_anchor_protocol(self) -> None:
        # Test Primary Flavor Anchor Protocol with designated primary base
        response = self.client.post(
            reverse('soda_chemistry_api'),
            data=json.dumps({
                'sweetness_style': 'CRAFT',
                'bottle_scale': 1.0,
                'ingredients': [
                    {'id': 1, 'name': 'Grapefruit Pink Syrup', 'type': 'SODA_SYRUP', 'intensity': 4, 'acidity': 4, 'bitterness': 1, 'is_primary': True},
                    {'id': 2, 'name': 'Coconut Syrup', 'type': 'SODA_SYRUP', 'intensity': 3, 'acidity': 1, 'bitterness': 1},
                    {'id': 3, 'name': 'Mint Syrup', 'type': 'SODA_SYRUP', 'intensity': 5, 'acidity': 1, 'bitterness': 1},
                    {'id': 4, 'name': 'Lime Syrup', 'type': 'SODA_SYRUP', 'intensity': 4, 'acidity': 4, 'bitterness': 1}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        modifiers = data['ingredients']['modifiers']
        self.assertEqual(len(modifiers), 4)
        
        grapefruit = next(m for m in modifiers if 'Grapefruit' in m['name'])
        coconut = next(m for m in modifiers if 'Coconut' in m['name'])
        mint = next(m for m in modifiers if 'Mint' in m['name'])
        lime = next(m for m in modifiers if 'Lime' in m['name'])
        
        self.assertAlmostEqual(grapefruit['volume_ml'], 72.0)  # 60% of 120ml
        self.assertAlmostEqual(coconut['volume_ml'], 30.0)    # 25% of 120ml
        self.assertAlmostEqual(mint['volume_ml'], 9.0)        # 7.5% of 120ml
        self.assertAlmostEqual(lime['volume_ml'], 9.0)        # 7.5% of 120ml
        self.assertAlmostEqual(data['drink_metrics']['total_syrup_volume_ml'], 120.0)
        
        # Test fallback: no is_primary provided, should default to first flavor (Grapefruit)
        response_fallback = self.client.post(
            reverse('soda_chemistry_api'),
            data=json.dumps({
                'sweetness_style': 'CRAFT',
                'bottle_scale': 1.0,
                'ingredients': [
                    {'id': 1, 'name': 'Grapefruit Pink Syrup', 'type': 'SODA_SYRUP', 'intensity': 4, 'acidity': 4, 'bitterness': 1},
                    {'id': 2, 'name': 'Coconut Syrup', 'type': 'SODA_SYRUP', 'intensity': 3, 'acidity': 1, 'bitterness': 1},
                    {'id': 3, 'name': 'Mint Syrup', 'type': 'SODA_SYRUP', 'intensity': 5, 'acidity': 1, 'bitterness': 1},
                    {'id': 4, 'name': 'Lime Syrup', 'type': 'SODA_SYRUP', 'intensity': 4, 'acidity': 4, 'bitterness': 1}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response_fallback.status_code, 200)
        data_fallback = response_fallback.json()
        modifiers_fallback = data_fallback['ingredients']['modifiers']
        
        grapefruit_fb = next(m for m in modifiers_fallback if 'Grapefruit' in m['name'])
        self.assertAlmostEqual(grapefruit_fb['volume_ml'], 72.0)


class CryoChemistryTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="cryo_tech", password="secure_password_123")
        self.client.login(username="cryo_tech", password="secure_password_123")

    def test_cryo_chemistry_success_default(self) -> None:
        # Test 32oz batch target of 946ml, 13% Brix solving with Water filler (0% sugar).
        response = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Strawberry Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 3, 'amount': 80.0},
                    {'name': 'Vanilla Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 2, 'amount': 40.0},
                    {'name': 'Water', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['recipe_validation'], 'Pass')
        metrics = data['drink_metrics']
        self.assertEqual(metrics['target_volume_ml'], 946.0)
        self.assertAlmostEqual(metrics['achieved_brix'], 13.0, places=1)
        self.assertAlmostEqual(metrics['filler_volume_ml'], 756.8, places=1)
        self.assertAlmostEqual(metrics['total_syrup_volume_ml'], 189.2, places=1)

    def test_cryo_chemistry_juice_filler(self) -> None:
        # Test 32oz batch (946ml) with Juice filler (10% sugar).
        response = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Strawberry Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 3, 'amount': 80.0},
                    {'name': 'Vanilla Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 2, 'amount': 40.0},
                    {'name': 'Apple Juice', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['recipe_validation'], 'Pass')
        metrics = data['drink_metrics']
        self.assertEqual(metrics['target_volume_ml'], 946.0)
        self.assertAlmostEqual(metrics['achieved_brix'], 13.0, places=1)
        self.assertAlmostEqual(metrics['filler_volume_ml'], 894.4, places=1)
        self.assertAlmostEqual(metrics['total_syrup_volume_ml'], 51.6, places=1)

    def test_cryo_chemistry_coconut_water_filler(self) -> None:
        # Test 32oz batch (946ml) with Coconut Water filler (3% sugar).
        # Target syrup volume should be ~152.6ml, filler volume ~793.4ml.
        response = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Strawberry Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 3, 'amount': 80.0},
                    {'name': 'Vanilla Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 2, 'amount': 40.0},
                    {'name': 'Coconut Water', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['recipe_validation'], 'Pass')
        metrics = data['drink_metrics']
        self.assertEqual(metrics['target_volume_ml'], 946.0)
        self.assertAlmostEqual(metrics['achieved_brix'], 13.0, places=1)
        self.assertAlmostEqual(metrics['filler_volume_ml'], 793.4, places=1)
        self.assertAlmostEqual(metrics['total_syrup_volume_ml'], 152.6, places=1)

    def test_cryo_chemistry_menthol_cap(self) -> None:
        # Test 32oz batch (946ml) with Mint ingredient.
        # Menthol limit is 3% of 946ml = 28.38ml.
        response = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Peppermint Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 3, 'amount': 80.0},
                    {'name': 'Water', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Fail: Sugar density check failed", data['recipe_validation'])
        self.assertAlmostEqual(data['ingredients']['modifiers'][0]['volume_ml'], 28.4, places=1)

    def test_cryo_chemistry_sweetness_tax(self) -> None:
        # Modifier with sweetness >= 4 (Strawberry Syrup has sweetness=4).
        response = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Strawberry Syrup', 'type': 'SODA_SYRUP', 'sweetness': 4, 'intensity': 3, 'amount': 80.0},
                    {'name': 'Vanilla Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 2, 'amount': 40.0},
                    {'name': 'Water', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['recipe_validation'], 'Pass')
        mods = data['ingredients']['modifiers']
        strawberry = next(m for m in mods if 'Strawberry' in m['name'])
        vanilla = next(m for m in mods if 'Vanilla' in m['name'])
        self.assertAlmostEqual(strawberry['volume_ml'], 128.2, places=1)
        self.assertAlmostEqual(vanilla['volume_ml'], 61.0, places=1)

    def test_cryo_chemistry_carbonation_ban(self) -> None:
        # Sparkling Water in slushie ingredients should trigger validation failure
        response = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Strawberry Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 3, 'amount': 80.0},
                    {'name': 'Sparkling Water', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Fail: Carbonation Hard-Ban", data['recipe_validation'])

    def test_cryo_chemistry_ginger_beer(self) -> None:
        # Ginger Beer should be treated as a flavor syrup reagent and bypass carbonation ban
        response = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'name': 'Ginger Beer Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 3, 'amount': 80.0},
                    {'name': 'Water', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['recipe_validation'], 'Pass')

    def test_cryo_chemistry_solitary_flavor_scaling_and_recalculation(self) -> None:
        # 1. Test Solitary Flavor Predictive Scaling (no user override)
        # For a 32oz batch target of 946ml, water filler, Pineapple Syrup (sweetness 4, sugar 0.65).
        # Should solve to exactly 189.2ml (13% Brix).
        response = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'id': 1, 'name': 'Pineapple Syrup', 'type': 'SODA_SYRUP', 'sweetness': 4, 'intensity': 3, 'amount': 0.0, 'isUserOverridden': False},
                    {'id': 2, 'name': 'Water', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['recipe_validation'], 'Pass')
        mods = data['ingredients']['modifiers']
        self.assertEqual(len(mods), 1)
        self.assertAlmostEqual(mods[0]['volume_ml'], 189.2, places=1)

        # 2. Test Dynamic Recalculation when a second flavor is added
        # First modifier should down-scale back to 80ml base, second to 40ml base, and solve.
        response2 = self.client.post(
            reverse('cryo_chemistry_api'),
            data=json.dumps({
                'bottle_scale': 1.0,
                'ingredients': [
                    {'id': 1, 'name': 'Pineapple Syrup', 'type': 'SODA_SYRUP', 'sweetness': 4, 'intensity': 3, 'amount': 0.0, 'isUserOverridden': False},
                    {'id': 3, 'name': 'Strawberry Syrup', 'type': 'SODA_SYRUP', 'sweetness': 3, 'intensity': 3, 'amount': 0.0, 'isUserOverridden': False},
                    {'id': 2, 'name': 'Water', 'type': 'OTHER', 'is_ready_to_drink': True}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2['recipe_validation'], 'Pass')
        mods2 = data2['ingredients']['modifiers']
        self.assertEqual(len(mods2), 2)
        # Pineapple Syrup should be significantly down-scaled from 189.2ml.
        self.assertLess(mods2[0]['volume_ml'], 189.2)





