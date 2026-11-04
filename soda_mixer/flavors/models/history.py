import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .base import SoftDeleteModel
from .ingredients import Ingredient
from .recipes import Recipe


class MixHistory(SoftDeleteModel):
    """An ad-hoc mix experiment that hasn't been named/saved yet."""
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    drink_type = models.CharField(max_length=10, choices=Recipe.DRINK_TYPE_CHOICES, default='SODA')
    name = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    mixologist_notes = models.TextField(blank=True, default='')
    profile_description = models.TextField(blank=True, default='')
    coffee_style = models.CharField(max_length=20, blank=True, null=True)
    coffee_base_type = models.CharField(max_length=20, blank=True, null=True)
    drink_size_oz = models.FloatField(blank=True, null=True)
    sweetness_style = models.CharField(max_length=20, blank=True, null=True)
    bottle_scale = models.FloatField(blank=True, null=True)
    source_cached_drink_uuid = models.UUIDField(blank=True, null=True, db_index=True)
    holiday_theme = models.ForeignKey(
        'HolidayTheme',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='mix_entries',
        db_index=True,
        help_text="Optional seasonal/holiday theme carried from Quick Drinks to Recipe promotion."
    )
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
    is_primary = models.BooleanField(default=False)
    
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
