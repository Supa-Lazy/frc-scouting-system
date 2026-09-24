import os

from django.db import migrations


def _seed_emails():
    """
    Initial admin accounts, read from the environment.

    Set SEED_AUTHORIZED_EMAILS to a comma-separated list before migrating a
    fresh database, e.g.

        SEED_AUTHORIZED_EMAILS="you@example.com,teammate@example.com"

    Left unset, nothing is seeded and the first account is added through the
    Django admin instead. A roster does not belong in version control, so
    there is deliberately no default list here.
    """
    raw = os.environ.get('SEED_AUTHORIZED_EMAILS', '')
    return [email.strip() for email in raw.split(',') if email.strip()]


def seed_authorized_users(apps, schema_editor):
    AuthorizedUser = apps.get_model('authenticate', 'AuthorizedUser')
    for email in _seed_emails():
        AuthorizedUser.objects.get_or_create(email=email)


def unseed_authorized_users(apps, schema_editor):
    AuthorizedUser = apps.get_model('authenticate', 'AuthorizedUser')
    for email in _seed_emails():
        AuthorizedUser.objects.filter(email=email).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('authenticate', '0002_sitesettings'),
    ]

    operations = [
        migrations.RunPython(seed_authorized_users, reverse_code=unseed_authorized_users),
    ]
