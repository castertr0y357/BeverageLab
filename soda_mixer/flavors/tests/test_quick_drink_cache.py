import datetime
import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from soda_mixer.flavors.models import (
    Ingredient, Recipe, RecipeIngredient, MixHistory, MixHistoryIngredient,
    CachedQuickDrink, QuickDrinkCacheConfiguration, HolidayTheme
)
from soda_mixer.flavors.quick_cache_service import (
    compute_flavor_signature, BUCKET_TARGETS, HOLIDAY_BUCKET_TARGETS,
    get_holiday_bucket_targets, prune_inactive_holiday_cache,
    replenish_quick_drink_cache, draw_quick_drinks,
    ensure_recipe_primary_ingredient, get_recipe_primary_category,
    sanitize_card_description, generate_fallback_card_description
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
        saved = Recipe.objects.create(
            name="Saved Cherry Fizz",
            drink_type="SODA",
            rating=5,
            description="FLAVOR SYNERGY: Complex cherry esters.\n\nOVERALL IMPRESSION: A radiant and sparkling cherry sensation."
        )
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

        existing_card = next((item for item in data1['items'] if item['id'] == str(saved.uuid)), None)
        if existing_card:
            self.assertEqual(existing_card['description'], "A radiant and sparkling cherry sensation.")
            self.assertIn("FLAVOR SYNERGY", existing_card['full_description'])

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

        # Check existing card description if it was drawn in the 2nd hand
        existing_card_2 = next((item for item in data2['items'] if item['id'] == str(saved.uuid)), None)
        if existing_card_2:
            self.assertEqual(existing_card_2['description'], "A radiant and sparkling cherry sensation.")
            self.assertIn("FLAVOR SYNERGY", existing_card_2['full_description'])

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

    def test_single_quick_drink_schema_structure(self):
        """Verify the structured output JSON schema for single quick drinks requires all sensory fields."""
        from soda_mixer.flavors.ai_service.prompts import AIPromptsMixin
        schema = AIPromptsMixin.get_single_quick_drink_json_schema()
        self.assertEqual(schema['type'], 'object')
        self.assertIn('name', schema['properties'])
        self.assertIn('description', schema['properties'])
        self.assertIn('mixologist_notes', schema['properties'])
        self.assertIn('profile_description', schema['properties'])
        self.assertIn('ingredients', schema['properties'])
        self.assertFalse(schema.get('additionalProperties', True))

    def test_sanitize_card_description_overall_impression_extraction(self):
        """Verify full multi-paragraph sensory reports are distilled into the clean 1-2 sentence OVERALL IMPRESSION."""
        full_synopsis = (
            "FLAVOR SYNERGY & AROMA: The synergy here is achieved through aromatic coupling. "
            "The rich, dark anthocyanins of the wild grape provide a deep base.\n\n"
            "THE TASTING EXPERIENCE: The initial taste is a vibrant burst of fruit.\n\n"
            "OVERALL IMPRESSION: This compound is a sophisticated, comforting synthesis, evoking the deep aesthetic of autumn. "
            "It finishes with remarkable clarity.\n\n"
            "AI Mixologist Notes: This compound represents a highly stable pairing."
        )
        distilled = sanitize_card_description(full_synopsis)
        self.assertEqual(
            distilled,
            "This compound is a sophisticated, comforting synthesis, evoking the deep aesthetic of autumn. "
            "It finishes with remarkable clarity."
        )

    def test_sanitize_card_description_without_overall_impression(self):
        """Verify descriptions without an OVERALL IMPRESSION header have section prefixes stripped and cap at 2 sentences."""
        raw_text = (
            "FLAVOR SYNERGY & AROMA: Crisp lime cuts through sugary berry syrup. "
            "A sharp, effervescent bite refreshes the palate. "
            "Additional notes that should be trimmed off because they exceed two sentences. "
            "AI Mixologist Notes: Technical notes here."
        )
        distilled = sanitize_card_description(raw_text)
        self.assertEqual(distilled, "Crisp lime cuts through sugary berry syrup. A sharp, effervescent bite refreshes the palate.")

    def test_sanitize_card_description_plain_and_empty(self):
        """Verify simple descriptions are preserved and empty/None returns empty string."""
        self.assertEqual(sanitize_card_description(""), "")
        self.assertEqual(sanitize_card_description(None), "")
        self.assertEqual(
            sanitize_card_description("A velvety blend of espresso and vanilla."),
            "A velvety blend of espresso and vanilla."
        )

    def test_generate_fallback_card_description_by_complexity_tier(self):
        """Verify dynamic sensory descriptions are synthesized when a recipe has no description."""
        # 2 ingredients
        two_ings = [
            {'name': 'Blackberry [Monin]', 'parts': 60.0, 'is_primary': True},
            {'name': 'Lemon', 'parts': 20.0, 'is_primary': False},
        ]
        desc_2 = generate_fallback_card_description('Test Drink', two_ings, 'SODA')
        self.assertIn('blackberry', desc_2)
        self.assertIn('lemon', desc_2)
        self.assertTrue(desc_2.endswith('.'))

        # 4 ingredients with Oxford comma
        four_ings = [
            {'name': 'Blackberry', 'parts': 60.0, 'is_primary': True},
            {'name': 'Ginger Beer', 'parts': 30.0, 'is_primary': False},
            {'name': 'Cinnamon', 'parts': 15.0, 'is_primary': False},
            {'name': 'Vanilla', 'parts': 10.0, 'is_primary': False},
        ]
        desc_4 = generate_fallback_card_description('Bubble gum', four_ings, 'SODA')
        self.assertIn('anchored by blackberry and ginger beer', desc_4)
        self.assertIn('accented with cinnamon and vanilla', desc_4)

        # Coffee mode
        coffee_ings = [
            {'name': 'Espresso', 'parts': 60.0, 'is_primary': True},
            {'name': 'Caramel', 'parts': 20.0, 'is_primary': False},
        ]
        desc_coffee = generate_fallback_card_description('Caramel Shot', coffee_ings, 'COFFEE')
        self.assertIn('pairing bold espresso with smooth caramel', desc_coffee)

    def test_draw_quick_drinks_backfills_empty_existing_recipe_description(self):
        """Verify that an existing recipe with an empty description gets a synthesized blurb in Quick Drinks
        and its database record is backfilled so it is never displayed blank."""
        empty_recipe = Recipe.objects.create(name="Blank Bubble Gum", drink_type="SODA", description="")
        RecipeIngredient.objects.create(recipe=empty_recipe, ingredient=self.cherry, amount=60.0, is_primary=True)
        RecipeIngredient.objects.create(recipe=empty_recipe, ingredient=self.lime, amount=20.0, is_primary=False)
        ensure_recipe_primary_ingredient(empty_recipe)

        result = draw_quick_drinks(drink_type='SODA', profile='Fruity', mode='experimental', count=5)
        matched_item = next((item for item in result['items'] if item['id'] == str(empty_recipe.uuid)), None)
        self.assertIsNotNone(matched_item)
        self.assertTrue(len(matched_item['description']) > 15)
        self.assertIn('cherry', matched_item['description'].lower())
        self.assertIn('lime', matched_item['description'].lower())

        # Check DB model backfill
        empty_recipe.refresh_from_db()
        self.assertEqual(empty_recipe.description, matched_item['description'])

    def test_holiday_theme_date_window_and_year_wrap(self):
        """Verify HolidayTheme.is_currently_active() handles standard windows, year-boundary wrapping, and force_active."""
        HolidayTheme.ensure_default_themes()
        spooky = HolidayTheme.objects.get(slug='spooky-synthesis')
        winter = HolidayTheme.objects.get(slug='winter-wonderland')

        # Spooky Synthesis: Oct 1 - Nov 1
        self.assertTrue(spooky.is_currently_active(datetime.date(2026, 10, 31)))
        self.assertTrue(spooky.is_currently_active(datetime.date(2026, 11, 1)))
        self.assertFalse(spooky.is_currently_active(datetime.date(2026, 11, 5)))

        # Winter Wonderland: Dec 1 - Jan 5 (wraps across year boundary)
        self.assertTrue(winter.is_currently_active(datetime.date(2026, 12, 25)))
        self.assertTrue(winter.is_currently_active(datetime.date(2027, 1, 3)))
        self.assertFalse(winter.is_currently_active(datetime.date(2026, 11, 25)))
        self.assertFalse(winter.is_currently_active(datetime.date(2027, 1, 10)))

        # force_active overrides out-of-season date
        winter.force_active = True
        winter.save()
        self.assertTrue(winter.is_currently_active(datetime.date(2026, 7, 15)))

        # Disabling overrides force_active
        winter.is_enabled = False
        winter.save()
        self.assertFalse(winter.is_currently_active(datetime.date(2026, 12, 25)))

    def test_holiday_bucket_targets_sum_to_15(self):
        """Verify holiday bucket targets allocate 15 recipes per lab across complexity tiers."""
        soda_buckets = get_holiday_bucket_targets('SODA', 15)
        coffee_buckets = get_holiday_bucket_targets('COFFEE', 15)
        self.assertEqual(soda_buckets, {2: 3, 3: 5, 4: 4, 5: 3})
        self.assertEqual(sum(soda_buckets.values()), 15)
        self.assertEqual(coffee_buckets, {3: 6, 4: 5, 5: 4})
        self.assertEqual(sum(coffee_buckets.values()), 15)

    def test_prune_inactive_holiday_cache_preserves_promoted_recipes(self):
        """Verify expired holiday CachedQuickDrinks are pruned while promoted official Recipes remain intact."""
        HolidayTheme.ensure_default_themes()
        spooky = HolidayTheme.objects.get(slug='spooky-synthesis')
        spooky.is_enabled = False  # Make it inactive
        spooky.save()

        active_ht = HolidayTheme.objects.get(slug='autumn-harvest')
        active_ht.is_enabled = True
        active_ht.force_active = True
        active_ht.save()

        c_expired = CachedQuickDrink.objects.create(
            drink_type='SODA', mode='experimental', profile='holiday:spooky-synthesis',
            holiday_theme=spooky, ingredient_count=2, name='Expired Spooky Drink',
            flavor_signature='cherry::lime',
            ingredients_json=[{'id': self.cherry.id, 'name': 'Cherry', 'parts': 60.0, 'is_primary': True}]
        )
        c_active = CachedQuickDrink.objects.create(
            drink_type='SODA', mode='experimental', profile='holiday:autumn-harvest',
            holiday_theme=active_ht, ingredient_count=2, name='Active Harvest Drink',
            flavor_signature='mango::lime',
            ingredients_json=[{'id': self.mango.id, 'name': 'Mango', 'parts': 60.0, 'is_primary': True}]
        )
        official_spooky = Recipe.objects.create(
            name='Official Spooky Elixir', drink_type='SODA', holiday_theme=spooky
        )

        pruned = prune_inactive_holiday_cache()
        self.assertEqual(pruned, 1)
        self.assertFalse(CachedQuickDrink.objects.filter(id=c_expired.id).exists())
        self.assertTrue(CachedQuickDrink.objects.filter(id=c_active.id).exists())
        self.assertTrue(Recipe.objects.filter(id=official_spooky.id, holiday_theme=spooky).exists())

    def test_holiday_promotion_tags_recipe_and_cycles_in_holiday_draw(self):
        """Verify promoting a holiday CachedQuickDrink via MixHistory automatically tags the Recipe with that HolidayTheme
        and includes it in subsequent holiday Quick Drink draws."""
        HolidayTheme.ensure_default_themes()
        autumn = HolidayTheme.objects.get(slug='autumn-harvest')
        autumn.force_active = True
        autumn.save()

        c_holiday = CachedQuickDrink.objects.create(
            drink_type='SODA', mode='experimental', profile='holiday:autumn-harvest',
            holiday_theme=autumn, ingredient_count=2, name='Harvest Cherry Spice',
            description='Warm autumn cherry.', flavor_signature='cherry::vanilla',
            ingredients_json=[
                {'id': self.cherry.id, 'name': 'Cherry', 'parts': 60.0, 'is_primary': True},
                {'id': self.vanilla.id, 'name': 'Vanilla', 'parts': 20.0, 'is_primary': False},
            ]
        )

        # Save to MixHistory referencing the cached drink
        save_resp = self.client.post(
            reverse('save_mix_to_history_api'),
            data=json.dumps({
                'drink_type': 'SODA',
                'name': 'Harvest Cherry Spice',
                'source_cached_drink_id': str(c_holiday.uuid),
                'ingredients': [
                    {'id': self.cherry.id, 'amount': 60.0, 'is_primary': True},
                    {'id': self.vanilla.id, 'amount': 20.0, 'is_primary': False},
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(save_resp.status_code, 200)
        mix_id = save_resp.json()['mix_id']
        mix_obj = MixHistory.objects.get(uuid=mix_id)
        self.assertEqual(mix_obj.holiday_theme, autumn)

        # Promote to Recipe
        promote_resp = self.client.post(reverse('create_recipe'), {
            'name': 'Harvest Cherry Reserve',
            'drink_type': 'SODA',
            'description': 'Warm autumn cherry.',
            'source_mix_id': mix_id,
            f'amount_{self.cherry.id}': 60.0,
            f'is_primary_{self.cherry.id}': 'true',
            f'amount_{self.vanilla.id}': 20.0,
        })
        self.assertEqual(promote_resp.status_code, 302)
        self.assertFalse(CachedQuickDrink.objects.filter(uuid=c_holiday.uuid).exists())

        promoted_recipe = Recipe.objects.get(name='Harvest Cherry Reserve')
        self.assertEqual(promoted_recipe.holiday_theme, autumn)

        # Drawing for 'holiday:autumn-harvest' should return the promoted official recipe
        draw_res = draw_quick_drinks(drink_type='SODA', profile='holiday:autumn-harvest', mode='experimental')
        self.assertEqual(draw_res['total_pool_size'], 1)
        self.assertEqual(draw_res['items'][0]['name'], 'Harvest Cherry Reserve')
        self.assertEqual(draw_res['items'][0]['source_type'], 'existing')
        self.assertEqual(draw_res['items'][0]['holiday_theme_id'], str(autumn.uuid))

    def test_holiday_settings_crud_apis(self):
        """Verify creating, toggling, and deleting a HolidayTheme via Settings API endpoints."""
        create_resp = self.client.post(
            reverse('save_holiday_theme_api'),
            data=json.dumps({
                'name': 'New Year Sparkle',
                'start_month': 12,
                'start_day': 28,
                'end_month': 1,
                'end_day': 3,
                'icon_class': 'bi-stars',
                'accent_color': '#eab308',
                'target_pool_size': 15,
                'flavor_directives': 'Effervescent champagne-inspired citrus and elderflower notes.',
                'is_enabled': True,
                'force_active': True,
            }),
            content_type='application/json'
        )
        self.assertEqual(create_resp.status_code, 200)
        h_uuid = create_resp.json()['uuid']
        ht = HolidayTheme.objects.get(uuid=h_uuid)
        self.assertEqual(ht.slug, 'new-year-sparkle')
        self.assertTrue(ht.force_active)

        # Toggle force_active off
        toggle_resp = self.client.post(
            reverse('toggle_holiday_theme_api', args=[h_uuid]),
            data=json.dumps({'force_active': False}),
            content_type='application/json'
        )
        self.assertEqual(toggle_resp.status_code, 200)
        ht.refresh_from_db()
        self.assertFalse(ht.force_active)

        # Delete holiday
        del_resp = self.client.post(reverse('delete_holiday_theme_api', args=[h_uuid]))
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse(HolidayTheme.objects.filter(uuid=h_uuid).exists())

