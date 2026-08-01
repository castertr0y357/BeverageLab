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
        from ..views.ai import get_display_name, get_multibrand_names_in_inventory
        
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
            is_in_inventory=True,
            compatible_systems="COFFEE"
        )
        self.creamer = Ingredient.objects.create(
            name="Whole Milk",
            brand="Local Dairy",
            ingredient_type="DAIRY",
            category="sweet",
            is_in_inventory=True,
            compatible_systems="COFFEE"
        )
        self.syrup = Ingredient.objects.create(
            name="Caramel Syrup",
            brand="Torani",
            ingredient_type="OTHER",
            category="sweet",
            is_in_inventory=True,
            compatible_systems="COFFEE"
        )

    def test_sanitize_coffee_amount(self) -> None:
        from ..views.ai import sanitize_coffee_amount
        self.assertEqual(sanitize_coffee_amount(self.bean, 100.0), 18.0)
        self.assertEqual(sanitize_coffee_amount(self.creamer, 50.0), 50.0)
        self.assertEqual(sanitize_coffee_amount(self.syrup, 25.0), 15.0)
        sugar = Ingredient.objects.create(
            name="Honey",
            ingredient_type="ADDITIVE",
            category="sweet",
            is_in_inventory=True,
            compatible_systems="COFFEE"
        )
        self.assertEqual(sanitize_coffee_amount(sugar, 25.0), 15.0)

    @patch('soda_mixer.flavors.ai_service.AIAssistant.suggest_autonomous_stream')
    def test_ai_suggest_api_coffee_sanitization(self, mock_suggest_stream: MagicMock) -> None:
        mock_suggest_stream.return_value = [
            {
                "type": "suggestion",
                "data": {
                    "name": "Whole Milk (Local Dairy)",
                    "reason": "Creams it up",
                    "resonance": 95,
                    "amount": 100.0,
                    "profile": {"intensity": 2, "sweetness": 2, "acidity": 1, "bitterness": 1, "complexity": 1}
                }
            },
            {
                "type": "complete",
                "data": {
                    "rebalancing": {
                        "Espresso Beans (Monin)": 100.0
                    },
                    "seal_recommended": False,
                    "seal_resonance": 80,
                    "reasoning": "Test suggestion rebalancing."
                }
            }
        ]

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

    @patch('soda_mixer.flavors.ai_service.AIAssistant.suggest_autonomous_stream')
    def test_ai_suggest_api_coffee_rebalancing_unmatched_key_dropped(self, mock_suggest_stream: MagicMock) -> None:
        """Unrecognized rebalancing keys must be dropped to prevent raw AI values leaking."""
        mock_suggest_stream.return_value = [
            {
                "type": "suggestion",
                "data": {
                    "name": "Whole Milk (Local Dairy)",
                    "reason": "Creams it up",
                    "resonance": 95,
                    "amount": 100.0,
                    "profile": {"intensity": 2, "sweetness": 2, "acidity": 1, "bitterness": 1, "complexity": 1}
                }
            },
            {
                "type": "complete",
                "data": {
                    "rebalancing": {
                        "Espresso Roast Supreme": 100.0,
                        "Unknown Bean Variety": 50.0
                    },
                    "seal_recommended": False,
                    "seal_resonance": 80,
                    "reasoning": "Test unmatched rebalancing keys."
                }
            }
        ]

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

    @patch('soda_mixer.flavors.ai_service.AIAssistant.suggest_autonomous_stream')
    def test_ai_suggest_api_force_type_filtering(self, mock_suggest_stream: MagicMock) -> None:
        """Verify that suggestions not matching the force_type are programmatically filtered out."""
        Ingredient.objects.create(
            name="Vanilla Syrup",
            brand="Monin",
            ingredient_type="ADDITIVE",
            category="sweet",
            is_in_inventory=True
        )

        mock_suggest_stream.return_value = [
            {
                "type": "suggestion",
                "data": {
                    "name": "Whole Milk (Local Dairy)",
                    "reason": "Creams it up",
                    "resonance": 95,
                    "amount": 50.0,
                    "profile": {"intensity": 2, "sweetness": 2, "acidity": 1, "bitterness": 1, "complexity": 1}
                }
            },
            {
                "type": "suggestion",
                "data": {
                    "name": "Vanilla Syrup (Monin)",
                    "reason": "Adds vanilla sweetness",
                    "resonance": 90,
                    "amount": 15.0,
                    "profile": {"intensity": 3, "sweetness": 4, "acidity": 1, "bitterness": 1, "complexity": 2}
                }
            },
            {
                "type": "complete",
                "data": {
                    "rebalancing": {},
                    "seal_recommended": False,
                    "seal_resonance": 80,
                    "reasoning": "Test force_type filtering."
                }
            }
        ]

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

    @patch('soda_mixer.flavors.ai_service.AIAssistant.suggest_autonomous_stream')
    def test_ai_suggest_api_coffee_bean_split_rebalancing(self, mock_suggest_stream: MagicMock) -> None:
        """Verify that when multiple coffee beans are returned in rebalancing, they scale to sum to 18.0g."""
        another_bean = Ingredient.objects.create(
            name="Ethiopian Beans",
            brand="Monin",
            ingredient_type="COFFEE_BEAN",
            category="coffee",
            is_in_inventory=True,
            compatible_systems="COFFEE"
        )
        
        mock_suggest_stream.return_value = [
            {
                "type": "suggestion",
                "data": {
                    "name": "Whole Milk (Local Dairy)",
                    "reason": "Creams it up",
                    "resonance": 95,
                    "amount": 100.0,
                    "profile": {"intensity": 2, "sweetness": 2, "acidity": 1, "bitterness": 1, "complexity": 1}
                }
            },
            {
                "type": "complete",
                "data": {
                    "rebalancing": {
                        "Espresso Beans (Monin)": 10.0,
                        "Ethiopian Beans (Monin)": 10.0
                    },
                    "seal_recommended": False,
                    "seal_resonance": 80,
                    "reasoning": "Test split bean rebalancing."
                }
            }
        ]

        response = self.client.post(
            reverse('ai_suggest_api'),
            data=json.dumps({
                'ingredients': ['Espresso Beans (Monin)', 'Ethiopian Beans (Monin)'],
                'drink_type': 'COFFEE',
                'mode': 'standard'
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = _get_sse_data(response)
        
        # Verify the two coffee beans sum to 18.0g (9.0g each)
        self.assertEqual(data['rebalancing']['Espresso Beans (Monin)'], 9.0)
        self.assertEqual(data['rebalancing']['Ethiopian Beans (Monin)'], 9.0)


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

    @patch('soda_mixer.flavors.ai_service.AIAssistant.check_status')
    def test_random_pairing_api_coffee_secondary_dairy(self, mock_status: MagicMock) -> None:
        """Verify that Coffee Lab random pairing selects DAIRY as the secondary ingredient (index 1)."""
        mock_status.return_value = 'unconfigured'
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
