# Generated manually for assistant.ImprovementTaskModel

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ImprovementTaskModel',
            fields=[
                ('id', models.UUIDField(
                    default=uuid.uuid4,
                    editable=False,
                    help_text='Unique identifier for the task',
                    primary_key=True,
                    serialize=False
                )),
                ('title', models.CharField(
                    help_text='Brief title describing the improvement task',
                    max_length=255
                )),
                ('description', models.JSONField(
                    default=dict,
                    help_text='Structured description with objective, inputs, actions, output'
                )),
                ('gap_type', models.CharField(
                    choices=[
                        ('unknown_data_type', 'Unknown Data Type'),
                        ('missing_keywords', 'Missing Keywords'),
                        ('no_data_method', 'No Data Method'),
                        ('unsupported_query_pattern', 'Unsupported Query Pattern'),
                    ],
                    help_text='Type of knowledge gap that triggered this task',
                    max_length=50
                )),
                ('severity', models.CharField(
                    choices=[
                        ('low', 'Low - Keyword Addition'),
                        ('medium', 'Medium - New Query Method'),
                        ('high', 'High - Application Change'),
                    ],
                    help_text='Severity level indicating implementation effort',
                    max_length=20
                )),
                ('original_query', models.TextField(
                    help_text='The original user query that revealed the gap'
                )),
                ('suggested_fix', models.TextField(
                    help_text='Human-readable description of the suggested fix'
                )),
                ('code_template', models.TextField(
                    blank=True,
                    help_text='Generated code template for implementing the fix'
                )),
                ('test_template', models.TextField(
                    blank=True,
                    help_text='Generated test code template for verifying the fix'
                )),
                ('requires_approval', models.BooleanField(
                    default=True,
                    help_text='Whether this task requires manual approval before execution'
                )),
                ('status', models.CharField(
                    choices=[
                        ('new', 'New'),
                        ('pending_approval', 'Pending Approval'),
                        ('approved', 'Approved'),
                        ('in_progress', 'In Progress'),
                        ('testing', 'Testing'),
                        ('completed', 'Completed'),
                        ('error', 'Error'),
                        ('rolled_back', 'Rolled Back'),
                    ],
                    default='new',
                    help_text='Current status in the task lifecycle',
                    max_length=20
                )),
                ('created_at', models.DateTimeField(
                    auto_now_add=True,
                    help_text='When the task was created'
                )),
                ('updated_at', models.DateTimeField(
                    auto_now=True,
                    help_text='When the task was last updated'
                )),
                ('approved_at', models.DateTimeField(
                    blank=True,
                    help_text='When the task was approved',
                    null=True
                )),
                ('completed_at', models.DateTimeField(
                    blank=True,
                    help_text='When the task was completed',
                    null=True
                )),
                ('approved_by', models.ForeignKey(
                    blank=True,
                    help_text='User who approved the task',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_improvement_tasks',
                    to=settings.AUTH_USER_MODEL
                )),
                ('error_message', models.TextField(
                    blank=True,
                    help_text='Error message if the task failed'
                )),
                ('git_commit_before', models.CharField(
                    blank=True,
                    help_text='Git commit SHA before changes were applied',
                    max_length=40
                )),
                ('git_commit_after', models.CharField(
                    blank=True,
                    help_text='Git commit SHA after changes were applied',
                    max_length=40
                )),
            ],
            options={
                'verbose_name': 'Improvement Task',
                'verbose_name_plural': 'Improvement Tasks',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='improvementtaskmodel',
            index=models.Index(fields=['status'], name='assistant_i_status_4b7e8c_idx'),
        ),
        migrations.AddIndex(
            model_name='improvementtaskmodel',
            index=models.Index(fields=['gap_type'], name='assistant_i_gap_typ_7a3d12_idx'),
        ),
        migrations.AddIndex(
            model_name='improvementtaskmodel',
            index=models.Index(fields=['severity'], name='assistant_i_severit_f2c891_idx'),
        ),
        migrations.AddIndex(
            model_name='improvementtaskmodel',
            index=models.Index(fields=['created_at'], name='assistant_i_created_d1e456_idx'),
        ),
        migrations.AddIndex(
            model_name='improvementtaskmodel',
            index=models.Index(fields=['requires_approval', 'status'], name='assistant_i_require_a9b3c7_idx'),
        ),
    ]
