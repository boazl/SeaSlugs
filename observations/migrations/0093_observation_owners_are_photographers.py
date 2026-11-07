from django.db import migrations

# Not every member is a photographer: the photographers are the "Macro photographer" group (observations/
# photographers.py). Everyone who already has an observation is one, so they join it.
GROUP = 'Macro photographer'


def add_owners(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Group = apps.get_model('auth', 'Group')
    Sample = apps.get_model('observations', 'Sample')
    group, _ = Group.objects.get_or_create(name=GROUP)
    for user in User.objects.filter(pk__in=Sample.objects.filter(deleted_at__isnull=True).values('owner_id')):
        user.groups.add(group)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0092_guest_photographers_group'),
    ]

    operations = [
        migrations.RunPython(add_owners, migrations.RunPython.noop),
    ]
