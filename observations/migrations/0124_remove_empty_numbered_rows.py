"""After migration 0123 moved their observations, cards, texts and guide names to the described species, the numbered
catalogue rows "Goniodoridella sp. 8" (= Murphydoris cobbi) and "Eubranchus sp. 26" (= Longibranchus putnami) are empty
duplicates; the owner approved deleting them. A row is deleted only while nothing points at it (no observation, card or
name in a publication); its identification issues are first pointed at the described species, keeping the old name in
the issue's notes. Safe in both environments: found by name, done only where still needed."""
from django.db import migrations

ROWS = {'Goniodoridella sp. 8': 'Murphydoris cobbi', 'Eubranchus sp. 26': 'Longibranchus putnami'}


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    Publication = apps.get_model('observations', 'SpeciesPublicationName')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    for old_name, new_name in ROWS.items():
        old = Species.objects.filter(scientific_name=old_name).first()
        new = Species.objects.filter(scientific_name=new_name).first()
        if old is None or new is None or Sample.objects.filter(species_id=old.pk).exists() \
                or SpeciesArea.objects.filter(species_id=old.pk).exists() or Publication.objects.filter(species_id=old.pk).exists():
            continue
        note = f'השם במהדורה השנייה: {old_name}.'
        for field in ('species', 'second_species', 'corrected_species'):
            for issue in Issue.objects.filter(**{f'{field}_id': old.pk}):
                setattr(issue, f'{field}_id', new.pk)
                if old_name not in issue.notes:
                    issue.notes = f'{issue.notes}\n{note}'.strip()
                issue.save()
        old.delete()


class Migration(migrations.Migration):
    dependencies = [('observations', '0123_described_book_species')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
