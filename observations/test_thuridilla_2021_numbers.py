from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Article, Country, DiveTrip, IdentificationIssue, Region, Sample, Sea, Species, SpeciesArea

migration = import_module('observations.migrations.0126_thuridilla_2021_numbers')
ROMBLON_7, SOLOMON, ROMBLON_4 = ('51367669-3422-47d7-8a8d-feb01fe2b501', 'f83b17d0-9348-4d7d-af8b-b1ba5955602d',
                                 '450a994b-828f-4eeb-993a-055d62d5d8a3')
ISSUE_38, ISSUE_39 = list(migration.ISSUES)


class Thuridilla2021NumbersTests(TestCase):
    """Migration 0126 (owner's decisions on issues #38, #39; Martín-Hervás et al. 2021): the book's "Thuridilla sp. 7"
    row becomes Thuridilla sp. 7 (2021) with the paper as its source (the "(2021)" exception tells the paper's numbers
    from the book's); the Solomon Islands observation filed as T. ratna moves to it with its card (same rows, transfer
    ids, slug); both observations, and the Romblon Thuridilla sp. 4 (2021), get cf. and a note; sp. 2 / sp. 4 (2021) /
    sp. 7 (2021) get identification texts from the paper (only where empty) and cite it by its real title; the issues
    are "decided" with catalogue and observations done and the photo labels to fix. Runs once."""

    def setUp(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sb = Country.objects.create(name='איי שלמה', name_en='Solomon Islands')
        scs = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        sol = Sea.objects.create(name='ים שלמה', name_en='Solomon Sea', url_code='sol')
        v = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph,
                                    region=Region.objects.create(name='Romblon', country=ph, sea=scs))
        g = DiveTrip.objects.create(code='G', title='g', year=2023, month=1, country=sb,
                                    region=Region.objects.create(name='Gizo', country=sb, sea=sol))
        self.paper = Article.objects.create(slug=migration.PAPER_SLUG, title_he='Thuridilla')
        self.sp7 = Species.objects.create(scientific_name='Thuridilla sp. 7', genus='Thuridilla', species='sp. 7',
                                          name_source='NSSI-2', description_he='ספר.', sources='x')
        self.ratna = Species.objects.create(scientific_name='Thuridilla ratna', genus='Thuridilla', species='ratna',
                                            author='(Er. Marcus, 1965)')
        self.sp4 = Species.objects.create(scientific_name='Thuridilla sp. 4 (2021)', genus='Thuridilla',
                                          species='sp. 4 (2021)', identification_he='קיים', sources='old')
        self.samples = {}
        for n, (transfer, species, trip) in enumerate(((ROMBLON_7, self.sp7, v), (SOLOMON, self.ratna, g),
                                                       (ROMBLON_4, self.sp4, v)), 1):
            sample = Sample(owner=owner, species=species, trip=trip, video_url=f'https://youtu.be/3000000000{n}')
            sample.save_reviewed()
            Sample.objects.filter(pk=sample.pk).update(transfer_id=transfer)
            self.samples[transfer] = sample.pk
        SpeciesArea.objects.filter(species=self.ratna).update(defining_sample_id=self.samples[SOLOMON])
        self.solomon_area = SpeciesArea.objects.get(species=self.ratna)
        self.i38 = IdentificationIssue.objects.create(kind='other', status='open', transfer_id=ISSUE_38)
        self.i39 = IdentificationIssue.objects.create(kind='misidentified', status='checking', species=self.sp7,
                                                      corrected_species=self.ratna, transfer_id=ISSUE_39)

    def test_decisions(self):
        migration.forwards(apps, None)
        migration.forwards(apps, None)
        sp7 = Species.objects.get(pk=self.sp7.pk)
        self.assertEqual((sp7.scientific_name, sp7.species, sp7.name_source),
                         ('Thuridilla sp. 7 (2021)', 'sp. 7 (2021)', migration.SOURCE))
        self.assertIn('מין אחר', sp7.description_he)
        self.assertIn('פס לבן רחב', sp7.identification_he)
        self.assertEqual(sp7.sources, f'{migration.WORMS}\n{migration.CITATION}')
        self.assertEqual(list(sp7.articles.all()), [self.paper])
        solomon = Sample.objects.get(pk=self.samples[SOLOMON])
        self.assertEqual((solomon.species_id, solomon.identification_qualifier), (sp7.pk, 'cf.'))
        self.assertIn('T. ratna', solomon.note_he)
        area = SpeciesArea.objects.get(pk=self.solomon_area.pk)
        self.assertEqual((area.species_id, area.slug), (sp7.pk, self.solomon_area.slug))
        self.assertEqual(Sample.objects.get(pk=self.samples[ROMBLON_7]).identification_qualifier, 'cf.')
        romblon4 = Sample.objects.get(pk=self.samples[ROMBLON_4])
        self.assertEqual((romblon4.species_id, romblon4.identification_qualifier), (self.sp4.pk, 'cf.'))
        sp4 = Species.objects.get(pk=self.sp4.pk)
        self.assertEqual(sp4.identification_he, 'קיים')
        self.assertIn('T. bayeri', sp4.similar_species_he)
        self.assertIn('Cladistics 37(6)', sp4.sources)
        i39 = IdentificationIssue.objects.get(pk=self.i39.pk)
        self.assertEqual((i39.status, i39.corrected_species_id, i39.second_observation_id, i39.action_photo),
                         ('decided', sp7.pk, self.samples[SOLOMON], 'needed'))
        self.assertIn('(Source: Martín-Hervás et al., 2021)', IdentificationIssue.objects.get(pk=self.i38.pk).decision)


class ThuridillaPaperNumbersPlainTests(TestCase):
    """Migration 0127 (owner's rule): a paper-numbered species has the plain number ("Thuridilla sp. 4") with the
    paper as its source -- "(2021)" never appears in a name; texts mentioning the site's paper species drop it, other
    paper numbers say "of the paper"; observation #195 moves from the sourceless "Thuridilla sp. 4" to T. gracilis
    (staying deleted) and the emptied row is deleted."""

    plain = import_module('observations.migrations.0127_thuridilla_paper_numbers_plain')

    def test_plain_numbers(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        trip = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph,
                                       region=Region.objects.create(name='Romblon', country=ph, sea=sea))
        gracilis = Species.objects.create(scientific_name='Thuridilla gracilis', genus='Thuridilla', species='gracilis')
        stray = Species.objects.create(scientific_name='Thuridilla sp. 4', genus='Thuridilla', species='sp. 4')
        sp4 = Species.objects.create(scientific_name='Thuridilla sp. 4 (2021)', genus='Thuridilla', species='sp. 4 (2021)',
                                     similar_species_en='Thuridilla sp. 8 (2021) has many blue spots.',
                                     description_he='בשם Thuridilla sp. 4 (2021) ברביזיה')
        sp7 = Species.objects.create(scientific_name='Thuridilla sp. 7 (2021)', genus='Thuridilla', species='sp. 7 (2021)',
                                     description_he='מכלול; הסימון (2021) מבדיל אותו מ־Thuridilla sp. 7 של ספר ההגדרה שלהם.')
        lost = Sample(owner=owner, species=stray, trip=trip, video_url='https://youtu.be/30000000001')
        lost.save_reviewed()
        from django.utils import timezone
        Sample.objects.filter(pk=lost.pk).update(transfer_id=self.plain.GRACILIS_SAMPLE, deleted_at=timezone.now())
        SpeciesArea.objects.filter(species=stray).delete()   # as on the site: the deleted observation has no card
        self.plain.forwards(apps, None)
        self.plain.forwards(apps, None)
        self.assertEqual(Sample.objects.get(pk=lost.pk).species_id, gracilis.pk)
        self.assertFalse(Species.objects.filter(pk=stray.pk).exists())
        sp4.refresh_from_db(); sp7.refresh_from_db()
        self.assertEqual((sp4.scientific_name, sp4.species, sp4.name_source), ('Thuridilla sp. 4', 'sp. 4', self.plain.SOURCE))
        self.assertEqual(sp7.scientific_name, 'Thuridilla sp. 7')
        self.assertEqual(sp4.similar_species_en, 'Thuridilla sp. 8 of the paper has many blue spots.')
        self.assertEqual(sp4.description_he, 'בשם Thuridilla sp. 4 ברביזיה')
        self.assertEqual(sp7.description_he, 'מכלול; אין לבלבל אותו עם Thuridilla sp. 7 של ספר ההגדרה שלהם.')


class ThuridillaSp7WithoutCfTests(TestCase):
    """Migration 0128 (owner's decision on issue #39): the two Thuridilla sp. 7 observations drop cf.; the Romblon note
    written by 0126 goes, the Solomon note keeps why it is not T. ratna without the cf. opening; notes the owner changed
    are kept."""

    nocf = import_module('observations.migrations.0128_thuridilla_sp7_without_cf')

    def test_drops_cf(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        trip = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph,
                                       region=Region.objects.create(name='Romblon', country=ph, sea=sea))
        sp7 = Species.objects.create(scientific_name='Thuridilla sp. 7', genus='Thuridilla', species='sp. 7')
        rows = {}
        for n, transfer in enumerate((self.nocf.ROMBLON, self.nocf.SOLOMON), 1):
            sample = Sample(owner=owner, species=sp7, trip=trip if n == 1 else DiveTrip.objects.create(
                code='G', title='g', year=2023, month=1, country=ph, region=trip.region), video_url=f'https://youtu.be/3000000000{n}')
            sample.save_reviewed()
            (he_old, _), (en_old, _) = self.nocf.NOTES[transfer]
            Sample.objects.filter(pk=sample.pk).update(transfer_id=transfer, identification_qualifier='cf.',
                                                       note_he=he_old if n == 1 else 'שלי', note_en=en_old)
            rows[transfer] = sample.pk
        self.nocf.forwards(apps, None)
        romblon, solomon = Sample.objects.get(pk=rows[self.nocf.ROMBLON]), Sample.objects.get(pk=rows[self.nocf.SOLOMON])
        self.assertEqual((romblon.identification_qualifier, romblon.note_he, romblon.note_en), ('', '', ''))
        self.assertEqual((solomon.identification_qualifier, solomon.note_he), ('', 'שלי'))
        self.assertTrue(solomon.note_en.startswith('White rhinophores'))


class Thuridilla234GracilisTests(TestCase):
    """Migration 0129 (owner's decision on issue #38): observation #234 moves from the paper's Thuridilla sp. 4 to
    T. gracilis without cf. or its cf. note, joining T. gracilis's card in the same area; the emptied old card is
    deleted (its URL redirects, historical_species_redirects.json); the paper's species row stays; the issue records it."""

    move = import_module('observations.migrations.0129_thuridilla_234_gracilis')

    def test_moves_to_gracilis(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        region = Region.objects.create(name='Romblon', country=ph, sea=sea)
        c = DiveTrip.objects.create(code='C', title='c', year=2023, month=1, country=ph, region=region)
        v = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph, region=region)
        gracilis = Species.objects.create(scientific_name='Thuridilla gracilis', genus='Thuridilla', species='gracilis')
        sp4 = Species.objects.create(scientific_name='Thuridilla sp. 4', genus='Thuridilla', species='sp. 4')
        Sample(owner=owner, species=gracilis, trip=c, video_url='https://youtu.be/30000000001').save_reviewed()
        moved = Sample(owner=owner, species=sp4, trip=v, video_url='https://youtu.be/30000000002')
        moved.save_reviewed()
        Sample.objects.filter(pk=moved.pk).update(transfer_id=self.move.SAMPLE, identification_qualifier='cf.',
                                                  note_he='זיהוי לא ודאי (cf.): x', note_en='Uncertain identification (cf.): x')
        SpeciesArea.objects.filter(species=sp4).update(slug=self.move.OLD_SLUG)
        issue = IdentificationIssue.objects.create(kind='other', status='decided', decision='הוחלט.',
                                                   transfer_id=self.move.ISSUE)
        self.move.forwards(apps, None)
        self.move.forwards(apps, None)
        moved.refresh_from_db()
        self.assertEqual((moved.species_id, moved.identification_qualifier, moved.note_he, moved.note_en),
                         (gracilis.pk, '', '', ''))
        self.assertFalse(SpeciesArea.objects.filter(slug=self.move.OLD_SLUG).exists())
        self.assertEqual(SpeciesArea.objects.filter(species=gracilis).count(), 1)
        self.assertTrue(Species.objects.filter(pk=sp4.pk).exists())
        issue.refresh_from_db()
        self.assertEqual(issue.decision.count('מיגרציה 0129'), 1)
