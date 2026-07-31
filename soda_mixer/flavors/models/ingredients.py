import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .base import SoftDeleteModel

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
    
    PHYSICAL_STATE_CHOICES = [
        ('LIQUID', 'Liquid'),
        ('SYRUP', 'Syrup'),
        ('SAUCE', 'Sauce'),
        ('POWDER', 'Powder'),
        ('SOLID_EXTRACTABLE', 'Solid Extractable'),
    ]
    
    MIXOLOGY_FUNCTION_CHOICES = [
        ('VOLUME_BASE', 'Volume Base'),
        ('FLAVORING', 'Flavoring'),
        ('SWEETENER', 'Sweetener'),
        ('TEXTURIZER', 'Texturizer'),
        ('GARNISH', 'Garnish'),
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
    physical_state = models.CharField(
        max_length=20, 
        choices=PHYSICAL_STATE_CHOICES, 
        default='SYRUP',
        db_index=True
    )
    mixology_function = models.CharField(
        max_length=20, 
        choices=MIXOLOGY_FUNCTION_CHOICES, 
        default='FLAVORING',
        db_index=True
    )
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

    def __init__(self, *args, **kwargs):
        # Extract deprecated fields from kwargs before initializing the Model
        ing_type = kwargs.pop('ingredient_type', None)
        rtd = kwargs.pop('is_ready_to_drink', None)
        dry = kwargs.pop('is_dry', None)
        
        super().__init__(*args, **kwargs)
        
        # If we got any of these, and new fields are at defaults, we can infer them
        if ing_type or rtd is not None or dry is not None:
            name_lower = self.name.lower() if self.name else ""
            
            temp_type = ing_type or 'SODA_SYRUP'
            temp_rtd = rtd if rtd is not None else False
            temp_dry = dry if dry is not None else False
            
            if self.physical_state == 'SYRUP' and self.mixology_function == 'FLAVORING':
                if temp_type == 'COFFEE_BEAN':
                    self.physical_state = 'SOLID_EXTRACTABLE'
                    self.mixology_function = 'FLAVORING'
                elif temp_type == 'DAIRY':
                    if 'cream' in name_lower or 'half' in name_lower or 'whipped' in name_lower:
                        self.physical_state = 'SAUCE'
                        self.mixology_function = 'TEXTURIZER'
                    else:
                        self.physical_state = 'LIQUID'
                        self.mixology_function = 'VOLUME_BASE'
                elif temp_rtd:
                    self.physical_state = 'LIQUID'
                    self.mixology_function = 'VOLUME_BASE'
                elif temp_dry:
                    self.physical_state = 'POWDER'
                    if any(x in name_lower for x in ['sugar', 'sweetener', 'stevia', 'splenda', 'honey powder', 'erythritol']):
                        self.mixology_function = 'SWEETENER'
                    elif any(x in name_lower for x in ['cinnamon', 'nutmeg', 'dust', 'powder', 'cocoa', 'matcha']):
                        self.mixology_function = 'GARNISH'
                    else:
                        self.mixology_function = 'FLAVORING'
                else:
                    if any(x in name_lower for x in ['honey', 'agave', 'maple', 'caramel', 'chocolate', 'fudge', 'sauce', 'puree']):
                        self.physical_state = 'SAUCE'
                        if any(x in name_lower for x in ['honey', 'agave', 'maple']):
                            self.mixology_function = 'SWEETENER'
                        else:
                            self.mixology_function = 'FLAVORING'
                    elif any(x in name_lower for x in ['sugar', 'simple syrup', 'syrup sugar']):
                        self.physical_state = 'SYRUP'
                        self.mixology_function = 'SWEETENER'
                    elif any(x in name_lower for x in ['syrup', 'monin', 'torani', 'extract', 'bitters']):
                        self.physical_state = 'SYRUP'
                        self.mixology_function = 'FLAVORING'
                    elif any(x in name_lower for x in ['water', 'juice', 'club soda', 'soda water', 'tonic']):
                        self.physical_state = 'LIQUID'
                        self.mixology_function = 'VOLUME_BASE'

    @property
    def ingredient_type(self) -> str:
        """Backward compatibility mapping for ingredient_type."""
        if self.physical_state == 'SOLID_EXTRACTABLE':
            return 'COFFEE_BEAN'
        elif self.mixology_function == 'VOLUME_BASE' and self.physical_state == 'LIQUID':
            return 'DAIRY'
        elif self.physical_state == 'SYRUP' and self.mixology_function == 'FLAVORING':
            return 'SODA_SYRUP'
        else:
            return 'ADDITIVE'

    @ingredient_type.setter
    def ingredient_type(self, value):
        if value == 'COFFEE_BEAN':
            self.physical_state = 'SOLID_EXTRACTABLE'
            self.mixology_function = 'FLAVORING'
        elif value == 'DAIRY':
            self.physical_state = 'LIQUID'
            self.mixology_function = 'VOLUME_BASE'
        elif value == 'SODA_SYRUP':
            self.physical_state = 'SYRUP'
            self.mixology_function = 'FLAVORING'
        elif value == 'ADDITIVE':
            self.physical_state = 'SYRUP'
            self.mixology_function = 'FLAVORING'

    @property
    def is_ready_to_drink(self) -> bool:
        """Backward compatibility mapping for is_ready_to_drink."""
        return self.mixology_function == 'VOLUME_BASE' and self.physical_state == 'LIQUID'

    @is_ready_to_drink.setter
    def is_ready_to_drink(self, value):
        if value:
            self.physical_state = 'LIQUID'
            self.mixology_function = 'VOLUME_BASE'
        else:
            if self.physical_state == 'LIQUID' and self.mixology_function == 'VOLUME_BASE':
                self.physical_state = 'SYRUP'
                self.mixology_function = 'FLAVORING'

    @property
    def is_dry(self) -> bool:
        """Backward compatibility mapping for is_dry."""
        return self.physical_state in ['SOLID_EXTRACTABLE', 'POWDER']

    @is_dry.setter
    def is_dry(self, value):
        if value:
            if self.physical_state not in ['SOLID_EXTRACTABLE', 'POWDER']:
                self.physical_state = 'POWDER'
        else:
            if self.physical_state in ['SOLID_EXTRACTABLE', 'POWDER']:
                self.physical_state = 'SYRUP'

    def get_ingredient_type_display(self) -> str:
        """Backward compatibility mapping for get_ingredient_type_display."""
        t = self.ingredient_type
        if t == 'COFFEE_BEAN':
            return 'Coffee Bean'
        elif t == 'DAIRY':
            return 'Dairy & Plant Milk'
        elif t == 'SODA_SYRUP':
            return 'Soda Syrup'
        elif t == 'ADDITIVE':
            return 'Additive (Syrup, Sugar, Honey, etc.)'
        return 'Other'

    def save(self, *args, **kwargs):
        # Auto-populate physical_state and mixology_function based on old fields
        # if they are left at defaults (SYRUP and FLAVORING)
        if self.physical_state == 'SYRUP' and self.mixology_function == 'FLAVORING':
            name_lower = self.name.lower()
            if self.ingredient_type == 'COFFEE_BEAN':
                self.physical_state = 'SOLID_EXTRACTABLE'
                self.mixology_function = 'FLAVORING'
            elif self.ingredient_type == 'DAIRY':
                if 'cream' in name_lower or 'half' in name_lower or 'whipped' in name_lower:
                    self.physical_state = 'SAUCE'
                    self.mixology_function = 'TEXTURIZER'
                else:
                    self.physical_state = 'LIQUID'
                    self.mixology_function = 'VOLUME_BASE'
            elif self.is_ready_to_drink:
                self.physical_state = 'LIQUID'
                self.mixology_function = 'VOLUME_BASE'
            elif self.is_dry:
                self.physical_state = 'POWDER'
                if any(x in name_lower for x in ['sugar', 'sweetener', 'stevia', 'splenda', 'honey powder', 'erythritol']):
                    self.mixology_function = 'SWEETENER'
                elif any(x in name_lower for x in ['cinnamon', 'nutmeg', 'dust', 'powder', 'cocoa', 'matcha']):
                    self.mixology_function = 'GARNISH'
                else:
                    self.mixology_function = 'FLAVORING'
            else:
                # Additive or other
                if any(x in name_lower for x in ['honey', 'agave', 'maple', 'caramel', 'chocolate', 'fudge', 'sauce', 'puree']):
                    self.physical_state = 'SAUCE'
                    if any(x in name_lower for x in ['honey', 'agave', 'maple']):
                        self.mixology_function = 'SWEETENER'
                    else:
                        self.mixology_function = 'FLAVORING'
                elif any(x in name_lower for x in ['sugar', 'simple syrup', 'syrup sugar']):
                    self.physical_state = 'SYRUP'
                    self.mixology_function = 'SWEETENER'
                elif any(x in name_lower for x in ['syrup', 'monin', 'torani', 'extract', 'bitters']):
                    self.physical_state = 'SYRUP'
                    self.mixology_function = 'FLAVORING'
                elif any(x in name_lower for x in ['water', 'juice', 'club soda', 'soda water', 'tonic']):
                    self.physical_state = 'LIQUID'
                    self.mixology_function = 'VOLUME_BASE'
                    
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Ingredients"
        unique_together = ['name', 'brand']
