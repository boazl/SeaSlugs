from django.db import migrations

# The existing guest photographers (inactive users -- the former photographer table, migration 0034) become
# photographers a manager can add observations for (observations/photographers.py).
GROUP = 'Macro photographer'


def add_guests(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Group = apps.get_model('auth', 'Group')
    group, _ = Group.objects.get_or_create(name=GROUP)
    for user in User.objects.filter(is_active=False):
        user.groups.add(group)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('observations', '0091_dailyvisitor_country_views'),
    ]

    operations = [
        migrations.RunPython(add_guests, migrations.RunPython.noop),
    ]
