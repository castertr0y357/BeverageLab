"""Models for Soda Mixer flavors and recipes."""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)

    def all_objects(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def delete(self, force=False, *args, **kwargs):
        if force:
            super().delete(*args, **kwargs)
        else:
            self.deleted_at = timezone.now()
            self.save()

    class Meta:
        abstract = True


class RecipeCategory(SoftDeleteModel):
    """A user-defined tag/category for organizing recipes."""
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    COLOR_CHOICES = [
        ('bg-primary', 'Blue'),
        ('bg-success', 'Green'),
        ('bg-danger', 'Red'),
        ('bg-warning text-dark', 'Yellow'),
        ('bg-info text-dark', 'Cyan'),
        ('bg-secondary', 'Grey'),
        ('bg-dark', 'Dark'),
        ('bg-pink', 'Pink'),
    ]
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=30, choices=COLOR_CHOICES, default='bg-secondary')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Recipe Categories"


class Ingredient(SoftDeleteModel):
    """A single ingredient that can be mixed (Soda Syrup, Coffee Bean, etc.)."""
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    INGREDIENT_TYPE_CHOICES = [
        ('SODA_SYRUP', 'Soda Syrup'),
        ('COFFEE_BEAN', 'Coffee Bean'),
        ('DAIRY', 'Dairy & Plant Milk'),
        ('ADDITIVE', 'Additive (Syrup, Sugar, Honey, etc.)'),
        ('OTHER', 'Other'),
    ]
    
    CATEGORY_CHOICES = [
        ('citrus', 'Citrus'),
        ('berry', 'Berry'),
        ('tropical', 'Tropical'),
        ('herbal', 'Herbal'),
        ('spice', 'Spice'),
        ('sweet', 'Sweet'),
        ('sour', 'Sour'),
        ('artificial', 'Artificial/Fun'),
        ('coffee', 'Coffee Profile'),
        ('dairy', 'Dairy/Milk'),
    ]

    name = models.CharField(max_length=100)
    brand = models.CharField(
        max_length=100,
        default="",
        blank=True,
        help_text="The manufacturer or brand of the syrup/reagent (e.g. Monin, Torani, Homemade)"
    )
    ingredient_type = models.CharField(max_length=20, choices=INGREDIENT_TYPE_CHOICES, default='SODA_SYRUP')
    category = models.CharField(max_length=50, default='citrus')
    
    # Common stats
    intensity = models.IntegerField(
        help_text="Intensity level from 1 (mild) to 5 (strong)",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    sweetness = models.IntegerField(
        help_text="Sweetness level from 1 (low) to 5 (high)",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    acidity = models.IntegerField(
        help_text="Acidity/tartness level from 1 (low) to 5 (high)",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    bitterness = models.IntegerField(
        help_text="Bitterness level from 1 (low) to 5 (high)",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=1
    )
    complexity = models.IntegerField(
        help_text="Complexity of flavor profile from 1 (simple) to 5 (layered/deep)",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    base_suitability = models.FloatField(
        help_text="AI-synthesized score representing how well this works as a dominant base component (1.0 to 5.0)",
        validators=[MinValueValidator(1.0), MaxValueValidator(5.0)],
        default=3.0
    )
    accent_suitability = models.FloatField(
        help_text="AI-synthesized score representing how well this works as a supporting accent component (1.0 to 5.0)",
        validators=[MinValueValidator(1.0), MaxValueValidator(5.0)],
        default=3.0
    )
    
    # Coffee-specific fields
    ROAST_CHOICES = [
        ('LIGHT', 'Light'),
        ('MEDIUM', 'Medium'),
        ('DARK', 'Dark'),
    ]
    origin = models.CharField(max_length=100, blank=True, null=True)
    roast_level = models.CharField(
        max_length=10,
        choices=ROAST_CHOICES,
        default='MEDIUM',
        blank=True,
        null=True
    )
    is_decaf = models.BooleanField(default=False)
    body_intensity = models.PositiveSmallIntegerField(default=3)
    acidity_score = models.PositiveSmallIntegerField(default=3)
    bitterness_score = models.PositiveSmallIntegerField(default=3)
    process = models.CharField(
        max_length=50, 
        choices=[('washed', 'Washed'), ('natural', 'Natural'), ('honey', 'Honey'), ('other', 'Other')],
        blank=True,
        null=True
    )
    roaster = models.CharField(max_length=100, blank=True, null=True)

    is_in_inventory = models.BooleanField(
        default=True,
        help_text="Whether this ingredient is currently in your bar/lab"
    )
    is_ready_to_drink = models.BooleanField(
        default=False,
        help_text="Whether this ingredient is a ready-to-drink liquid (e.g. juices, milk, tea) that can serve as a primary volume filler."
    )
    is_dry = models.BooleanField(
        default=False,
        help_text="Whether this ingredient is measured in weight (g) rather than volume (ml/oz)."
    )
    favorite = models.BooleanField(
        default=False,
        help_text="Whether this ingredient is a favorite/preferred reagent."
    )
    description = models.TextField(blank=True, null=True)
    ai_notes = models.TextField(
        blank=True,
        null=True,
        help_text="AI-generated notes about the flavor profile and pairings"
    )
    flavor_notes = models.TextField(
        blank=True,
        help_text="Comma-separated flavor descriptors (e.g., 'berry, chocolatey, floral')"
    )
    
    # System accessibility tags
    compatible_systems = models.CharField(
        max_length=100, 
        default="SODA,COFFEE,SLUSHIE",
        help_text="Comma-separated list of compatible lab systems (SODA, COFFEE, SLUSHIE)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Ingredients"
        unique_together = ['name', 'brand']


class Recipe(SoftDeleteModel):
    """A saved recipe with ingredient combinations."""
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    DRINK_TYPE_CHOICES = [
        ('SODA', 'Soda Synthesis'),
        ('COFFEE', 'Coffee Laboratory'),
        ('SLUSHIE', 'Cryo-Slushie Lab'),
    ]

    BREW_METHOD_CHOICES = [
        ('espresso', 'Espresso'),
        ('v60', 'V60 Pour Over'),
        ('chemex', 'Chemex'),
        ('french_press', 'French Press'),
        ('aeropress', 'AeroPress'),
        ('cold_brew', 'Cold Brew'),
        ('machine', 'Automatic Machine'),
        ('other', 'Other'),
    ]

    GRIND_SIZE_CHOICES = [
        ('fine', 'Fine'),
        ('medium', 'Medium'),
        ('coarse', 'Coarse'),
    ]

    COFFEE_STYLE_CHOICES = [
        ('hot', 'Hot'),
        ('iced', 'Iced'),
        ('espresso_shot', 'Espresso Shot'),
    ]

    COFFEE_BASE_TYPE_CHOICES = [
        ('espresso', 'Espresso'),
        ('standard_brew', 'Standard Brew'),
    ]

    name = models.CharField(max_length=100)
    drink_type = models.CharField(max_length=10, choices=DRINK_TYPE_CHOICES, default='SODA')
    description = models.TextField(blank=True, null=True)
    rating = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="User rating from 0 to 5 stars"
    )
    categories = models.ManyToManyField(RecipeCategory, blank=True, related_name='recipes')
    
    # Coffee-specific brew details
    brew_method = models.CharField(max_length=20, choices=BREW_METHOD_CHOICES, blank=True, null=True)
    grind_size = models.CharField(max_length=10, choices=GRIND_SIZE_CHOICES, blank=True, null=True)
    water_temp_c = models.FloatField(blank=True, null=True, help_text="Water temperature in Celsius")
    brew_time_sec = models.IntegerField(blank=True, null=True, help_text="Total brew time in seconds")
    total_water_g = models.FloatField(blank=True, null=True, help_text="Total water used in grams")

    # Coffee drink format
    coffee_style = models.CharField(
        max_length=20,
        choices=COFFEE_STYLE_CHOICES,
        blank=True,
        null=True,
        help_text="Drink format: hot, iced, or espresso shot"
    )
    coffee_base_type = models.CharField(
        max_length=20,
        choices=COFFEE_BASE_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Whether the coffee base is espresso or a standard brew"
    )
    drink_size_oz = models.FloatField(
        blank=True,
        null=True,
        help_text="Target drink size in oz (8/12/16/20 for drinks; 1/2 for espresso shots)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def has_ready_to_drink(self) -> bool:
        """Returns True if the recipe contains at least one ready-to-drink ingredient."""
        return self.recipe_ingredients.filter(ingredient__is_ready_to_drink=True).exists()

    @property
    def water_temp_f(self):
        """Celsius to Fahrenheit conversion."""
        if self.water_temp_c is not None:
            return round((self.water_temp_c * 9/5) + 32, 1)
        return None

    def __str__(self):
        return f"{self.drink_type}: {self.name}"


class RecipeIngredient(models.Model):
    """Links an ingredient to a recipe with amount information."""
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='recipe_ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.SET_NULL, null=True, blank=True, related_name='ingredient_usage')
    amount = models.FloatField(
        help_text="Amount (ml for Soda, grams for Coffee)",
        default=1.0
    )
    notes = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(
        default=False,
        help_text="Designates this ingredient as the primary flavor anchor for Soda synthesis."
    )
    
    # 🧪 Synthesized Profile Overrides (optional AI fine-tuning)
    intensity = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    sweetness = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    acidity = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    bitterness = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    complexity = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])

    @property
    def effective_profile(self):
        """Returns the synthesized override profile if available, otherwise defaults to base reagent stats."""
        return {
            'intensity': self.intensity if self.intensity is not None else (self.ingredient.intensity if self.ingredient else 3),
            'sweetness': self.sweetness if self.sweetness is not None else (self.ingredient.sweetness if self.ingredient else 3),
            'acidity': self.acidity if self.acidity is not None else (self.ingredient.acidity if self.ingredient else 3),
            'bitterness': self.bitterness if self.bitterness is not None else (self.ingredient.bitterness if self.ingredient else 1),
            'complexity': self.complexity if self.complexity is not None else (self.ingredient.complexity if self.ingredient else 3),
            'is_synthesized': self.intensity is not None or self.sweetness is not None or self.acidity is not None or self.bitterness is not None or self.complexity is not None
        }

    def __str__(self):
        if self.recipe.drink_type == 'COFFEE':
            unit = "g" if self.ingredient and self.ingredient.ingredient_type == 'COFFEE_BEAN' else "ml"
        elif self.recipe.drink_type == 'SLUSHIE':
            unit = "oz"
        else:
            unit = "ml"
        ing_name = self.ingredient.name if self.ingredient else "Unknown Reagent"
        return f"{self.recipe.name} - {ing_name} ({self.amount}{unit})"

    class Meta:
        unique_together = ['recipe', 'ingredient']


class MixHistory(SoftDeleteModel):
    """An ad-hoc mix experiment that hasn't been named/saved yet."""
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    drink_type = models.CharField(max_length=10, choices=Recipe.DRINK_TYPE_CHOICES, default='SODA')
    mixed_at = models.DateTimeField(auto_now_add=True)
    promoted_recipe = models.OneToOneField(
        Recipe,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='history_entry'
    )

    def __str__(self):
        ingredients = ', '.join(mf.ingredient.name for mf in self.mix_ingredients.all() if mf.ingredient)[:3]
        return f"{self.drink_type} on {self.mixed_at.strftime('%b %d %H:%M')} — {ingredients}"

    class Meta:
        verbose_name_plural = "Mix History"
        ordering = ['-mixed_at']


class MixHistoryIngredient(models.Model):
    """Links an ingredient to a history entry with amount info."""
    mix = models.ForeignKey(MixHistory, on_delete=models.CASCADE, related_name='mix_ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.SET_NULL, null=True, blank=True, related_name='mix_usage')
    amount = models.FloatField(default=1.0)
    
    # 🧪 Synthesized Profile Overrides (captured from AI suggestions)
    intensity = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    sweetness = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    acidity = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    bitterness = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    complexity = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])

    @property
    def effective_profile(self):
        """Returns the synthesized override profile if available, otherwise defaults to base reagent stats."""
        return {
            'intensity': self.intensity if self.intensity is not None else (self.ingredient.intensity if self.ingredient else 3),
            'sweetness': self.sweetness if self.sweetness is not None else (self.ingredient.sweetness if self.ingredient else 3),
            'acidity': self.acidity if self.acidity is not None else (self.ingredient.acidity if self.ingredient else 3),
            'bitterness': self.bitterness if self.bitterness is not None else (self.ingredient.bitterness if self.ingredient else 1),
            'complexity': self.complexity if self.complexity is not None else (self.ingredient.complexity if self.ingredient else 3),
            'is_synthesized': self.intensity is not None or self.sweetness is not None or self.acidity is not None or self.bitterness is not None or self.complexity is not None
        }

    def __str__(self):
        ing_name = self.ingredient.name if self.ingredient else "Unknown Reagent"
        return f"{self.mix} — {ing_name}"

    class Meta:
        unique_together = ['mix', 'ingredient']


class LLMProvider(models.Model):
    """Configuration for an LLM provider (Cloud or Local)."""
    PROVIDER_CHOICES = [
        ('OPENAI', 'ChatGPT (OpenAI)'),
        ('CLAUDE', 'Claude (Anthropic)'),
        ('GEMINI', 'Gemini (Google)'),
        ('OLLAMA', 'Ollama (Local)'),
        ('OPENWEBUI', 'OpenWebUI'),
        ('ANYTHINGLLM', 'AnythingLLM'),
        ('CUSTOM', 'Custom OpenAI-Compatible'),
    ]
    name = models.CharField(max_length=100)
    provider_type = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    api_key = models.CharField(max_length=255, blank=True, null=True)
    base_url = models.URLField(blank=True, null=True, help_text="e.g., http://localhost:11434")
    default_model = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., gpt-4o or mistral")
    is_enabled = models.BooleanField(default=False)
    THINKING_EFFORT_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    enable_thinking = models.BooleanField(
        default=False,
        help_text="Enable internal model thinking/reasoning if supported by the provider/model."
    )
    thinking_effort = models.CharField(
        max_length=10,
        choices=THINKING_EFFORT_CHOICES,
        default='medium',
        help_text="Thinking/reasoning effort level (low, medium, high) if supported by provider/model."
    )
    enable_keep_warm = models.BooleanField(
        default=False,
        help_text="Enable background periodic keep-alive tasks to maintain model in VRAM."
    )
    
    def __str__(self):
        return f"{self.name} ({self.get_provider_type_display()})"


class SystemConfiguration(models.Model):
    """Singleton model for laboratory-wide settings and API credentials."""
    mealie_url = models.URLField(
        blank=True, 
        help_text="The base URL of your Mealie instance (e.g., https://mealie.local)"
    )
    mealie_api_key = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="Long-lived API token generated in Mealie User Settings"
    )
    default_llm_provider = models.ForeignKey(
        LLMProvider,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='default_for_config'
    )
    
    def save(self, *args, **kwargs):
        # Enforce singleton pattern: only one config object should exist
        self.pk = 1
        super().save(*args, **kwargs)
        
    @classmethod
    def get_config(cls):
        config, created = cls.objects.get_or_create(pk=1)
        return config

    class Meta:
        verbose_name_plural = "System Configurations"


class BackgroundExecutionTask(models.Model):
    """Tracks asynchronous execution progress and status of laboratory tasks."""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('SUCCESS', 'Success'),
        ('FAILURE', 'Failure'),
    ]
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    progress = models.IntegerField(default=0)  # 0 to 100
    error_message = models.TextField(blank=True, null=True)
    result_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.task_name} ({self.status} - {self.progress}%)"