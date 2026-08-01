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

