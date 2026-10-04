# Step 2 of 2: scientific_name is derived from genus + species and no longer typed by hand.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0038_species_name_from_genus_and_species'),
    ]

    operations = [
        migrations.AlterField(
            model_name='species',
            name='scientific_name',
            field=models.CharField(db_index=True, editable=False, max_length=200, verbose_name='שם מדעי (נגזר מסוג + מין)'),
        ),
    ]
