import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .base import SoftDeleteModel
from .ingredients import Ingredient


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


class Recipe(SoftDeleteModel):
    """A saved recipe with ingredient combinations."""
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    DRINK_TYPE_CHOICES = [
        ('SODA', 'Soda Synthesis'),
        ('COFFEE', 'Coffee Laboratory'),
        ('CRYO', 'Cryo-Slushie Lab'),
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
        return self.recipe_ingredients.filter(ingredient__physical_state='LIQUID', ingredient__mixology_function='VOLUME_BASE').exists()

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
