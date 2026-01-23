# Generated manually for finding status tracking
# 2026-01-23

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add finding status tracking for cross-run analysis.

    This enables:
    - Tracking if a finding is new, recurring, fixed, or regressed
    - Computing first/last seen timestamps
    - Generating trend analysis dashboards
    """

    dependencies = [
        ('security', '0003_add_acknowledgment_fields_to_finding'),
    ]

    operations = [
        # Add status field to track finding lifecycle
        migrations.AddField(
            model_name='securityfinding',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('new', 'New'),
                    ('recurring', 'Recurring'),
                    ('fixed', 'Fixed'),
                    ('regressed', 'Regressed'),
                ],
                default='new',
                db_index=True,
                help_text='Finding lifecycle status compared to previous runs',
            ),
        ),
        # First time this finding was detected (by finding_key)
        migrations.AddField(
            model_name='securityfinding',
            name='first_seen_run_id',
            field=models.UUIDField(
                null=True,
                blank=True,
                help_text='Run ID when this finding was first detected',
            ),
        ),
        # Occurrence count across all runs
        migrations.AddField(
            model_name='securityfinding',
            name='occurrence_count',
            field=models.IntegerField(
                default=1,
                help_text='Number of times this finding has appeared across runs',
            ),
        ),
        # Add summary fields to SecurityRun for quick trend display
        migrations.AddField(
            model_name='securityrun',
            name='new_findings',
            field=models.IntegerField(default=0, help_text='Findings appearing for the first time'),
        ),
        migrations.AddField(
            model_name='securityrun',
            name='fixed_findings',
            field=models.IntegerField(default=0, help_text='Findings that were fixed since last run'),
        ),
        migrations.AddField(
            model_name='securityrun',
            name='regressed_findings',
            field=models.IntegerField(default=0, help_text='Previously fixed findings that reappeared'),
        ),
        migrations.AddField(
            model_name='securityrun',
            name='recurring_findings',
            field=models.IntegerField(default=0, help_text='Findings that still exist from previous run'),
        ),
    ]
