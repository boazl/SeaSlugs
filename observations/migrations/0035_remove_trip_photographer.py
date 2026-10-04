# Step 2 of 2: a trip has no photographer of its own any more (the photographer of an
# observation is its creator), so drop the free-text credit, the Photographer lookup
# column and the Photographer table itself.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0034_assign_trip_samples_to_trip_photographer'),
    ]

    operations = [
        migrations.RemoveField(model_name='divetrip', name='photographer_fk'),
        migrations.RemoveField(model_name='divetrip', name='photographer'),
        migrations.DeleteModel(name='Photographer'),
    ]
