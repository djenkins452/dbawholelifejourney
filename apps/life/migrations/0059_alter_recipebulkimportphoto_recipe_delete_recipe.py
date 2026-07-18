# Foundation 1B — Recipe Ownership Migration (life side).
# Remove Recipe from apps.life's state and re-target the RecipeBulkImportPhoto FK to
# meals.Recipe — WITHOUT touching the database. The table ``life_recipe`` is retained
# (now owned by meals.Recipe, see meals/0011) and the FK constraint on
# life_recipebulkimportphoto already points at it, so all database_operations are empty:
# no DROP TABLE, no constraint DDL, no data loss.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Recipe must already exist in meals' state before we delete it from life's.
        ('meals', '0011_recipe_alter_mealplanentry_recipe_and_more'),
        ('life', '0058_backfill_project_richtext'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='recipebulkimportphoto',
                    name='recipe',
                    field=models.ForeignKey(blank=True, help_text='The Recipe created when user confirms this photo (owned by Meal Intelligence)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bulk_import_photo', to='meals.recipe'),
                ),
                migrations.DeleteModel(
                    name='Recipe',
                ),
            ],
        ),
    ]
