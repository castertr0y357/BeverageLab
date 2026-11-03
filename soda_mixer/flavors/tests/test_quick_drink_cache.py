import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from soda_mixer.flavors.models import (
    Ingredient, Recipe, RecipeIngredient, MixHistory, MixHistoryIngredient,
    CachedQuickDrink, QuickDrinkCacheConfiguration
)
from soda_mixer.flavors.quick_cache_service import (
    compute_flavor_signature, BUCKET_TARGETS, replenish_quick_drink_cache,
    draw_quick_drinks, ensure_recipe_primary_ingredient, get_recipe_primary_category
)

User = get_user_model()


class QuickDrinkCacheAndUniquenessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="lab_director", email="director@lab.local", password="secure_password_123"
        )
        self.client.login(username="lab_director", password="secure_password_123")

        # Clear any default seeded ingredients and recipes so our test inventory is isolated
        Ingredient.all_objects.all().delete()
        Recipe.all_objects.all().delete()
        CachedQuickDrink.objects.all().delete()

        self.cherry = Ingredient.objects.create(
            name="Cherry", ingredient_type="SODA_SYRUP", category="fruity",
            compatible_systems="SODA,SLUSHIE,COFFEE", is_in_inventory=True
        )
        self.lime = Ingredient.objects.create(
            name="Lime", ingredient_type="SODA_SYRUP", category="citrus",
            compatible_systems="SODA,SLUSHIE", is_in_inventory=True
        )
        self.vanilla = Ingredient.objects.create(
            name="Vanilla", ingredient_type="ADDITIVE", category="sweet",
            compatible_systems="SODA,SLUSHIE,COFFEE", is_in_inventory=True
        )
        self.mango = Ingredient.objects.create(
            name="Mango", ingredient_type="SODA_SYRUP", category="fruity",
            compatible_systems="SODA,SLUSHIE", is_in_inventory=True
        )
        self.mint = Ingredient.objects.create(
            name="Mint", ingredient_type="ADDITIVE", category="herbal",
            compatible_systems="SODA,SLUSHIE,COFFEE", is_in_inventory=True
        )

    def test_anchor_aware_flavor_signature(self):
        """Verify Cherry 60, Lime 20, Vanilla 10 and Cherry 60, Vanilla 20, Lime 10 produce
        the exact same signature, while Lime 60, Vanilla 20, Cherry 10 produces a distinct signature.
        """
        mix_a = [
            {'name': 'Cherry', 'parts': 60.0},
            {'name': 'Lime', 'parts': 20.0},
            {'name': 'Vanilla', 'parts': 10.0},
        ]
        mix_b = [
            {'name': 'Cherry', 'parts': 60.0},
            {'name': 'Vanilla', 'parts': 20.0},
            {'name': 'Lime', 'parts': 10.0},
        ]
        mix_c = [
            {'name': 'Lime', 'parts': 60.0},
            {'name': 'Vanilla', 'parts': 20.0},
            {'name': 'Cherry', 'parts': 10.0},
        ]

        sig_a, count_a, dom_a = compute_flavor_signature(mix_a, 'SODA')
        sig_b, count_b, dom_b = compute_flavor_signature(mix_b, 'SODA')
        sig_c, count_c, dom_c = compute_flavor_signature(mix_c, 'SODA')

        self.assertEqual(sig_a, 'cherry::lime|vanilla')
        self.assertEqual(sig_b, 'cherry::lime|vanilla')
        self.assertEqual(sig_a, sig_b)
        self.assertEqual(count_a, 3)
        self.assertEqual(dom_a, 'cherry')

        self.assertEqual(sig_c, 'lime::cherry|vanilla')
        self.assertNotEqual(sig_a, sig_c)
        self.assertEqual(dom_c, 'lime')

    def test_dynamic_bucket_targets(self):
        """Verify Soda/Slushie buckets use {2:5, 3:8, 4:8, 5:5} and Coffee uses {3:8, 4:8, 5:5}."""
        self.assertEqual(BUCKET_TARGETS['SODA'], {2: 5, 3: 8, 4: 8, 5: 5})
        self.assertEqual(BUCKET_TARGETS['SLUSHIE'], {2: 5, 3: 8, 4: 8, 5: 5})
        self.assertEqual(BUCKET_TARGETS['COFFEE'], {3: 8, 4: 8, 5: 5})

    @patch('soda_mixer.flavors.ai_service.AIAssistant.generate_single_quick_drink')
    def test_replenish_skips_full_buckets_and_stops_after_two_duplicate_attempts(self, mock_gen):
        """Verify 1-at-a-time cache replenishment stops after 2 consecutive duplicate attempts."""
        # Return the exact same recipe every time so the 1st succeeds and next 2 fail as duplicates
        mock_gen.return_value = {
            'name': 'Ruby Limeade',
            'description': 'Bright cherry and tart lime.',
            'mixologist_notes': '60/40 balance.',
            'profile_description': 'Crisp and fruity.',
            'ingredients': [
                {'name': 'Cherry', 'parts': 60.0},
                {'name': 'Lime', 'parts': 20.0},
            ]
        }

        result = replenish_quick_drink_cache(
            target_lab='SODA',
            target_profile='Fruity',
            target_mode='experimental',
            max_per_bucket=2,
        )
        # 1st attempt creates 'cherry::lime', next 2 attempts return 'cherry::lime' (duplicate) -> saturates
        self.assertEqual(result['created'], 1)
        cached = CachedQuickDrink.objects.get(flavor_signature='cherry::lime')
        self.assertEqual(cached.name, 'Ruby Limeade')
        self.assertEqual(cached.mixologist_notes, '60/40 balance.')
        self.assertEqual(cached.profile_description, 'Crisp and fruity.')

    def test_unified_draw_cycles_existing_and_cached_and_filters_out_of_stock(self):
        """Verify draw_quick_drinks blends saved recipes and cached drinks, cycles unseen items,
        and excludes out-of-stock recipes.
        """
        # 1. Create an official saved recipe with Cherry as dominant primary
        saved = Recipe.objects.create(name="Saved Cherry Fizz", drink_type="SODA", rating=5)
        RecipeIngredient.objects.create(recipe=saved, ingredient=self.cherry, amount=60.0, is_primary=False)
        RecipeIngredient.objects.create(recipe=saved, ingredient=self.vanilla, amount=20.0, is_primary=False)
        ensure_recipe_primary_ingredient(saved)
        self.assertEqual(get_recipe_primary_category(saved), "Fruity")

        # 2. Create 6 cached drinks in Fruity
        combos = [
            ("Cached 1", [self.cherry, self.lime], "cherry::lime", 2),
            ("Cached 2", [self.mango, self.lime], "mango::lime", 2),
            ("Cached 3", [self.cherry, self.lime, self.mint], "cherry::lime|mint", 3),
            ("Cached 4", [self.mango, self.vanilla, self.mint], "mango::mint|vanilla", 3),
            ("Cached 5", [self.cherry, self.mango, self.lime, self.vanilla], "cherry::lime|mango|vanilla", 4),
            ("Cached 6", [self.cherry, self.mango, self.lime, self.vanilla, self.mint], "cherry::lime|mango|mint|vanilla", 5),
        ]
        for title, ing_list, sig, cnt in combos:
            CachedQuickDrink.objects.create(
                drink_type='SODA',
                mode='experimental',
                profile='Fruity',
                ingredient_count=cnt,
                name=title,
                description='Cached test drink',
                mixologist_notes='Notes',
                profile_description='Profile',
                ingredients_json=[
                    {'id': ing.id, 'name': ing.name, 'parts': 60.0 if i == 0 else 15.0, 'is_primary': i == 0}
                    for i, ing in enumerate(ing_list)
                ],
                flavor_signature=sig,
            )

        # Draw 1st hand of 5 via API
        resp1 = self.client.get(reverse('quick_drinks_draw_api') + '?lab_mode=SODA&profile=Fruity&mode=experimental')
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertEqual(data1['status'], 'success')
        self.assertEqual(data1['total_pool_size'], 7)  # 1 existing + 6 cached
        self.assertEqual(len(data1['items']), 5)
        self.assertFalse(data1['needs_live_generation'])

        seen_ids = [item['id'] for item in data1['items']]

        # Draw 2nd hand passing seen_ids -> should prioritize the 2 unseen items first
        resp2 = self.client.get(
            reverse('quick_drinks_draw_api')
            + f"?lab_mode=SODA&profile=Fruity&mode=experimental&exclude_ids={','.join(seen_ids)}"
        )
        data2 = resp2.json()
        second_ids = {item['id'] for item in data2['items']}
        # All 7 items in the pool must have been covered across the two draws
        self.assertEqual(len(set(seen_ids) | second_ids), 7)

        # Mark Mint out of stock -> Cached 3, 4, 6 should be excluded dynamically (leaving 4 in-stock items)
        self.mint.is_in_inventory = False
        self.mint.save()
        resp3 = self.client.get(reverse('quick_drinks_draw_api') + '?lab_mode=SODA&profile=Fruity&mode=experimental')
        self.assertEqual(resp3.json()['total_pool_size'], 4)

    def test_manual_dismiss_and_promotion_scrubbing(self):
        """Verify dismissing a cached drink deletes it, and promoting a cached drink scrubs it from the cache."""
        c1 = CachedQuickDrink.objects.create(
            drink_type='SODA', mode='experimental', profile='Fruity', ingredient_count=2,
            name='Dismiss Me', flavor_signature='cherry::lime',
            ingredients_json=[{'id': self.cherry.id, 'name': 'Cherry', 'parts': 60.0, 'is_primary': True}]
        )
        c2 = CachedQuickDrink.objects.create(
            drink_type='SODA', mode='experimental', profile='Fruity', ingredient_count=2,
            name='Promote Me', flavor_signature='mango::lime',
            ingredients_json=[{'id': self.mango.id, 'name': 'Mango', 'parts': 60.0, 'is_primary': True}]
        )

        # 1. Manual dismiss
        resp_dismiss = self.client.post(reverse('dismiss_cached_quick_drink_api', args=[c1.uuid]))
        self.assertEqual(resp_dismiss.status_code, 200)
        self.assertFalse(CachedQuickDrink.objects.filter(uuid=c1.uuid).exists())

        # 2. Save to MixHistory with source_cached_drink_id and promote via create_recipe
        save_resp = self.client.post(
            reverse('save_mix_to_history_api'),
            data=json.dumps({
                'drink_type': 'SODA',
                'name': 'Promote Me',
                'source_cached_drink_id': str(c2.uuid),
                'ingredients': [{'id': self.mango.id, 'amount': 60.0, 'is_primary': True}]
            }),
            content_type='application/json'
        )
        mix_id = save_resp.json()['mix_id']

        promote_resp = self.client.post(reverse('create_recipe'), {
            'name': 'Official Mango Lime',
            'drink_type': 'SODA',
            'source_mix_id': mix_id,
            f'amount_{self.mango.id}': 60.0,
            f'is_primary_{self.mango.id}': 'true',
        })
        self.assertEqual(promote_resp.status_code, 302)
        self.assertFalse(CachedQuickDrink.objects.filter(uuid=c2.uuid).exists())
        self.assertTrue(Recipe.objects.filter(name='Official Mango Lime').exists())

    def test_quick_cache_settings_save_api(self):
        resp = self.client.post(
            reverse('save_quick_cache_config_api'),
            data=json.dumps({'is_enabled': True, 'schedule_time': '03:00', 'cache_modes': 'EXPERIMENTAL'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        cfg = QuickDrinkCacheConfiguration.get_config()
        self.assertEqual(cfg.schedule_time, '03:00')
        self.assertEqual(cfg.cache_modes, 'EXPERIMENTAL')

    def test_format_eta(self):
        """Verify ETA helper formats seconds into human-readable strings."""
        from soda_mixer.flavors.quick_cache_service import format_eta
        self.assertEqual(format_eta(None), "Calculating...")
        self.assertEqual(format_eta(0), "Finishing up...")
        self.assertEqual(format_eta(45), "~45s")
        self.assertEqual(format_eta(125), "~2m 05s")
        self.assertEqual(format_eta(3665), "~1h 01m")

    @patch('soda_mixer.flavors.ai_service.AIAssistant.generate_single_quick_drink')
    def test_replenish_telemetry_callback(self, mock_gen):
        """Verify progress_callback receives live telemetry dictionary with created and remaining counts."""
        mock_gen.return_value = {
            'name': 'Ruby Limeade',
            'description': 'Bright cherry and tart lime.',
            'mixologist_notes': '60/40 balance.',
            'profile_description': 'Crisp and fruity.',
            'ingredients': [
                {'name': 'Cherry', 'parts': 60.0},
                {'name': 'Lime', 'parts': 20.0},
            ]
        }
        reports = []
        def test_callback(pct, msg, telemetry=None):
            reports.append((pct, msg, telemetry))

        result = replenish_quick_drink_cache(
            progress_callback=test_callback,
            target_lab='SODA',
            target_profile='Fruity',
            target_mode='experimental',
            max_per_bucket=1,
        )
        self.assertGreaterEqual(len(reports), 1)
        # Check last report telemetry
        last_pct, last_msg, last_telem = reports[-1]
        self.assertEqual(last_pct, 100)
        self.assertIsNotNone(last_telem)
        self.assertIn('created', last_telem)
        self.assertIn('total_needed', last_telem)
        self.assertIn('remaining', last_telem)
        self.assertIn('eta_display', last_telem)
        self.assertEqual(last_telem['eta_display'], 'Complete')
        self.assertEqual(last_telem['remaining'], 0)
