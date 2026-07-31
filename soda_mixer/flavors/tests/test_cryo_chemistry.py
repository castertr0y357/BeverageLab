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

