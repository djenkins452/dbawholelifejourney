"""
Core Admin Configuration
"""

from django.contrib import admin

from .models import Category, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "order", "icon"]
    list_editable = ["order"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["order", "name"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "color", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["name", "user__email"]
    raw_id_fields = ["user"]
