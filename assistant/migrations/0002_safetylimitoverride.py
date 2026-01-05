# Generated manually for assistant.SafetyLimitOverride

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SafetyLimitOverride',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID'
                )),
                ('limit_name', models.CharField(
                    choices=[
                        ('max_autonomous_per_hour', 'Max Autonomous Per Hour'),
                        ('max_autonomous_per_day', 'Max Autonomous Per Day'),
                        ('max_pending_tasks', 'Max Pending Tasks'),
                        ('max_file_modifications_per_day', 'Max File Modifications Per Day'),
                        ('error_rate_threshold', 'Error Rate Threshold'),
                        ('system_enabled', 'System Enabled'),
                    ],
                    help_text='The safety limit to override',
                    max_length=50,
                    unique=True
                )),
                ('value', models.IntegerField(
                    help_text='Override value for the limit'
                )),
                ('is_active', models.BooleanField(
                    default=True,
                    help_text='Whether this override is currently active'
                )),
                ('reason', models.TextField(
                    blank=True,
                    help_text='Reason for the override'
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('expires_at', models.DateTimeField(
                    blank=True,
                    help_text='When this override expires (null = never)',
                    null=True
                )),
            ],
            options={
                'verbose_name': 'Safety Limit Override',
                'verbose_name_plural': 'Safety Limit Overrides',
            },
        ),
    ]
