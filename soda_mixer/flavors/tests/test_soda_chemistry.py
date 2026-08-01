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
