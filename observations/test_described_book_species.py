from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from .models import (Article, Country, DiveTrip, IdentificationIssue, Region, Sample, Sea, Species, SpeciesArea,
                     SpeciesPublicationName, TaxonFamily, TaxonGenus)

migration = import_module('observations.migrations.0123_described_book_species')
MOVE = {m['old']: m for m in migration.MOVES}


class DescribedBookSpeciesTests(TestCase):
    """Migration 0123 (owner's decision on issues #34, 35, 36): a species numbered by the 2nd edition of Gosliner et al.
    and since described takes its WoRMS accepted name. With no catalogue row for that name the numbered row is renamed in
    place; with one, the observations and the gallery card move to it (same observation rows and transfer ids, the card
    keeps its row and slug), with the numbered row's texts where it has none, its names in the guides and its guides.
    Either way the species gets its author, no name source, texts for a described species, and sources citing WoRMS, the
    original description and both editions; observations take the new genus; a missing genus (Longibranchus) is added
    to its family; defining samples are repaired; the issue becomes "decided" with catalogue and observation done and the
    photo (and video) to fix. Runs once."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        self.trip = DiveTrip.objects.create(code='C', title='c', year=2023, month=1, country=ph,
                                            region=Region.objects.create(name='Anilao', country=ph, sea=sea))
        self.family = TaxonFamily.objects.create(name='Eubranchidae')
        self.eubranchus = TaxonGenus.objects.create(name='Eubranchus', family=self.family, taxonomic_order='709')
        TaxonGenus.objects.create(name='Thecacera')
        self.nssi2 = Article.objects.create(slug='nssi-2', title_he='NSSI-2')

    def numbered(self, name, video='https://youtu.be/30000000002'):
        genus, epithet = name.split(' ', 1)
        species = Species.objects.create(
            scientific_name=name, genus=genus, species=epithet, name_source='NSSI-2 Gosliner, Valdés & Behrens, 2018',
            description_he=f'מין שטרם תואר רשמית מהסוג {genus}, בשם {name}. משפט על הסוג.',
            description_en=f'An undescribed species, listed as {name} in Nudibranch & Sea Slug Identification – '
                           f'Indo-Pacific. A genus sentence.',
            identification_he='לבן. ' + MOVE[name]['drop'][0] + '(לפי ...)',
            identification_en='White. ' + MOVE[name]['drop'][1] + '(after ...)', food='הידרואידים.')
        species.articles.add(self.nssi2)
        SpeciesPublicationName.objects.create(species=species, article=self.nssi2, name=name, pages='281')
        sample = Sample(owner=self.owner, species=species, trip=self.trip, genus=genus, video_url=video)
        sample.save_reviewed()
        sample.refresh_from_db()
        issue = IdentificationIssue.objects.create(kind='book_edition', status='checking', priority=1, species=species,
                                                   transfer_id=MOVE[name]['issue'])
        return species, sample, issue

    def test_moves_to_the_existing_row_with_the_accepted_name(self):
        old, sample, issue = self.numbered('Eubranchus sp. 26', video='https://youtu.be/30000000001')
        row = Species.objects.create(scientific_name='Eubranchus putnami', genus='Eubranchus', species='putnami',
                                     author='Fernández-Simón & Moles, 2023')
        area = SpeciesArea.objects.get(species=old)
        slug, transfer = area.slug, sample.transfer_id
        migration.forwards(apps, None)
        row.refresh_from_db()
        self.assertEqual((row.scientific_name, row.genus, row.author, row.name_source),
                         ('Longibranchus putnami', 'Longibranchus', '(Fernández-Simón & Moles, 2023)', ''))
        self.assertTrue(row.description_he.startswith('אאולידית ממשפחת Eubranchidae'))
        self.assertTrue(row.description_he.endswith('משפט על הסוג.'))
        self.assertEqual((row.identification_he, row.identification_en, row.food), ('לבן. (לפי ...)', 'White. (after ...)', 'הידרואידים.'))
        self.assertEqual(row.sources.splitlines()[0], migration.WORMS.format(1832557))
        self.assertIn('Diversity 15(2): 219', row.sources)
        self.assertEqual(list(row.articles.all()), [self.nssi2])
        self.assertEqual(SpeciesPublicationName.objects.get(article=self.nssi2).species_id, row.pk)
        sample = Sample.objects.get(pk=sample.pk)
        self.assertEqual((sample.species_id, sample.genus, sample.transfer_id), (row.pk, 'Longibranchus', transfer))
        area.refresh_from_db()
        self.assertEqual((area.species_id, area.slug), (row.pk, slug))
        genus = TaxonGenus.objects.get(name='Longibranchus')
        self.assertEqual((genus.family_id, genus.taxonomic_order, genus.defining_sample_id), (self.family.pk, '709', sample.pk))
        self.eubranchus.refresh_from_db()
        self.assertIsNone(self.eubranchus.defining_sample_id)
        self.assertTrue(Species.objects.filter(pk=old.pk, scientific_name='Eubranchus sp. 26').exists())
        issue.refresh_from_db()
        self.assertEqual((issue.status, issue.corrected_species_id, issue.action_catalog, issue.action_observation,
                          issue.action_photo, issue.action_video), ('decided', row.pk, 'done', 'done', 'needed', 'needed'))

    def test_renames_in_place_without_a_row(self):
        old, sample, issue = self.numbered('Thecacera sp. 8')
        migration.forwards(apps, None)
        old.refresh_from_db()
        self.assertEqual((old.scientific_name, old.author, old.name_source),
                         ('Thecacera pikachu', 'Pola, Paz-Sedano, Martín, L. Warren, Noble & Martín-Hervás, 2026', ''))
        self.assertIn('ממזרח טימור', old.description_he)
        self.assertIn('Zootaxa 5793(1)', old.sources)
        issue.refresh_from_db()
        self.assertEqual((issue.status, issue.action_photo, issue.action_video), ('decided', 'needed', 'needed'))

    def test_runs_once(self):
        old, sample, issue = self.numbered('Thecacera sp. 8')
        migration.forwards(apps, None)
        old.refresh_from_db()
        texts = (old.description_he, old.sources, old.identification_he)
        migration.forwards(apps, None)
        old.refresh_from_db()
        self.assertEqual((old.description_he, old.sources, old.identification_he), texts)


class RemoveEmptyNumberedRowsTests(TestCase):
    """Migration 0124 (owner's approval): the numbered rows Goniodoridella sp. 8 and Eubranchus sp. 26, left empty by
    0123, are deleted -- only while nothing points at them (observation, card, name in a publication); their issues are
    first pointed at the described species, with the old name kept in the notes."""

    remove = import_module('observations.migrations.0124_remove_empty_numbered_rows')

    def test_deletes_an_empty_row_and_repoints_its_issue(self):
        old = Species.objects.create(scientific_name='Goniodoridella sp. 8', genus='Goniodoridella', species='sp. 8')
        new = Species.objects.create(scientific_name='Murphydoris cobbi', genus='Murphydoris', species='cobbi')
        issue = IdentificationIssue.objects.create(kind='book_edition', species=old, corrected_species=new, notes='x')
        self.remove.forwards(apps, None)
        self.assertFalse(Species.objects.filter(pk=old.pk).exists())
        issue.refresh_from_db()
        self.assertEqual((issue.species_id, issue.corrected_species_id), (new.pk, new.pk))
        self.assertIn('Goniodoridella sp. 8', issue.notes)

    def test_keeps_a_row_still_used(self):
        old = Species.objects.create(scientific_name='Eubranchus sp. 26', genus='Eubranchus', species='sp. 26')
        Species.objects.create(scientific_name='Longibranchus putnami', genus='Longibranchus', species='putnami')
        SpeciesPublicationName.objects.create(species=old, article=Article.objects.create(slug='a', title_he='a'), name='x')
        self.remove.forwards(apps, None)
        self.assertTrue(Species.objects.filter(pk=old.pk).exists())
