import json
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from . import article_transfer
from .models import Article, Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea

NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'


class Fixture(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('boss', password='x')
        country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        self.sea = Sea.objects.create(name='ים סין', name_en='South China Sea')
        self.region = Region.objects.create(name='אנילאו', name_en='Anilao', country=country, sea=self.sea)
        self.country = country
        self.trip = DiveTrip.objects.create(title='t', year=2025, month=3, country=country, region=self.region)
        self.n = 0

    def observe(self, species, variant=''):
        self.n += 1
        sample = Sample(owner=self.owner, species=species, trip=self.trip, undetermined_variant=variant,
                        video_url=f'https://youtu.be/2000000000{self.n}')
        sample.save_reviewed()
        return sample

    def species(self, name, **kwargs):
        genus, epithet = name.split(' ', 1)
        return Species.objects.create(scientific_name=name, genus=genus, species=epithet, **kwargs)


class BibliographyTests(Fixture):
    """The articles library is also a bibliography: each entry has a kind -- identification guide, a paper in which
    species were described or numbered, or a general scientific paper -- and /articles/ lists them in those three
    sections, each entry with its full reference, the short form it is cited by, and the undescribed species whose name
    it is the source of. An entry may be a reference only (a book, a paper not kept on the site): no PDF and no sections,
    but a reference or a link. On a species page the source of an undescribed species' name links to its entry."""

    def test_sections_references_and_cited_species(self):
        Article.objects.create(slug='nssi-2', title_en='NSSI 2nd edition', kind='guide', short_ref=NSSI2,
                               citation='Gosliner, T.M., Valdés, Á. & Behrens, D.W. (2018). Nudibranch & Sea Slug Identification.')
        Article.objects.create(slug='phylo', title_en='A phylogeny', kind='description', citation='Someone (2021). Cladistics 37.',
                               link='https://doi.org/10.1/x')
        sp = self.species('Tenellia sp. 17', name_source=NSSI2)
        self.observe(sp)
        page = self.client.get('/articles/?lang=en').content.decode()
        self.assertLess(page.index('id="kind-guide"'), page.index('id="kind-description"'))
        self.assertIn('Identification guides', page)
        self.assertIn('Gosliner, T.M., Valdés, Á. &amp; Behrens, D.W. (2018)', page)
        self.assertIn('Not stored on the site', page)
        self.assertIn('Source of the name of:', page)
        self.assertIn('<i>Tenellia</i> sp. 17', page)
        area = SpeciesArea.objects.get(species=sp)
        page = self.client.get(f'/species/{area.slug}/?lang=en').content.decode()
        self.assertIn('(Source: <a class="name-source" href="/articles/?lang=en#nssi-2"', page)

    def test_admin_accepts_a_reference_only_entry(self):
        self.client.force_login(self.owner)
        base = {'title_en': 'Book', 'published_on': '2026-11-20', 'kind': 'guide',
                'blocks-TOTAL_FORMS': '0', 'blocks-INITIAL_FORMS': '0', 'references-TOTAL_FORMS': '0', 'references-INITIAL_FORMS': '0'}
        self.assertContains(self.client.post('/admin/observations/article/add/', {**base, 'slug': 'empty'}), 'למאמר צריך תוכן')
        response = self.client.post('/admin/observations/article/add/', {**base, 'slug': 'book', 'citation': 'Author (2018). Book.'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Article.objects.get(slug='book').is_reference_only)

    def test_transfer_carries_the_bibliography(self):
        article = Article.objects.create(slug='book', title_en='Book', kind='guide', citation='Author (2018). Book.', short_ref='Author, 2018')
        entry = article_transfer.article_entry(article)
        self.assertEqual((entry['kind'], entry['short_ref']), ('guide', 'Author, 2018'))
        document = article_transfer.article_document(article)
        article.delete()
        upload = SimpleUploadedFile('book.article.json', json.dumps(document).encode())
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            article_transfer.receive([upload])
        copy = Article.objects.get(slug='book')
        self.assertEqual((copy.kind, copy.citation, copy.short_ref), ('guide', 'Author (2018). Book.', 'Author, 2018'))
        old = {k: v for k, v in entry.items() if k not in ('kind', 'citation', 'short_ref')}
        self.assertTrue(article_transfer._valid_entry(old))      # a list from before the bibliography is still read


class MarkBareSpMigrationTests(Fixture):
    """Migration 0113: every gallery card of a bare "Genus sp." (an unidentified animal) gets a mark -- its variant letter,
    else the next free letter in the genus -- in place (the species is renamed when the card is its only one; a card whose
    mark is an empty catalogue row moves to it), the variant is folded into the name, the card keeps its URL, and the
    species gets the site observation as its source. The guides become bibliography entries and Coryphellina sp. 1 /
    Thuridilla sp. 7 cite the 2nd edition."""

    def run_migration(self):
        import_module('observations.migrations.0113_bibliography_and_sp_marks').forward(apps, None)

    def test_marks(self):
        okenia = self.species('Okenia sp.')
        self.species('Okenia sp. A')
        obs = self.observe(okenia)
        slug = SpeciesArea.objects.get(species=okenia).slug
        phyllidiella = self.species('Phyllidiella sp.')
        empty_b = self.species('Phyllidiella sp. B')
        a, b = self.observe(phyllidiella, 'A'), self.observe(phyllidiella, 'B')
        thuridilla = self.species('Thuridilla sp. 7')
        self.run_migration()
        okenia.refresh_from_db(); obs.refresh_from_db()
        self.assertEqual((okenia.scientific_name, obs.species_id), ('Okenia sp. B', okenia.pk))
        self.assertEqual(SpeciesArea.objects.get(species=okenia).slug, slug)
        self.assertEqual(okenia.name_source, 'SeaSlugs.org.il observation: Anilao, 2025')
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(b.species_id, empty_b.pk)
        self.assertEqual((a.species.scientific_name, a.undetermined_variant, b.undetermined_variant), ('Phyllidiella sp. A', '', ''))
        self.assertFalse(SpeciesArea.objects.exclude(undetermined_variant='').exists())
        thuridilla.refresh_from_db()
        self.assertEqual(thuridilla.name_source, NSSI2)
        self.assertEqual(Article.objects.get(short_ref=NSSI2).kind, 'guide')
        self.run_migration()      # a second run changes nothing
        self.assertEqual(Species.objects.filter(scientific_name__startswith='Okenia sp. ').count(), 2)


class OriginalDescriptionsMigrationTests(Fixture):
    """Migration 0114: the original description of each described gallery species (WoRMS "original description"
    sources, observations/data/original_descriptions.json) becomes a bibliography entry of kind "description", picked
    by the species it describes; an entry is made only when one of its species is in the catalogue, and running it
    again adds nothing. On a species page the entry leads to its place in the library."""

    def test_entries_and_links(self):
        migration = import_module('observations.migrations.0114_original_descriptions')
        data = json.loads(migration.DATA.read_text(encoding='utf-8'))
        entry = next(e for e in data if any(s['name'] == 'Ardeadoris egretta' for s in e['species']))
        egretta = self.species('Ardeadoris egretta', author='Rudman, 1984')
        self.observe(egretta)
        migration.forward(apps, None)
        migration.forward(apps, None)
        article = Article.objects.get(slug=entry['slug'])
        self.assertEqual((article.kind, list(article.species.all())), ('description', [egretta]))
        self.assertIn('Zoological Journal of the Linnean Society', article.citation)
        self.assertEqual(Article.objects.count(), 1)
        page = self.client.get(f'/species/{SpeciesArea.objects.get(species=egretta).slug}/?lang=en').content.decode()
        self.assertIn(f'href="/articles/?lang=en#{article.slug}"', page)
