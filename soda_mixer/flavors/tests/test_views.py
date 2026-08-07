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

class BeverageLabViewsTest(TestCase):
    """Integration tests for application views and AJAX endpoints."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.staff_user = User.objects.create_user(username="director", password="secure_password_123", is_staff=True)
        
        self.ing = Ingredient.objects.create(
            name="Club Soda", ingredient_type="OTHER", category="sweet", intensity=1, sweetness=1, acidity=1, bitterness=1, complexity=1, compatible_systems="SODA,COFFEE", is_in_inventory=True
        )
        self.coffee_bean = Ingredient.objects.create(
            name="Espresso Beans", brand="Monin", ingredient_type="COFFEE_BEAN", category="coffee", physical_state="SOLID_EXTRACTABLE", mixology_function="VOLUME_BASE", intensity=5, sweetness=1, acidity=2, bitterness=4, complexity=4, compatible_systems="COFFEE", is_in_inventory=True
        )
        self.recipe = Recipe.objects.create(name="Simple Soda", drink_type="SODA")
        self.ri = RecipeIngredient.objects.create(recipe=self.recipe, ingredient=self.ing, amount=200.0)

    def test_unauthenticated_user_redirect(self) -> None:
        # LaboratoryAccessMiddleware redirects unauthenticated requests
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_authenticated_user_home(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.get(reverse('dashboard'))
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
        from ..models import MixHistoryIngredient, RecipeIngredient
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
        from ..models import MixHistoryIngredient
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

    @patch('requests.post')
    def test_ai_suggest_api_force_type(self, mock_request: MagicMock) -> None:
        """Verify that when forcing a specific category, the LLM is instructed and standard fallback behaves as expected."""
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
        mock_response.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "{\\\"suggestions\\\": [{\\\"name\\\": \\\"Whole Milk\\\", \\\"reason\\\": \\\"Adds body\\\", \\\"resonance\\\": 90, \\\"amount\\\": 50.0}], \\\"rebalancing\\\": {}, \\\"seal_recommended\\\": false, \\\"seal_resonance\\\": 0, \\\"reasoning\\\": \\\"Test reason\\\"}"}}]}',
            b'data: [DONE]'
        ]
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

        from ..ai_service import AIAssistant
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

        from ..ai_service import AIAssistant
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
        
        from ..views.ai import ai_bulk_analyze_task
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
        
        from ..views.ai import ai_bulk_analyze_task
        ai_bulk_analyze_task(update_progress=lambda *args, **kwargs: None)
        
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.base_suitability, 1.5)
        self.assertEqual(self.ing.accent_suitability, 4.2)
        self.assertEqual(self.ing.ai_notes, "Custom base suitability notes")

    def test_home_page_renders_empty_mode_message_element(self) -> None:
        self.client.login(username="lab_tech", password="secure_password_123")
        response = self.client.get(reverse('lab_view', args=['soda', 'manual']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="emptyModeMessage"')
        self.assertContains(response, 'id="stepHeader"')

    @patch('requests.post')
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
        mock_response.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "{\\\"suggestions\\\": [{\\\"name\\\": \\\"Espresso Beans (Monin)\\\", \\\"reason\\\": \\\"Strong base\\\", \\\"resonance\\\": 95, \\\"amount\\\": 18.0}], \\\"rebalancing\\\": {\\\"Espresso Beans (Monin)\\\": 10.0}, \\\"seal_recommended\\\": false, \\\"seal_resonance\\\": 0, \\\"reasoning\\\": \\\"Test reason\\\"}"}}]}',
            b'data: [DONE]'
        ]
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
        chunks = [chunk.strip() for chunk in content.split('\n\n') if chunk.strip()]

        # Parse messages
        progress_msgs = []
        success_data = None
        for chunk in chunks:
            for line in chunk.split('\n'):
                if line.startswith('data:'):
                    data_str = line.replace('data:', '').strip()
                    if not data_str: continue
                    try:
                        parsed = json.loads(data_str)
                        if parsed.get('status') == 'progress':
                            progress_msgs.append(parsed.get('message'))
                        elif parsed.get('status') == 'success':
                            success_data = parsed
                    except ValueError:
                        pass

        # Assert progress messages are sent in order
        self.assertIn("Scanning current compound registry...", progress_msgs)
        self.assertIn("Locating matching flavor affinity groups...", progress_msgs)
        self.assertIn("Querying Mixology Oracle...", progress_msgs)

        # Assert final success payload contains suggestions
        self.assertIsNotNone(success_data)
        self.assertEqual(success_data['status'], 'success')
        self.assertEqual(success_data['suggestions'][0]['name'], 'Espresso Beans')

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

