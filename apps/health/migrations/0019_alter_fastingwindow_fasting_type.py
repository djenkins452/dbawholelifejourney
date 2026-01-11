# Generated manually to add "No Fasting" option

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('health', '0018_add_common_fitness_classes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fastingwindow',
            name='fasting_type',
            field=models.CharField(
                choices=[
                    ('none', 'No Fasting'),
                    ('16:8', '16:8 (16 hours fast)'),
                    ('18:6', '18:6 (18 hours fast)'),
                    ('20:4', '20:4 (20 hours fast)'),
                    ('OMAD', 'OMAD (One Meal A Day)'),
                    ('24h', '24 Hour Fast'),
                    ('36h', '36 Hour Fast'),
                    ('custom', 'Custom'),
                ],
                default='16:8',
                max_length=10,
            ),
        ),
    ]
