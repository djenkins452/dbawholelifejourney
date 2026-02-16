# ==============================================================================
# File: apps/admin_console/admin.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console customizations
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-01
# Last Updated: 2026-02-15
# ==============================================================================

from django.contrib import admin

from .models import AdminGuideSection, AdminGuideArticle


@admin.register(AdminGuideSection)
class AdminGuideSectionAdmin(admin.ModelAdmin):
    list_display = ['icon', 'title', 'section_key', 'order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['title', 'section_key']
    ordering = ['order']


@admin.register(AdminGuideArticle)
class AdminGuideArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'section', 'slug', 'order', 'is_editable', 'is_active']
    list_filter = ['section', 'is_editable', 'is_active']
    search_fields = ['title', 'content']
    ordering = ['section__order', 'order']
