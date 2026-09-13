from django.db import migrations


def permissions(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    for action in ('add', 'change', 'view', 'delete'):
        Permission.objects.filter(content_type__app_label='observations', codename=f'{action}_observation').update(codename=f'{action}_sample')


class Migration(migrations.Migration):
    dependencies = [('observations', '0001_initial')]
    operations = [
        migrations.RenameModel('Observation', 'Sample'),
        migrations.RunPython(permissions, migrations.RunPython.noop),
    ]
