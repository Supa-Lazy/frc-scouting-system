from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hours_app', '0007_alter_checkinout_check_in_time_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[('member', 'Member'), ('lead', 'Lead'), ('mentor', 'Mentor')],
                    default='member',
                    max_length=20,
                )),
                ('subteams', models.CharField(blank=True, default='', max_length=200)),
                ('onboarding_complete', models.BooleanField(default=False)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='hours_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.CreateModel(
            name='Badge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('badge_type', models.CharField(
                    choices=[
                        ('cad_trained', 'CAD Trained'),
                        ('programming_trained', 'Programming Trained'),
                        ('lathe_trained', 'Lathe Trained'),
                        ('cnc_trained', 'CNC Trained'),
                        ('mill_trained', 'Mill Trained'),
                        ('electrical_trained', 'Electrical Trained'),
                    ],
                    max_length=50,
                )),
                ('awarded_at', models.DateTimeField(auto_now_add=True)),
                ('awarded_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='badges_awarded',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='hours_badges',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'unique_together': {('user', 'badge_type')},
            },
        ),
    ]
