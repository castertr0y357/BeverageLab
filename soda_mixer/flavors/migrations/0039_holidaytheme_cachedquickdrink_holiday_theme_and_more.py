# Generated migration for HolidayTheme model, ForeignKey links on Recipe, MixHistory, and CachedQuickDrink,
# and zero-config seeding of the 6 default seasonal/holiday themes.

import uuid
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


DEFAULT_THEMES = [
    {
        'name': 'Spooky Synthesis',
        'slug': 'spooky-synthesis',
        'start_month': 10,
        'start_day': 1,
        'end_month': 11,
        'end_day': 1,
        'icon_class': 'bi-moon-stars-fill',
        'accent_color': '#a855f7',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select dark, brooding berries (Blackberry, Wild Grape, Cherry) contrasted with sharp green '
            'citrus (Kiwi, Lime) or smoky caramelized accents (Toasted Marshmallow, Spiced Brown Sugar). '
            'Give the recipe an eerie, gothic, or Halloween laboratory name.'
        ),
    },
    {
        'name': 'Autumn Harvest',
        'slug': 'autumn-harvest',
        'start_month': 11,
        'start_day': 2,
        'end_month': 11,
        'end_day': 30,
        'icon_class': 'bi-tree-fill',
        'accent_color': '#f97316',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select warm, comforting autumn reagents such as Cinnamon, Spiced Brown Sugar, Desert Pear, '
            'Toasted Marshmallow, Vanilla, and rich orchard fruits. '
            'Give the recipe a cozy, harvest, or hearth-inspired laboratory name.'
        ),
    },
    {
        'name': 'Winter Wonderland',
        'slug': 'winter-wonderland',
        'start_month': 12,
        'start_day': 1,
        'end_month': 1,
        'end_day': 5,
        'icon_class': 'bi-snow2',
        'accent_color': '#38bdf8',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select festive winter reagents such as Peppermint, Frosted Mint, Chocolate Fudge, Cherry, '
            'Cinnamon, Orange, and creamy Vanilla. '
            'Give the recipe a festive winter, frost, or holiday laboratory name.'
        ),
    },
    {
        'name': "Valentine's Reserve",
        'slug': 'valentines-reserve',
        'start_month': 2,
        'start_day': 1,
        'end_month': 2,
        'end_day': 15,
        'icon_class': 'bi-suit-heart-fill',
        'accent_color': '#f43f5e',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select romantic crimson fruits (Cherry, Strawberry, Raspberry) layered with indulgent '
            'Chocolate Fudge, Toasted Marshmallow, or creamy Vanilla. '
            'Give the recipe an elegant, romantic, ruby-toned laboratory name.'
        ),
    },
    {
        'name': 'Emerald Alchemy',
        'slug': 'emerald-alchemy',
        'start_month': 3,
        'start_day': 1,
        'end_month': 3,
        'end_day': 20,
        'icon_class': 'bi-flower1',
        'accent_color': '#10b981',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select vibrant green and botanical reagents such as Frosted Mint, Peppermint, Kiwi, Lime, '
            'Green Apple, and creamy Vanilla. '
            'Give the recipe an emerald, shamrock, or botanical laboratory name.'
        ),
    },
    {
        'name': 'Summer Solstice',
        'slug': 'summer-solstice',
        'start_month': 5,
        'start_day': 15,
        'end_month': 8,
        'end_day': 31,
        'icon_class': 'bi-brightness-high-fill',
        'accent_color': '#facc15',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select sun-drenched, refreshing reagents such as Watermelon, Pineapple, Guava, Coconut, '
            'Strawberry, Lemon, and Lime. '
            'Give the recipe a radiant summer, solar, or coastal laboratory name.'
        ),
    },
]


def seed_default_holiday_themes(apps, schema_editor):
    HolidayTheme = apps.get_model('flavors', 'HolidayTheme')
    for item in DEFAULT_THEMES:
        HolidayTheme.objects.get_or_create(slug=item['slug'], defaults=item)


class Migration(migrations.Migration):

    dependencies = [
        ('flavors', '0038_cachedquickdrink_quickdrinkcacheconfiguration_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='HolidayTheme',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('name', models.CharField(max_length=80, unique=True)),
                ('slug', models.SlugField(max_length=80, unique=True)),
                ('start_month', models.IntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])),
                ('start_day', models.IntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)])),
                ('end_month', models.IntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])),
                ('end_day', models.IntegerField(default=31, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)])),
                ('flavor_directives', models.TextField(blank=True, default='', help_text='Positive mixology instructions guiding ingredient selection and thematic naming.')),
                ('icon_class', models.CharField(default='bi-stars', max_length=50)),
                ('accent_color', models.CharField(default='#00f2fe', max_length=30)),
                ('is_enabled', models.BooleanField(db_index=True, default=True)),
                ('force_active', models.BooleanField(db_index=True, default=False, help_text='Force this holiday active in Quick Drinks and Nightly Cache regardless of current date.')),
                ('target_pool_size', models.IntegerField(default=15, help_text='Target number of cached recipes per lab for this holiday (default 15).', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(50)])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Holiday Theme',
                'verbose_name_plural': 'Holiday Themes',
                'ordering': ['start_month', 'start_day', 'name'],
            },
        ),
        migrations.AlterField(
            model_name='cachedquickdrink',
            name='profile',
            field=models.CharField(db_index=True, help_text='Category profile (e.g. Fruity, Sweet, or holiday:winter-wonderland)', max_length=80),
        ),
        migrations.AddField(
            model_name='cachedquickdrink',
            name='holiday_theme',
            field=models.ForeignKey(blank=True, help_text='Associated HolidayTheme if this cached drink was generated for a seasonal spotlight.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cached_drinks', to='flavors.holidaytheme', db_index=True),
        ),
        migrations.AddField(
            model_name='mixhistory',
            name='holiday_theme',
            field=models.ForeignKey(blank=True, help_text='Optional seasonal/holiday theme carried from Quick Drinks to Recipe promotion.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mix_entries', to='flavors.holidaytheme', db_index=True),
        ),
        migrations.AddField(
            model_name='recipe',
            name='holiday_theme',
            field=models.ForeignKey(blank=True, help_text='Optional seasonal/holiday theme this recipe belongs to.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recipes', to='flavors.holidaytheme', db_index=True),
        ),
        migrations.RunPython(seed_default_holiday_themes, migrations.RunPython.noop),
    ]
