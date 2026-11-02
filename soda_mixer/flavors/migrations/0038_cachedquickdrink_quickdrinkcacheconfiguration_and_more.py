# Generated migration for CachedQuickDrink, QuickDrinkCacheConfiguration,
# MixHistory.source_cached_drink_uuid, and primary ingredient backfill on existing Recipes.

import uuid
from django.db import migrations, models


def backfill_recipe_primary_ingredients(apps, schema_editor):
    Recipe = apps.get_model('flavors', 'Recipe')
    coffee_structural = (
        'bean', 'espresso', 'roast', 'whole milk', 'oat milk',
        'skim milk', 'almond milk', 'soy milk', 'coconut milk'
    )
    for recipe in Recipe.objects.all():
        rings = list(recipe.recipe_ingredients.select_related('ingredient').all())
        if not rings:
            continue
        if any(r.is_primary for r in rings):
            continue
        dt = (recipe.drink_type or 'SODA').upper()
        flavor_rings = []
        for r in rings:
            ing = r.ingredient
            if not ing:
                continue
            if dt == 'COFFEE':
                if ing.physical_state == 'SOLID_EXTRACTABLE' or (ing.mixology_function == 'VOLUME_BASE' and ing.physical_state == 'LIQUID'):
                    continue
                if (ing.category or '').lower() in ('coffee', 'dairy'):
                    continue
                if any(t in (ing.name or '').lower() for t in coffee_structural):
                    continue
            flavor_rings.append(r)
        if not flavor_rings:
            flavor_rings = [r for r in rings if r.ingredient is not None]
        if flavor_rings:
            dominant = max(flavor_rings, key=lambda r: (float(r.amount or 0.0), (r.ingredient.name or '').lower()))
            dominant.is_primary = True
            dominant.save(update_fields=['is_primary'])


class Migration(migrations.Migration):

    dependencies = [
        ('flavors', '0037_remove_systemconfiguration_mealie_api_key_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CachedQuickDrink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('drink_type', models.CharField(choices=[('SODA', 'Soda Synthesis'), ('COFFEE', 'Coffee Laboratory'), ('SLUSHIE', 'Cryo-Slushie Lab')], db_index=True, default='SODA', max_length=10)),
                ('mode', models.CharField(choices=[('standard', 'Standard Mode'), ('experimental', 'Experimental Mode')], db_index=True, default='experimental', max_length=20)),
                ('profile', models.CharField(db_index=True, help_text='Category profile (e.g. Fruity, Sweet, Citrus)', max_length=50)),
                ('ingredient_count', models.IntegerField(db_index=True, help_text='Total ingredient count bucket (2, 3, 4, or 5)')),
                ('name', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True, default='', help_text='Short 20-30 word menu blurb')),
                ('mixologist_notes', models.TextField(blank=True, default='', help_text='Pre-generated mixologist note for instant Synopsis view')),
                ('profile_description', models.TextField(blank=True, default='', help_text='Pre-generated 3-paragraph sensory report for instant Synopsis view')),
                ('ingredients_json', models.JSONField(default=list, help_text='List of {id, name, parts, is_primary}')),
                ('flavor_signature', models.CharField(db_index=True, help_text='Canonical signature: dominant_anchor::sorted_modifiers', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'Cached Quick Drink',
                'verbose_name_plural': 'Cached Quick Drinks',
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='QuickDrinkCacheConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=True, help_text='Enable scheduled nightly Quick Drink cache replenishment.')),
                ('schedule_time', models.CharField(default='02:00', help_text='UTC time of daily execution (HH:MM in 24hr format).', max_length=5)),
                ('cache_modes', models.CharField(choices=[('EXPERIMENTAL', 'Experimental Mode Only'), ('STANDARD', 'Standard Mode Only'), ('BOTH', 'Both (Experimental First, Then Standard)')], default='BOTH', max_length=20)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_status', models.CharField(blank=True, default='', max_length=20)),
                ('last_summary', models.TextField(blank=True, default='')),
            ],
            options={
                'verbose_name_plural': 'Quick Drink Cache Configurations',
            },
        ),
        migrations.AddField(
            model_name='mixhistory',
            name='source_cached_drink_uuid',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_recipe_primary_ingredients, migrations.RunPython.noop),
    ]
