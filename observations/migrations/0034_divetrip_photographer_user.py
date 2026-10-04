# Step 1 of 3 replacing the Photographer lookup table with the Users table: add the new
# nullable user foreign key under a temporary name. (Split into three migrations so each
# one is either pure schema or pure data -- PostgreSQL refuses to mix the two in a single
# transaction.)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('observations', '0033_species_size_from_species_size_max_species_size_to'),
    ]

    operations = [
        migrations.AddField(
            model_name='divetrip',
            name='photographer_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='photographed_trips', to=settings.AUTH_USER_MODEL, verbose_name='צלם'),
        ),
    ]
