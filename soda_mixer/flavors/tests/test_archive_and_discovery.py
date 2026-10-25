import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from soda_mixer.flavors.models import Recipe, RecipeIngredient, Ingredient, MixHistory, MixHistoryIngredient

User = get_user_model()

class ArchivePromotionScrubbingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.client.login(username="lab_tech", password="secure_password_123")
        self.ing1 = Ingredient.objects.create(
            name="Lemon Syrup",
            ingredient_type="SODA_SYRUP",
            category="citrus",
            is_in_inventory=True
        )
        self.ing2 = Ingredient.objects.create(
            name="Vanilla Syrup",
            ingredient_type="ADDITIVE",
            category="sweet",
            is_in_inventory=True
        )

    def test_save_mix_to_history_and_subsequent_update(self):
        # 1. Initial auto-archive save
        payload = {
            'drink_type': 'SODA',
            'ingredients': [
                {'id': self.ing1.id, 'amount': 25.0, 'is_primary': True},
                {'id': self.ing2.id, 'amount': 10.0, 'is_primary': False}
            ]
        }
        resp = self.client.post(reverse('save_mix_to_history_api'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'saved')
        mix_id = data['mix_id']

        mix = MixHistory.objects.get(uuid=mix_id)
        self.assertEqual(mix.drink_type, 'SODA')
        self.assertEqual(mix.mix_ingredients.count(), 2)

        # 2. Update with generated AI notes and formula name
        update_payload = {
            'mix_id': mix_id,
            'name': 'Citrus Velvet Soda',
            'mixologist_notes': 'A bright citrus punch balanced by smooth vanilla undertones.',
            'profile_description': 'Refreshing and crisp.',
            'sweetness_style': 'CRISP',
            'bottle_scale': 0.5
        }
        resp_update = self.client.post(reverse('save_mix_to_history_api'), data=json.dumps(update_payload), content_type='application/json')
        self.assertEqual(resp_update.status_code, 200)

        mix.refresh_from_db()
        self.assertEqual(mix.name, 'Citrus Velvet Soda')
        self.assertEqual(mix.mixologist_notes, 'A bright citrus punch balanced by smooth vanilla undertones.')
        self.assertEqual(mix.sweetness_style, 'CRISP')
        self.assertEqual(mix.bottle_scale, 0.5)

    def test_create_recipe_scrubs_source_mix(self):
        # Create a mix history entry
        mix = MixHistory.objects.create(drink_type='SODA', name='To Be Saved')
        MixHistoryIngredient.objects.create(mix=mix, ingredient=self.ing1, amount=30.0)

        # Post to create_recipe with source_mix_id
        post_data = {
            'name': 'Saved Soda Recipe',
            'drink_type': 'SODA',
            'source_mix_id': str(mix.uuid),
            f'amount_{self.ing1.id}': 30.0,
            f'notes_{self.ing1.id}': '',
            f'is_primary_{self.ing1.id}': 'true'
        }
        resp = self.client.post(reverse('create_recipe'), post_data)
        self.assertEqual(resp.status_code, 302)

        # MixHistory must be scrubbed
        self.assertFalse(MixHistory.objects.filter(uuid=mix.uuid).exists())
        self.assertTrue(Recipe.objects.filter(name='Saved Soda Recipe').exists())

    def test_promote_api_scrubs_source_mix(self):
        mix = MixHistory.objects.create(drink_type='SODA', name='Promoted From History')
        MixHistoryIngredient.objects.create(mix=mix, ingredient=self.ing1, amount=20.0)

        resp = self.client.post(
            reverse('promote_mix_to_recipe_api', args=[mix.uuid]),
            data=json.dumps({'name': 'Promoted Formula'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MixHistory.objects.filter(uuid=mix.uuid).exists())
        self.assertTrue(Recipe.objects.filter(name='Promoted Formula').exists())


class UnifiedSynopsisAndDiscoveryTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="lab_tech", password="secure_password_123")
        self.client.login(username="lab_tech", password="secure_password_123")
        self.citrus = Ingredient.objects.create(
            name="Lime Cordial",
            ingredient_type="SODA_SYRUP",
            category="citrus",
            is_in_inventory=True
        )
        self.vanilla = Ingredient.objects.create(
            name="Madagascar Vanilla",
            ingredient_type="ADDITIVE",
            category="sweet",
            is_in_inventory=True
        )
        self.recipe = Recipe.objects.create(
            name="Classic Key Lime Soda",
            drink_type="SODA",
            description="Crisp key lime soda.\n\nAI Mixologist Notes:\nBright effervescence."
        )
        RecipeIngredient.objects.create(recipe=self.recipe, ingredient=self.citrus, amount=25.0, is_primary=True)
        RecipeIngredient.objects.create(recipe=self.recipe, ingredient=self.vanilla, amount=10.0, is_primary=False)

    def test_recipe_detail_renders_synopsis_without_submit_area(self):
        url = reverse('recipe_detail', args=[self.recipe.uuid])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'flavors/synopsis.html')
        self.assertContains(resp, 'Classic Key Lime Soda')
        self.assertContains(resp, 'scale12oz')
        self.assertNotContains(resp, 'id="formSubmitArea"')
        self.assertNotContains(resp, 'ARCHIVE SYNTHESIS')

    def test_quick_existing_recipes_api(self):
        # Category citrus matches Lime Cordial in Classic Key Lime Soda
        resp = self.client.get(reverse('quick_existing_recipes_api') + '?lab_mode=SODA&profile=citrus')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertGreaterEqual(data['total_matching'], 1)
        self.assertEqual(data['recipes'][0]['name'], 'Classic Key Lime Soda')

    def test_quick_existing_recipes_excludes_out_of_inventory(self):
        # Set ingredient out of inventory
        self.citrus.is_in_inventory = False
        self.citrus.save()

        resp = self.client.get(reverse('quick_existing_recipes_api') + '?lab_mode=SODA&profile=citrus')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total_matching'], 0)
        self.assertEqual(len(data['recipes']), 0)
