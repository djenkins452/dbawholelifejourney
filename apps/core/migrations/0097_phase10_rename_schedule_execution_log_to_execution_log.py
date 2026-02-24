"""
Phase 10 Consolidation — Rename ScheduleExecutionLog → ExecutionLog.

Single behavioral log table. Renames the model, table, related names,
and constraints without data loss.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('calendar_engine', '0004_phase9_idempotency_not_null'),
        ('core', '0096_userstate_schedule_instability_last_updated_and_more'),
    ]

    operations = [
        # 1. Remove old constraint and index (must happen before rename)
        migrations.RemoveConstraint(
            model_name='scheduleexecutionlog',
            name='uq_schedule_exec_log_user_idempotency',
        ),
        migrations.RemoveIndex(
            model_name='scheduleexecutionlog',
            name='core_schedu_user_id_461d2d_idx',
        ),

        # 2. Rename the model (Django ORM level)
        migrations.RenameModel(
            old_name='ScheduleExecutionLog',
            new_name='ExecutionLog',
        ),

        # 3. Rename the database table
        migrations.AlterModelTable(
            name='executionlog',
            table='core_execution_log',
        ),

        # 4. Update related_name on user FK
        migrations.AlterField(
            model_name='executionlog',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='execution_logs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 5. Update related_name on calendar_event FK
        migrations.AlterField(
            model_name='executionlog',
            name='calendar_event',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='cal_execution_logs',
                to='calendar_engine.calendarevent',
            ),
        ),

        # 6. Re-create constraint and index with new names
        migrations.AddConstraint(
            model_name='executionlog',
            constraint=models.UniqueConstraint(
                fields=('user', 'idempotency_key'),
                name='uq_exec_log_user_idempotency',
            ),
        ),
        migrations.AddIndex(
            model_name='executionlog',
            index=models.Index(
                fields=['user', 'occurred_at'],
                name='core_execut_user_id_227eb6_idx',
            ),
        ),
    ]
