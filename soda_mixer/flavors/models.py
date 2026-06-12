"""Models for Soda Mixer flavors and recipes."""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class RecipeCategory(models.Model):
    """A user-defined tag/category for organizing recipes."""
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


class Ingredient(models.Model):
    """A single ingredient that can be mixed (Soda Syrup, Coffee Bean, etc.)."""
    INGREDIENT_TYPE_CHOICES = [
        ('SODA_SYRUP', 'Soda Syrup'),
        ('COFFEE_BEAN', 'Coffee Bean'),
        ('ADDITIVE', 'Additive (e.g., Creamer, Sugar)'),
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
    ]

    name = models.CharField(max_length=100, unique=True)
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
    
    # Coffee-specific fields
    origin = models.CharField(max_length=100, blank=True, null=True)
    roast_level = models.IntegerField(
        help_text="Roast level from 1 (light) to 5 (dark)",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        blank=True,
        null=True
    )
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
    description = models.TextField(blank=True, null=True)
    flavor_notes = models.CharField(
        max_length=200,
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


class Recipe(models.Model):
    """A saved recipe with ingredient combinations."""
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
            unit = "g"
        elif self.recipe.drink_type == 'SLUSHIE':
            unit = "oz"
        else:
            unit = "ml"
        ing_name = self.ingredient.name if self.ingredient else "Unknown Reagent"
        return f"{self.recipe.name} - {ing_name} ({self.amount}{unit})"

    class Meta:
        unique_together = ['recipe', 'ingredient']


class MixHistory(models.Model):
    """An ad-hoc mix experiment that hasn't been named/saved yet."""
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
        default=True,
        help_text="Enable internal model thinking/reasoning if supported by the provider/model."
    )
    thinking_effort = models.CharField(
        max_length=10,
        choices=THINKING_EFFORT_CHOICES,
        default='medium',
        help_text="Thinking/reasoning effort level (low, medium, high) if supported by provider/model."
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