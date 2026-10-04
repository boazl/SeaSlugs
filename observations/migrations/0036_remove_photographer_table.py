# Step 3 of 3: the data now lives in the user foreign key -- drop the free-text credit, the
# Photographer lookup column and the Photographer table itself, and give the user foreign key
# its permanent name, DiveTrip.photographer.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0035_divetrip_photographer_to_users'),
    ]

    operations = [
        migrations.RemoveField(model_name='divetrip', name='photographer_fk'),
        migrations.RemoveField(model_name='divetrip', name='photographer'),
        migrations.DeleteModel(name='Photographer'),
        migrations.RenameField(model_name='divetrip', old_name='photographer_user', new_name='photographer'),
    ]
