# Foundation 1B — Recipe Ownership Migration.
# Move the Recipe model from apps.life to apps.meals WITHOUT touching the database.
# The physical table ``life_recipe`` (and every FK constraint pointing at it) already
# exists and is correct, so this is a pure Django STATE change: register Recipe under
# meals and re-target the RecipeIngredient/MealPlanEntry FKs to meals.Recipe. All
# database_operations are empty — no CREATE TABLE, no constraint DDL, no data movement,
# IDs preserved. (Paired with life/0059 which removes Recipe from life's state.)
import apps.core.current_context
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('meals', '0010_routine_maintenance_bridge_choices'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='Recipe',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('status', models.CharField(choices=[('active', 'Active'), ('archived', 'Archived'), ('deleted', 'Deleted')], db_index=True, default='active', max_length=10)),
                        ('deleted_at', models.DateTimeField(blank=True, null=True)),
                        ('created_via', models.CharField(choices=[('manual', 'Manual Entry'), ('ai_camera', 'AI Camera Scan'), ('import', 'Data Import'), ('api', 'API'), ('routine', 'Routine Completion')], default='manual', help_text='How this entry was created', max_length=20)),
                        ('title', models.CharField(max_length=200)),
                        ('description', models.TextField(blank=True, help_text='Brief description or story behind this recipe')),
                        ('ingredients', models.TextField(help_text='One ingredient per line')),
                        ('instructions', models.TextField()),
                        ('prep_time_minutes', models.PositiveIntegerField(blank=True, help_text='Preparation time in minutes', null=True)),
                        ('cook_time_minutes', models.PositiveIntegerField(blank=True, help_text='Cooking time in minutes', null=True)),
                        ('servings', models.PositiveIntegerField(blank=True, null=True)),
                        ('difficulty', models.CharField(blank=True, choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')], max_length=20)),
                        ('category', models.CharField(blank=True, help_text='e.g., Breakfast, Dinner, Dessert, Holiday', max_length=50)),
                        ('tags', models.JSONField(blank=True, default=list, help_text="Tags like 'vegetarian', 'quick', 'family-favorite'")),
                        ('source', models.CharField(blank=True, help_text='Where did this recipe come from?', max_length=200)),
                        ('source_url', models.URLField(blank=True)),
                        ('image', models.ImageField(blank=True, null=True, upload_to='life/recipes/')),
                        ('notes', models.TextField(blank=True, help_text='Your variations, tips, or memories')),
                        ('is_favorite', models.BooleanField(default=False)),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)ss', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'verbose_name': 'Recipe',
                        'verbose_name_plural': 'Recipes',
                        'db_table': 'life_recipe',
                        'ordering': ['-is_favorite', 'title'],
                    },
                    bases=(apps.core.current_context.NarratableMixin, models.Model),
                ),
                migrations.AlterField(
                    model_name='mealplanentry',
                    name='recipe',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meal_plan_entries', to='meals.recipe'),
                ),
                migrations.AlterField(
                    model_name='recipeingredient',
                    name='recipe',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='structured_ingredients', to='meals.recipe'),
                ),
            ],
        ),
    ]
