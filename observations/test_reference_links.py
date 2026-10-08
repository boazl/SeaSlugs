import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from . import reference_links as rl
from .models import Species
from .table_transfer import TABLES, export_table, plan


class MatchingTests(TestCase):
    def test_full_name_rule(self):
        for genus, epithet, ok in (('Felimare', 'picta', True), ('Hypselodoris', 'sp.', False), ('Atagema', 'sp. 12', False),
                                   ('Chromodoris', 'cf. strigata', False), ('Discodorid', 'sp.', False), ('', 'picta', False),
                                   ('Felimare', '', False), ('Doto', 'aff', False), ('Thecacera', 'pacifica-x', True)):
            self.assertEqual(rl.is_full_name(genus, epithet), ok, (genus, epithet))

    def test_candidate_names_add_the_accepted_name_once(self):
        sp = Species(genus='Hypselodoris', species='bullockii', accepted_genus='Felimare', accepted_species='bullockii')
        self.assertEqual(rl.candidate_names(sp), ['Hypselodoris bullockii', 'Felimare bullockii'])
        same = Species(genus='Felimare', species='picta', accepted_genus='Felimare', accepted_species='picta')
        self.assertEqual(rl.candidate_names(same), ['Felimare picta'])
        self.assertEqual(rl.candidate_names(Species(genus='Doto', species='sp.', accepted_genus='Doto', accepted_species='x')), [])

    def test_worms_prefers_accepted_and_resolves_synonyms(self):
        records = [{'scientificname': 'Felimare picta', 'status': 'unaccepted', 'AphiaID': 1, 'valid_AphiaID': 2, 'rank': 'Species'},
                   {'scientificname': 'Felimare picta', 'status': 'accepted', 'AphiaID': 3, 'valid_AphiaID': 3, 'rank': 'Species'}]
        self.assertEqual(rl.parse_worms(records, 'Felimare picta'), 3)
        self.assertEqual(rl.parse_worms(records[:1], 'Felimare picta'), 2)
        self.assertIsNone(rl.parse_worms([{'scientificname': 'Felimare', 'status': 'accepted', 'AphiaID': 9, 'rank': 'Genus'}], 'Felimare picta'))
        self.assertIsNone(rl.parse_worms(None, 'Felimare picta'))
        self.assertIsNone(rl.parse_worms([{'scientificname': 'Other name', 'AphiaID': 5, 'rank': 'Species'}], 'Felimare picta'))

    def test_inat_needs_exact_species_name_and_a_photo(self):
        results = [{'id': 1, 'name': 'Felimare picta', 'rank': 'species', 'default_photo': None},
                   {'id': 2, 'name': 'Felimare picta', 'rank': 'species', 'default_photo': {'url': 'x'}, 'is_active': False},
                   {'id': 3, 'name': 'Felimare', 'rank': 'genus', 'default_photo': {'url': 'x'}},
                   {'id': 4, 'name': 'Felimare pictus', 'rank': 'species', 'default_photo': {'url': 'x'}},
                   {'id': 5, 'name': 'felimare picta', 'rank': 'species', 'default_photo': {'url': 'x'}}]
        self.assertEqual(rl.parse_inat(results, ['Felimare picta']), 5)
        self.assertIsNone(rl.parse_inat(results[:4], ['Felimare picta']))

    def test_best_link_order_and_kind(self):
        self.assertEqual(rl.best_link(10, 20), 'https://www.inaturalist.org/taxa/20')
        self.assertEqual(rl.best_link(10, None), 'https://www.marinespecies.org/aphia.php?p=taxdetails&id=10')
        self.assertEqual(rl.best_link(None, None), '')
        self.assertEqual(rl.link_kind(rl.best_link(10, 20)), 'photo')
        self.assertEqual(rl.link_kind(rl.best_link(10, None)), 'worms')
        self.assertEqual(rl.link_kind('https://example.org'), '')


class CommandTests(TestCase):
    def setUp(self):
        self.cache = Path(tempfile.mkdtemp()) / 'cache.jsonl'
        self.picta = Species.objects.create(genus='Felimare', species='picta')
        self.bull = Species.objects.create(genus='Hypselodoris', species='bullockii', accepted_genus='Felimare', accepted_species='bullockii')
        self.sp = Species.objects.create(genus='Chromodoris', species='sp.')
        self.manual = Species.objects.create(genus='Doto', species='coronata', reference_link='https://example.org/mine')

    def run_command(self, *args):
        out = StringIO()
        call_command('fill_reference_links', f'--cache={self.cache}', '--sleep=0', *args, stdout=out)
        return out.getvalue()

    def fake_worms(self, names):
        return {n: {'Felimare picta': 11, 'Felimare bullockii': 12, 'Doto coronata': 13}.get(n) for n in names}

    def fake_inat(self, names):
        return 21 if names[0] == 'Felimare picta' else None

    def fetch_and_apply(self):
        with patch.object(rl, 'fetch_worms', self.fake_worms), patch.object(rl, 'fetch_inat', self.fake_inat):
            return self.run_command('--fetch', '--apply')

    def test_photo_page_beats_worms_and_species_without_full_name_get_nothing(self):
        self.fetch_and_apply()
        for sp in (self.picta, self.bull, self.sp, self.manual):
            sp.refresh_from_db()
        self.assertEqual(self.picta.reference_link, 'https://www.inaturalist.org/taxa/21')
        self.assertEqual(self.bull.reference_link, 'https://www.marinespecies.org/aphia.php?p=taxdetails&id=12')   # via the accepted name
        self.assertEqual(self.sp.reference_link, '')
        self.assertEqual(self.manual.reference_link, 'https://example.org/mine')                                   # never overwritten

    def test_cache_makes_a_second_run_free(self):
        self.fetch_and_apply()
        calls = []
        with patch.object(rl, 'fetch_worms', lambda n: calls.append(n) or {}), patch.object(rl, 'fetch_inat', lambda n: calls.append(n)):
            self.run_command('--fetch')
        self.assertEqual(calls, [])
        self.assertEqual(len(self.cache.read_text().splitlines()), len({json.dumps(json.loads(l)) for l in self.cache.read_text().splitlines()}))

    def test_limit_stops_early_and_a_rerun_continues(self):
        with patch.object(rl, 'fetch_worms', self.fake_worms), patch.object(rl, 'fetch_inat', self.fake_inat) as inat:
            self.run_command('--fetch', '--limit=1')
        inat_lines = [json.loads(l) for l in self.cache.read_text().splitlines() if '"inat"' in l]
        self.assertEqual(len(inat_lines), 1)
        self.fetch_and_apply()
        self.assertEqual(len([l for l in self.cache.read_text().splitlines() if '"inat"' in l]), 3)   # picta, bullockii, coronata

    def test_report_only_changes_nothing(self):
        with patch.object(rl, 'fetch_worms', self.fake_worms), patch.object(rl, 'fetch_inat', self.fake_inat):
            self.run_command('--fetch')
        message = self.run_command()
        self.assertIn('1 iNaturalist pages, 2 WoRMS pages', message)
        self.assertEqual(Species.objects.exclude(reference_link='').count(), 1)   # only the manual one

    @override_settings(PRODUCTION=True)
    def test_apply_is_refused_in_production(self):
        with self.assertRaises(CommandError):
            self.run_command('--apply')


class AdminAndTransferTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser('root', 'r@example.com', 'pw'); self.client.force_login(self.root)
        self.photo = Species.objects.create(genus='Felimare', species='picta', reference_link='https://www.inaturalist.org/taxa/21')
        self.worms = Species.objects.create(genus='Doto', species='coronata', reference_link='https://www.marinespecies.org/aphia.php?p=taxdetails&id=13')
        self.none = Species.objects.create(genus='Doto', species='fragilis')

    def test_changelist_column_labels_the_kind_of_link(self):
        page = self.client.get('/admin/observations/species/').content.decode()
        self.assertIn('href="https://www.inaturalist.org/taxa/21"', page)
        self.assertIn('🖼 תמונות', page)
        self.assertIn('>WoRMS</a>', page)
        self.assertIn('קישור עזר', page)

    def test_field_is_editable_on_the_species_form(self):
        page = self.client.get(f'/admin/observations/species/{self.none.pk}/change/').content.decode()
        self.assertIn('name="reference_link"', page)

    def test_public_species_pages_never_show_it(self):
        from django.urls import reverse
        for url in ('/', '/he/', '/en/'):
            response = self.client.get(url)
            if response.status_code == 200:
                self.assertNotIn('inaturalist.org/taxa/21', response.content.decode())

    def test_travels_with_the_species_table_and_old_exports_still_import(self):
        self.assertEqual(TABLES['species'][1][-1], 'reference_link')
        doc = export_table('species')
        self.assertIn('reference_link', doc['rows'][0])
        self.assertTrue(all(i['action'] == 'same' for i in plan(doc)))
        doc['rows'][0]['reference_link'] = 'https://example.org/new'
        self.assertEqual(sum(i['action'] == 'update' for i in plan(doc)), 1)
        # an export made before this field existed has no such key at all
        old = export_table('species')
        for row in old['rows']:
            del row['reference_link']
        self.assertTrue(all(i['action'] == 'same' for i in plan(old)))


class BundledCacheTests(TestCase):
    def test_the_bundled_cache_is_well_formed_and_only_points_at_the_two_sources(self):
        from .management.commands.fill_reference_links import DEFAULT_CACHE, load_cache
        cache = load_cache(DEFAULT_CACHE)
        self.assertGreater(len(cache['worms']), 4000)
        self.assertGreater(len(cache['inat']), 4000)
        for key, found in cache['worms'].items():
            self.assertTrue(found is None or isinstance(found, int), key)
            self.assertTrue(rl.is_full_name(*key.split(' ', 1)), key)       # never a 'sp.' name
        self.assertTrue(all(found is None or isinstance(found, int) for found in cache['inat'].values()))
