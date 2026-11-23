"""Owner's rule (correcting migration 0126): a species numbered by a paper carries the plain number -- "Thuridilla sp. 4",
"Thuridilla sp. 7" -- and its source is shown as "(Source: Martín-Hervás et al., 2021)"; "(2021)" never appears in a name.

- Observation #195 (Romblon, deleted, no media) was filed under a sourceless "Thuridilla sp. 4"; the owner identifies it
  as Thuridilla gracilis: it moves there (it stays deleted). The sourceless row, then empty, is deleted (its issues, if
  any, point at the paper's species).
- "Thuridilla sp. 4 (2021)" -> "Thuridilla sp. 4", "Thuridilla sp. 7 (2021)" -> "Thuridilla sp. 7" (same rows; the cards
  keep their slugs).
- Texts (species pages, observation notes, the decisions of issues #38 / #39): the site's own paper species lose
  "(2021)"; another of the paper's numbers mentioned in a text says it is the paper's ("Thuridilla sp. 8 של המאמר" /
  "Thuridilla sp. 8 of the paper"); the sp. 7 description warns against the book's sp. 7 instead of explaining "(2021)".
Safe in both environments: found by name / transfer id, done only where still needed."""
import re

from django.db import migrations

SOURCE = 'Martín-Hervás et al., 2021'
GRACILIS_SAMPLE = '0ceb5474-0a30-4bb7-ab36-fe8c517bc67f'
RENAMES = {'Thuridilla sp. 4 (2021)': ('Thuridilla sp. 4', 'sp. 4'), 'Thuridilla sp. 7 (2021)': ('Thuridilla sp. 7', 'sp. 7')}
OWN = {'2', '4', '7'}   # the paper's numbers that are species of the site
SAMPLES = ['450a994b-828f-4eeb-993a-055d62d5d8a3', '51367669-3422-47d7-8a8d-feb01fe2b501',
           'f83b17d0-9348-4d7d-af8b-b1ba5955602d']
ISSUES = ['4f19052c-d638-52be-8a82-cbdb298aa266', '7d8eec0e-7c86-5706-8597-36df4ba4ba71']
SENTENCES = {
    'הסימון (2021) מבדיל אותו מ־Thuridilla sp. 7 של ספר ההגדרה': 'אין לבלבל אותו עם Thuridilla sp. 7 של ספר ההגדרה',
    '"(2021)" tells it apart from Thuridilla sp. 7 of Gosliner': 'not to be confused with Thuridilla sp. 7 of Gosliner',
}
TEXT_FIELDS = ['description_he', 'description_en', 'identification_he', 'identification_en', 'similar_species_he',
               'similar_species_en']


def plain(text, english):
    for old, new in SENTENCES.items():
        text = text.replace(old, new)
    def repl(m):
        if m.group(1) in OWN:
            return f'sp. {m.group(1)}'
        return f'sp. {m.group(1)} of the paper' if english else f'sp. {m.group(1)} של המאמר'
    return re.sub(r'sp\. (\d+) \(2021\)', repl, text)


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    Publication = apps.get_model('observations', 'SpeciesPublicationName')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    gracilis = Species.objects.filter(scientific_name='Thuridilla gracilis').first()
    stray = Species.objects.filter(scientific_name='Thuridilla sp. 4').exclude(name_source=SOURCE).first()
    if stray is not None and gracilis is not None:
        Sample.objects.filter(transfer_id=GRACILIS_SAMPLE, species_id=stray.pk).update(species_id=gracilis.pk)
    paper4 = Species.objects.filter(scientific_name='Thuridilla sp. 4 (2021)').first()
    if stray is not None and not Sample.objects.filter(species_id=stray.pk).exists() \
            and not SpeciesArea.objects.filter(species_id=stray.pk).exists() \
            and not Publication.objects.filter(species_id=stray.pk).exists():
        if paper4 is not None:
            for field in ('species', 'second_species', 'corrected_species'):
                Issue.objects.filter(**{f'{field}_id': stray.pk}).update(**{f'{field}_id': paper4.pk})
        stray.delete()
    for old, (new, epithet) in RENAMES.items():
        sp = Species.objects.filter(scientific_name=old).first()
        if sp is None or Species.objects.filter(scientific_name=new).exists():
            continue
        sp.scientific_name, sp.species, sp.name_source = new, epithet, SOURCE
        sp.save()
    for sp in Species.objects.filter(genus='Thuridilla'):
        changed = False
        for field in TEXT_FIELDS:
            value = getattr(sp, field)
            new = plain(value, field.endswith('_en'))
            if new != value:
                setattr(sp, field, new); changed = True
        if changed: sp.save()
    for sample in Sample.objects.filter(transfer_id__in=SAMPLES):
        Sample.objects.filter(pk=sample.pk).update(note_he=plain(sample.note_he, False), note_en=plain(sample.note_en, True))
    for issue in Issue.objects.filter(transfer_id__in=ISSUES):
        new = plain(issue.decision, False)
        if new != issue.decision:
            issue.decision = new
            issue.save()


class Migration(migrations.Migration):
    dependencies = [('observations', '0126_thuridilla_2021_numbers')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
