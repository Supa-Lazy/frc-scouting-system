from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authenticate', '0003_seed_authorized_users'),
    ]

    operations = [
        migrations.AddField(
            model_name='authorizeduser',
            name='role',
            field=models.CharField(
                choices=[
                    ('student', 'Student'),
                    ('scout_tech', 'Scout Tech'),
                    ('strategist', 'Strategist'),
                    ('teacher', 'Teacher'),
                ],
                default='student',
                max_length=20,
            ),
        ),
    ]
