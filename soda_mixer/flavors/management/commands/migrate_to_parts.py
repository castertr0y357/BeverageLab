from django.core.management.base import BaseCommand
from django.db import transaction
from soda_mixer.flavors.models import Recipe

class Command(BaseCommand):
    help = 'Migrates legacy recipes from percentages (sum=100) to normalized relative parts.'

    def handle(self, *args, **options):
        recipes = Recipe.objects.all()
        updated_recipes = 0
        updated_ingredients = 0

        with transaction.atomic():
            for recipe in recipes:
                ingredients = recipe.recipe_ingredients.all()
                if not ingredients:
                    continue
                
                total_amount = sum(ing.amount for ing in ingredients)
                
                # If it looks like a percentage-based recipe (adds up to 100 or close)
                if 99.0 <= total_amount <= 101.0:
                    # Dividing by 10 is a safe bet to shift from "60, 30, 10" to "6.0, 3.0, 1.0" parts.
                    for ing in ingredients:
                        ing.amount = round(ing.amount / 10.0, 2)
                        ing.save()
                        updated_ingredients += 1
                    updated_recipes += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully migrated {updated_recipes} recipes ({updated_ingredients} ingredients) to normalized parts.'))
