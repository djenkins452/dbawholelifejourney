# ==============================================================================
# File: apps/core/migrations/0036_favoritepage_pageview.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Add FavoritePage and PageView models for favorites menu feature
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-05
# Last Updated: 2026-01-05
# ==============================================================================

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0035_merge_bible_reading_plans'),
    ]

    operations = [
        migrations.CreateModel(
            name='FavoritePage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.CharField(help_text="The URL path of the favorited page (e.g., '/journal/entries/')", max_length=500)),
                ('title', models.CharField(help_text='Display title for the favorite', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorite_pages', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Favorite Page',
                'verbose_name_plural': 'Favorite Pages',
                'ordering': ['-created_at'],
                'unique_together': {('user', 'url')},
            },
        ),
        migrations.CreateModel(
            name='PageView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.CharField(help_text='The URL path that was viewed', max_length=500)),
                ('title', models.CharField(help_text='Page title at time of viewing', max_length=200)),
                ('viewed_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='page_views', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Page View',
                'verbose_name_plural': 'Page Views',
                'ordering': ['-viewed_at'],
            },
        ),
    ]
