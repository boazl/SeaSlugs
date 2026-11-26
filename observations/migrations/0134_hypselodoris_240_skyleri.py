"""Owner's decision (issue #9): the Anilao observation #240 filed as Hypselodoris carnea (western Indian Ocean; white
lines, black spots, a continuous purple margin, red gill and rhinophores) is Hypselodoris skyleri Gosliner & R. F.
Johnson, 2018 (brown longitudinal lines, opaque white dots, separate purple spots along the margin -- 3rd edition of
Gosliner, Valdés & Behrens, p. 215), like observation #78 already on the site. It moves in place (same row and transfer
id) and joins H. skyleri's Philippines card; the emptied H. carnea card is deleted and its URL redirects there
(historical_species_redirects.json). H. carnea stays in the catalogue. The issue is decided: observation and catalogue
done, photo label to fix. Safe in both environments, done once."""
import importlib

from django.db import migrations

SAMPLE = 'dbf76ae2-78de-4079-a994-2349e52fa85d'
ISSUE = 'bea4f09f-26d0-54d0-9a0f-f01585bc9377'
OLD_SLUG = 'hypselodoris-carnea-phillipines-indo-pacific-south-china-sea'
DECISION = ("הוחלט: #240 היא Hypselodoris skyleri Gosliner & R. F. Johnson, 2018 (מהדורה 3, עמ' 215), כמו #78. בוצע במיגרציה "
            "0134: התצפית הצטרפה לכרטיס של H. skyleri בפיליפינים, והכרטיס של H. carnea מפנה אליו. נותר: הכיתוב בתמונה – "
            "'Hypselodoris skyleri Gosliner & R. F. Johnson, 2018'.")


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    skyleri = Species.objects.filter(scientific_name='Hypselodoris skyleri').first()
    sample = Sample.objects.filter(transfer_id=SAMPLE, species__scientific_name='Hypselodoris carnea').first()
    if skyleri is None or sample is None:
        return
    old = sample.species_id
    Sample.objects.filter(pk=sample.pk).update(species_id=skyleri.pk)
    area = SpeciesArea.objects.filter(slug=OLD_SLUG, species_id=old).first()
    if area is not None and not Sample.objects.filter(species_id=old, deleted_at__isnull=True).exists():
        if SpeciesArea.objects.filter(species_id=skyleri.pk, country_id=area.country_id, sea_id=area.sea_id,
                                      undetermined_variant=area.undetermined_variant).exists():
            area.delete()
        else:
            SpeciesArea.objects.filter(pk=area.pk).update(species_id=skyleri.pk)
    issue = Issue.objects.filter(transfer_id=ISSUE, status__in=('open', 'checking')).first()
    if issue is not None:
        if not issue.decision.strip(): issue.decision = DECISION
        issue.status = 'decided'
        issue.corrected_species_id = skyleri.pk
        issue.action_observation = issue.action_catalog = 'done'
        issue.action_photo = issue.action_photo or 'needed'
        issue.save()
    importlib.import_module('observations.migrations.0071_defining_samples_one_level_below').fix(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('observations', '0133_phyllidia_png_reviews')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
