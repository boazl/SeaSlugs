"""Owner's decision (issue #38): the Romblon observation #234, filed as the paper's Thuridilla sp. 4 with cf., is
Thuridilla gracilis (Risbec, 1928) -- after Martín-Hervás et al. 2021 a dark body with fine cream lines, an orange inner
parapodial stripe, sometimes diffuse light blue spots, orange-tipped rhinophores. It moves to T. gracilis (same row and
transfer id) without cf. and without the cf. note, and joins T. gracilis's Philippines card; its old card, left empty,
is deleted, and its published URL redirects there (historical_species_redirects.json). The paper's Thuridilla sp. 4
stays in the catalogue without observations. The issue's decision records the change. Safe in both environments."""
import importlib

from django.db import migrations

SAMPLE = '450a994b-828f-4eeb-993a-055d62d5d8a3'
ISSUE = '4f19052c-d638-52be-8a82-cbdb298aa266'
OLD_SLUG = 'thuridilla-sp-4-2021-phillipines-indo-pacific-south-china-sea'
ADDED = ("עדכון (מיגרציה 0129, החלטת הבעלים): תצפית #234 היא Thuridilla gracilis (Risbec, 1928), בלי cf.; הכרטיס הישן שלה "
         "מפנה לכרטיס של T. gracilis בפיליפינים. הכיתוב בתמונה של #234: 'Thuridilla gracilis' ובשורה השנייה '(Risbec, 1928)'.")


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    gracilis = Species.objects.filter(scientific_name='Thuridilla gracilis').first()
    sample = Sample.objects.filter(transfer_id=SAMPLE).first()
    if gracilis is None or sample is None or sample.species_id == gracilis.pk:
        return
    old_species = sample.species_id
    changes = {'species_id': gracilis.pk}
    if sample.identification_qualifier == 'cf.': changes['identification_qualifier'] = ''
    if sample.note_he.startswith('זיהוי לא ודאי (cf.)'): changes['note_he'] = ''
    if sample.note_en.startswith('Uncertain identification (cf.)'): changes['note_en'] = ''
    Sample.objects.filter(pk=sample.pk).update(**changes)
    old_area = SpeciesArea.objects.filter(slug=OLD_SLUG, species_id=old_species).first()
    if old_area is not None and not Sample.objects.filter(species_id=old_species, deleted_at__isnull=True).exists():
        old_area.delete()
    issue = Issue.objects.filter(transfer_id=ISSUE).first()
    if issue is not None and ADDED not in issue.decision:
        issue.decision = f'{issue.decision}\n{ADDED}'.strip()
        issue.save()
    importlib.import_module('observations.migrations.0071_defining_samples_one_level_below').fix(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('observations', '0128_thuridilla_sp7_without_cf')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
