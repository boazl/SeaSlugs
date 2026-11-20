"""The source of the name of the owner's own marked species -- "Genus sp. A", "sp. B" (his marks for animals that look
like one species): the site observation that defines it, as "SeaSlugs.org.il observation: <photographer>, <region>,
<year>" -- the earliest published observation of the species (the same rule as Species.site_source; in the admin,
the species action "מקור השם מהתצפית הראשונה באתר" does the same for any marked species).
A bare "Genus sp." (unidentified) gets nothing; a source already set is never replaced. Safe in both environments.
"""
import re

from django.db import migrations

LETTER_MARK = re.compile(r'^sp\.\s*[A-Z]$')


def forward(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    Profile = apps.get_model('observations', 'Profile')
    for species in Species.objects.filter(species__startswith='sp.', name_source=''):
        if not LETTER_MARK.match(species.species.strip()):
            continue
        samples = list(Sample.objects.filter(species=species, kind='species', status='published', deleted_at__isnull=True)
                       .select_related('trip__region', 'owner'))
        if not samples:
            continue
        first = min(samples, key=lambda s: (s.trip.year or 9999, s.trip.month or 13, s.trip.start_day or 99, s.pk))
        owner, trip = first.owner, first.trip
        name = ''
        if owner is not None:
            profile = Profile.objects.filter(user=owner).first()
            name = f'{profile.first_name_en} {profile.last_name_en}'.strip() if profile else ''
            name = name or f'{owner.first_name} {owner.last_name}'.strip()
        region = (trip.region.name_en or trip.region.name) if trip.region_id else ''
        parts = [name, region, str(trip.year or '')]
        species.name_source = 'SeaSlugs.org.il observation: ' + ', '.join(p for p in parts if p)
        species.save(update_fields=['name_source'])


class Migration(migrations.Migration):
    dependencies = [('observations', '0110_sp_name_sources')]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
