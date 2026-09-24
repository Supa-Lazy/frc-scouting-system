from django.db import migrations, models


def copy_role_to_roles(apps, schema_editor):
    AuthorizedUser = apps.get_model('authenticate', 'AuthorizedUser')
    for user in AuthorizedUser.objects.all():
        user.roles = user.role or 'student'
        user.save(update_fields=['roles'])


class Migration(migrations.Migration):

    dependencies = [
        ('authenticate', '0005_alter_sitesettings_logo_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='authorizeduser',
            name='roles',
            field=models.CharField(default='student', max_length=200),
        ),
        migrations.RunPython(copy_role_to_roles, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='authorizeduser',
            name='role',
        ),
    ]
