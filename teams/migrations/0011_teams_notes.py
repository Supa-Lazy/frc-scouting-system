from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0010_team_match_data_is_excluded'),
    ]

    operations = [
        migrations.AddField(
            model_name='teams',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
    ]
