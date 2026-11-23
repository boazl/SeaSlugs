import json
from importlib import import_module
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea
from .table_transfer import TABLES

APP_JS = Path(settings.BASE_DIR) / 'dist' / 'app.js'


class SpNameSourceTests(TestCase):
    """An undescribed "sp." species has no author: where a described species shows its author, it shows the publication
    that numbered it -- Species.name_source -- as "Source: Gosliner, Valdés & Behrens, 2018" -- without the library's edition code and without parentheses, on its
    own line on the species page, as on the photo labels ("Source:" in Hebrew too -- the label goes with the Latin name; on
    Hebrew pages): on the species page (title and observations), the genus / taxon cards and the gallery cards (catalog.js
    `source`, app.js authorText). A described species keeps its author; a "sp." without a source shows nothing; a source
    on a described species is ignored. The field travels with the species table; migration 0110 fills it for the gallery's
    numbered sp. species and corrects the Thuridilla numbering issue."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין', name_en='South China Sea')
        self.region = Region.objects.create(name='אנילאו', name_en='Anilao', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='t', year=2026, month=2, country=country, region=self.region)
        self.n = 0

    def gallery(self, name, author='', source=''):
        genus, epithet = name.split(' ', 1)
        species = Species.objects.create(scientific_name=name, genus=genus, species=epithet, author=author, name_source=source)
        self.n += 1
        Sample(owner=self.owner, species=species, trip=self.trip, video_url=f'https://youtu.be/0000000000{self.n}').save_reviewed()
        return species, SpeciesArea.objects.get(species=species)

    def test_author_text(self):
        sp, _ = self.gallery('Thuridilla sp. 2', source='Martín-Hervás et al., 2021')
        self.assertEqual(sp.author_text('en'), 'Source: Martín-Hervás et al., 2021')
        self.assertEqual(sp.author_text('he'), 'Source: Martín-Hervás et al., 2021')
        described, _ = self.gallery('Thuridilla gracilis', author='(Risbec, 1928)', source='ignored')
        self.assertEqual(described.author_text('en'), '(Risbec, 1928)')
        bare, _ = self.gallery('Tenellia sp. A')
        self.assertEqual(bare.author_text('en'), '')

    def test_species_page_and_catalog(self):
        sp, area = self.gallery('Tenellia sp. 65', source='NSSI-3 Gosliner, Valdés & Behrens, 2026')
        page = self.client.get(f'/species/{area.slug}/?lang=en').content.decode()
        # shown as "Authors, Year", without the library's edition code (the owner's uniform rule for sources)
        self.assertIn('<span class="species-author species-source">Source: Gosliner, Valdés &amp; Behrens, 2026</span>', page)
        page = self.client.get(f'/species/{area.slug}/?lang=he').content.decode()
        self.assertIn('<span class="species-author species-source">Source: Gosliner, Valdés &amp; Behrens, 2026</span>', page)
        body = self.client.get('/catalog.js').content.decode()
        catalog = json.loads(body.split('=', 1)[1].strip().removesuffix(';'))
        self.assertIn('"source": "Gosliner, Valdés & Behrens, 2026"', json.dumps(catalog, ensure_ascii=False))
        self.assertEqual(sp.source_display, 'Gosliner, Valdés & Behrens, 2026')
        script = APP_JS.read_text()
        self.assertIn('function authorText(sp)', script)
        self.assertIn('const authorLine = authorText(sp);', script)

    def test_travels_with_the_species_table(self):
        self.assertIn('name_source', TABLES['species'][1])

    def test_migration_fills_sources(self):
        migration = import_module('observations.migrations.0110_sp_name_sources')
        thuridilla, _ = self.gallery('Thuridilla sp. 4 (2021)')
        tenellia, _ = self.gallery('Tenellia sp. 65', source='kept')
        aegires, _ = self.gallery('Aegires sp. 8')
        migration.forward(apps, None)
        for species in (thuridilla, tenellia, aegires):
            species.refresh_from_db()
        self.assertEqual(thuridilla.name_source, 'Martín-Hervás et al., 2021')
        self.assertEqual(tenellia.name_source, 'kept')
        self.assertEqual(aegires.name_source, 'NSSI-2 Gosliner, Valdés & Behrens, 2018')


class SiteMarkedSourceTests(TestCase):
    """The owner's own marked species (sp. A, or a number he gave) take as their source the site observation that
    defines them: "SeaSlugs.org.il observation: <photographer>, <region>, <year>" -- the earliest published one
    (Species.site_source). Migration 0111 fills it for the letter marks; the species admin action does it for any
    selected marked species. A bare "sp." and a species that already has a source are left alone."""

    def setUp(self):
        from .models import Profile
        self.owner = User.objects.create_user('boaz', password='x', first_name='בועז', last_name='ליבס')
        Profile.objects.update_or_create(user=self.owner, defaults={'first_name_en': 'Boaz', 'last_name_en': 'Liebes'})
        country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין', name_en='South China Sea')
        self.region = Region.objects.create(name='אנילאו', name_en='Anilao', country=country, sea=sea)
        later = Region.objects.create(name='רומבלון', name_en='Romblon', country=country, sea=sea)
        self.old_trip = DiveTrip.objects.create(code='H', title='a', year=2025, month=3, country=country, region=self.region)
        self.new_trip = DiveTrip.objects.create(code='V', title='b', year=2026, month=1, country=country, region=later)
        self.n = 0

    def species(self, name, trips, source=''):
        genus, epithet = name.split(' ', 1)
        species = Species.objects.create(scientific_name=name, genus=genus, species=epithet, name_source=source)
        for trip in trips:
            self.n += 1
            Sample(owner=self.owner, species=species, trip=trip, video_url=f'https://youtu.be/1000000000{self.n}').save_reviewed()
        return species

    def test_site_source_is_the_earliest_observation(self):
        sp = self.species('Elysia sp. A', [self.new_trip, self.old_trip])
        self.assertEqual(sp.site_source(), 'SeaSlugs.org.il observation: Boaz Liebes, Anilao, 2025')

    def test_migration_fills_letter_marks_only(self):
        marked = self.species('Elysia sp. A', [self.new_trip])
        bare = self.species('Elysia sp.', [self.new_trip])
        kept = self.species('Elysia sp. B', [self.new_trip], source='kept')
        import_module('observations.migrations.0111_site_marked_sp_sources').forward(apps, None)
        for s in (marked, bare, kept):
            s.refresh_from_db()
        self.assertEqual(marked.name_source, 'SeaSlugs.org.il observation: Boaz Liebes, Romblon, 2026')
        self.assertEqual((bare.name_source, kept.name_source), ('', 'kept'))

    def test_admin_action(self):
        numbered = self.species('Elysia sp. 3', [self.old_trip])
        bare = self.species('Elysia sp.', [self.old_trip])
        self.client.force_login(User.objects.create_superuser('boss', password='x'))
        self.client.post('/admin/observations/species/', {'action': 'fill_site_source',
                                                          '_selected_action': [numbered.pk, bare.pk]})
        numbered.refresh_from_db(); bare.refresh_from_db()
        self.assertEqual(numbered.name_source, 'SeaSlugs.org.il observation: Boaz Liebes, Anilao, 2025')
        self.assertEqual(bare.name_source, '')
