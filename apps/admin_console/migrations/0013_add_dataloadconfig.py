# ==============================================================================
# File: apps/admin_console/migrations/0013_add_dataloadconfig.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Add DataLoadConfig model for tracking one-time data loads
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0012_add_task_attachment'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataLoadConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('loader_name', models.CharField(help_text='Unique identifier for this data loader', max_length=100, unique=True)),
                ('display_name', models.CharField(help_text='Human-readable name', max_length=200)),
                ('loader_type', models.CharField(choices=[('fixture', 'Django Fixture'), ('command', 'Management Command'), ('blueprint', 'Project Blueprint')], default='fixture', max_length=20)),
                ('description', models.TextField(blank=True, help_text='Description of what this loader does')),
                ('is_loaded', models.BooleanField(default=False, help_text='Whether this loader has been run successfully')),
                ('loaded_at', models.DateTimeField(blank=True, help_text='When the loader was last run', null=True)),
                ('loaded_by', models.CharField(blank=True, help_text='What triggered the load (startup, manual, migration)', max_length=50)),
                ('records_created', models.PositiveIntegerField(default=0, help_text='Number of records created by this loader')),
                ('records_updated', models.PositiveIntegerField(default=0, help_text='Number of records updated by this loader')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Data Load Config',
                'verbose_name_plural': 'Data Load Configs',
                'ordering': ['loader_type', 'loader_name'],
            },
        ),
    ]
