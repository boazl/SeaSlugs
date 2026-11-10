"""The "Macro diver" group and the profile's "interested in finding macro diving partners" tick agree (a member is
listed as a partner only with both; models._sync_macro_diver keeps them together from now on): a tick without the
group -- a manager removed the member from the group -- is unticked, and the group is removed from members who did not
tick. The groups that had no use on the site (New user, Subscriber, Artist) are deleted."""
from django.db import migrations

UNUSED_GROUPS = ('New user', 'Subscriber', 'Artist')


def forwards(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Profile = apps.get_model('observations', 'Profile')
    group = Group.objects.filter(name='Macro diver').first()
    in_group = set(group.user_set.values_list('pk', flat=True)) if group else set()
    Profile.objects.filter(macro_diver=True).exclude(user_id__in=in_group).update(macro_diver=False)
    if group:
        ticked = set(Profile.objects.filter(macro_diver=True).values_list('user_id', flat=True))
        for user_id in in_group - ticked:
            group.user_set.remove(user_id)
    Group.objects.filter(name__in=UNUSED_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0098_profile_must_change_password'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
