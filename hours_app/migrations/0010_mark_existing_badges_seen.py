from django.db import migrations, models


def mark_existing_seen(apps, schema_editor):
    """Backfill seen_at on badges that existed before the award reveal shipped.

    seen_at is what gates the one-time earn animation. Leaving it null on
    historical badges would show every member a modal for each badge they
    already hold the next time they open the dashboard, which reads as a bug
    rather than a celebration. Only awards made from here on should reveal.
    """
    Badge = apps.get_model('hours_app', 'Badge')
    Badge.objects.filter(seen_at__isnull=True).update(seen_at=models.F('awarded_at'))


def unmark(apps, schema_editor):
    Badge = apps.get_model('hours_app', 'Badge')
    Badge.objects.update(seen_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('hours_app', '0009_badge_seen_at_userprofile_about_and_more'),
    ]

    operations = [
        migrations.RunPython(mark_existing_seen, unmark),
    ]
