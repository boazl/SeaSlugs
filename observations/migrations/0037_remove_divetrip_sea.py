# Step 2 of 2: a trip's sea is its region's sea -- drop DiveTrip.sea.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0036_give_sea_only_trips_a_region'),
    ]

    operations = [
        migrations.RemoveField(model_name='divetrip', name='sea'),
    ]
