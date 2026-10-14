"""Defining samples descend past an empty level: an order with no family observation (with a photo or
video) takes a genus observation, then a species one; a family with no genus observation takes a
species one. Re-runs 0071's fix -- which now applies that rule -- on databases 0071 already ran on."""
import importlib
from django.db import migrations

_fix = importlib.import_module('observations.migrations.0071_defining_samples_one_level_below').fix


class Migration(migrations.Migration):
    dependencies = [('observations', '0071_defining_samples_one_level_below')]
    operations = [migrations.RunPython(_fix, migrations.RunPython.noop)]
