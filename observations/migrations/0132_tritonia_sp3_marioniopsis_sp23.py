"""Owner's decisions (issues #40 and #89):
- Tritonia sp. 3 of the 2nd edition of Gosliner, Valdés & Behrens (p. 257) is Marioniopsis sp. 23 of the 3rd (p. 284,
  word-for-word the same description): renamed in place, as in migration 0122 -- same species row, observation (genus
  updated, same transfer id) and card slug; name source NSSI-3; texts give the 2nd-edition name; identification from
  the book; the 3rd-edition name and page as the species' name in that publication.
- With it the site has no observation of a Tritonia species left; the genus observation #336 ("genera-tritonia.jpg",
  an animal like the former Tritonia sp. 4, now Marioniopsis sp. 6) is deleted (soft, reversible), so the genus leaves
  the gallery. The genus row and its catalogue species stay.
Issues: #40 decided (catalogue done, photo label to fix); #89 fixed when it is here (on the live site it arrives with
the identissues transfer). Defining samples are repaired (0071's rule). Safe in both environments, done once."""
import importlib

from django.db import migrations
from django.utils import timezone

NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'
NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'
NSSI3_SLUG = 'nssi-3-gosliner-valdes-behrens-2026'
NSSI3_CITATION = ('Gosliner, T. M., Valdés, Á. & Behrens, D. W. (2026). Nudibranch & Sea Slug Identification – '
                  'Indo-Pacific, 3rd ed. New World Publications.')
NSSI2_CITATION = ('Gosliner, T. M., Valdés, Á. & Behrens, D. W. (2018). Nudibranch & Sea Slug Identification – '
                  'Indo-Pacific, 2nd ed. New World Publications.')
GENUS_OBSERVATION = 'e171f6a1-c869-40a6-b826-7fb564053596'
ISSUE_40 = 'a93fa741-070c-50ce-9411-58cccaa8176d'
ISSUE_89 = 'e4ff51bb-6ddd-4880-9115-c936b6904261'
TEXTS = dict(
    description_he='מין שטרם תואר רשמית מהסוג Marioniopsis (משפחת Tritoniidae), המופיע במהדורה השלישית של ספר ההגדרה של '
                   'Gosliner, Valdés ו־Behrens (2026) בשם Marioniopsis sp. 23; במהדורה השנייה (2018) הופיע בשם Tritonia sp. 3. '
                   'חשופיות עם זימים מסועפים לאורך שולי הגב ופרגוד פה עם מחושים.',
    description_en='An undescribed species of Marioniopsis (Tritoniidae), listed as Marioniopsis sp. 23 in the 3rd edition of '
                   'Gosliner, Valdés & Behrens (2026), Nudibranch & Sea Slug Identification – Indo-Pacific; the 2nd edition '
                   '(2018) lists it as Tritonia sp. 3. Nudibranchs with branched gills along the edges of the back and an oral '
                   'veil with tentacles.',
    identification_he='חום מנומר; זימים משניים מסועפים במידה בינונית, עם קצוות חומים כהים; מחושי הפרגוד פשוטים או מפוצלים. '
                      'ניזון מהאלמוג הרך החום Paralemnalia ודומה לו מאוד. אורך כ־15 מ״מ. הפיליפינים. (לפי Gosliner, Valdés & '
                      'Behrens 2026, מהדורה 3, עמ׳ 284, בשם Marioniopsis sp. 23; Gosliner, Valdés & Behrens 2018, מהדורה 2, עמ׳ 257, '
                      'בשם Tritonia sp. 3)',
    identification_en='Mottled brown; secondary gills moderately branched, with dark brown tips; velar tentacles simple or bifid. '
                      'Feeds on the brownish soft coral Paralemnalia, which it closely resembles. About 15 mm. Philippines. '
                      '(after Gosliner, Valdés & Behrens 2026, 3rd ed., p. 284, as Marioniopsis sp. 23; Gosliner, Valdés & '
                      'Behrens 2018, 2nd ed., p. 257, as Tritonia sp. 3)',
)
DECISION_40 = ('הוחלט: Marioniopsis sp. 23 (מהדורה 3, עמ׳ 284) — שם המין במקום, מקור המהדורה השלישית. בוצע במיגרציה 0132. '
               "נותר: הכיתוב בתמונה של #219 — 'Marioniopsis sp. 23' ובשורה השנייה 'Source: Gosliner, Valdés & Behrens, 2026'.")
DECISION_89 = 'הוחלט: תצפית הסוג #336 נמחקה (מחיקה רכה, הפיכה); הסוג Tritonia יצא מהגלריה. בוצע במיגרציה 0132.'


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    Article = apps.get_model('observations', 'Article')
    Publication = apps.get_model('observations', 'SpeciesPublicationName')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    sp = Species.objects.filter(scientific_name='Tritonia sp. 3').first()
    if sp is not None and not Species.objects.filter(scientific_name='Marioniopsis sp. 23').exists():
        sp.scientific_name, sp.genus, sp.species = 'Marioniopsis sp. 23', 'Marioniopsis', 'sp. 23'
        if sp.accepted_genus == 'Tritonia': sp.accepted_genus = 'Marioniopsis'
        if sp.accepted_species: sp.accepted_species = 'sp. 23'
        if sp.name_source in ('', NSSI2): sp.name_source = NSSI3
        if sp.description_he.startswith('מין שטרם תואר רשמית מהסוג Tritonia'): sp.description_he = TEXTS['description_he']
        if sp.description_en.startswith('An undescribed species of Tritonia'): sp.description_en = TEXTS['description_en']
        for field in ('identification_he', 'identification_en'):
            if not getattr(sp, field): setattr(sp, field, TEXTS[field])
        sp.sources = '\n'.join(['https://www.marinespecies.org/aphia.php?p=taxdetails&id=456341', NSSI3_CITATION, NSSI2_CITATION])
        sp.save()
        nssi3 = Article.objects.filter(slug=NSSI3_SLUG).first()
        if nssi3 is not None:
            if not Publication.objects.filter(species_id=sp.pk, article_id=nssi3.pk).exists():
                Publication.objects.create(species_id=sp.pk, article_id=nssi3.pk, name='Marioniopsis sp. 23', pages='284')
            sp.articles.add(nssi3)
        Sample.objects.filter(species_id=sp.pk, genus='Tritonia').update(genus='Marioniopsis')
        issue = Issue.objects.filter(transfer_id=ISSUE_40, status__in=('open', 'checking')).first()
        if issue is not None:
            if not issue.decision.strip(): issue.decision = DECISION_40
            issue.status = 'decided'
            issue.corrected_species_id = sp.pk
            issue.action_catalog = 'done'
            issue.action_photo = issue.action_photo or 'needed'
            issue.save()
    genus_obs = Sample.objects.filter(transfer_id=GENUS_OBSERVATION, deleted_at__isnull=True).first()
    if genus_obs is not None:
        Sample.objects.filter(pk=genus_obs.pk).update(deleted_at=timezone.now())
        issue = Issue.objects.filter(transfer_id=ISSUE_89, status__in=('open', 'checking')).first()
        if issue is not None:
            if not issue.decision.strip(): issue.decision = DECISION_89
            issue.status = 'fixed'
            issue.fixed_on = timezone.localdate()
            issue.action_observation = 'done'
            issue.action_photo = ''
            issue.save()
    importlib.import_module('observations.migrations.0071_defining_samples_one_level_below').fix(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('observations', '0131_species_original_genus')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
