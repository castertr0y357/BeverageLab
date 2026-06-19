from django.contrib import admin
from .models import Ingredient, Recipe, RecipeIngredient, MixHistory, MixHistoryIngredient, RecipeCategory


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ['name', 'ingredient_type', 'category', 'intensity', 'is_in_inventory', 'is_ready_to_drink']
    list_filter = ['ingredient_type', 'category', 'intensity', 'is_in_inventory', 'is_ready_to_drink']
    search_fields = ['name', 'description', 'ai_notes', 'flavor_notes', 'origin', 'roaster']
    ordering = ['name']


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ['name', 'drink_type', 'rating', 'created_at']
    list_filter = ['drink_type', 'rating', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['-created_at']


admin.site.register(RecipeIngredient)
admin.site.register(MixHistory)
admin.site.register(MixHistoryIngredient)
admin.site.register(RecipeCategory)