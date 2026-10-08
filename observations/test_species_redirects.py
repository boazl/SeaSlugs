from unittest.mock import patch
from uuid import uuid4
from xml.etree import ElementTree

from django.contrib.auth.models import User
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea
from .species_redirects import HISTORICAL_SPECIES_REDIRECTS, validate_mappings


OLD = 'diniatys-dentifer-phillipines-indo-pacific'
CURRENT = 'diniatys-dentifer-phillipines-indo-pacific-south-china-sea'
UNRESOLVED = ('doto-sp', 'eubranchus-mandapamensis', 'nakamigawaia-sp', 'tenellia-sp')


class MappingValidationTests(SimpleTestCase):
    def record(self, old='old-area', current='current-area', sample_id=None):
        return {'old_slug': old, 'current_slug': current,
                'sample_transfer_id': sample_id or str(uuid4())}

    def test_manifest_has_only_37_approved_sources_and_no_unresolved_species(self):
        self.assertEqual(len(HISTORICAL_SPECIES_REDIRECTS), 37)
        self.assertEqual(HISTORICAL_SPECIES_REDIRECTS[OLD][0], CURRENT)
        for stem in UNRESOLVED:
            self.assertNotIn(stem + '-phillipines-indo-pacific', HISTORICAL_SPECIES_REDIRECTS)

    def test_invalid_slug_paths_and_external_targets_are_rejected(self):
        for slug in ('', 'https://example.com/species/', '//example.com', '../other',
                     'slug?lang=en', 'slug#fragment', 'slug/extra', 'slug\n', 'x' * 221):
            for field in ('old_slug', 'current_slug'):
                with self.subTest(slug=slug, field=field):
                    record = self.record()
                    record[field] = slug
                    with self.assertRaises(ValueError):
                        validate_mappings([record])

    def test_duplicate_sources_and_self_redirects_are_rejected(self):
        for records in ([self.record(), self.record()], [self.record('same', 'same')]):
            with self.assertRaises(ValueError):
                validate_mappings(records)

    def test_chains_and_cycles_are_rejected(self):
        for records in ([self.record('a', 'b'), self.record('b', 'c')],
                        [self.record('a', 'b'), self.record('b', 'a')]):
            with self.assertRaises(ValueError):
                validate_mappings(records)

    def test_malformed_records_and_unverified_sample_ids_are_rejected(self):
        for records in ({}, [None], [{}], [self.record(sample_id='invalid')],
                        [dict(self.record(), extra='unexpected')]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                validate_mappings(records)


class SpeciesRedirectTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('redirect-test-owner')
        self.country = Country.objects.create(name='פיליפינים', name_en='Phillipines')
        self.sea = Sea.objects.create(name='South China Sea', name_en='Indo Pacific - South China Sea')
        region = Region.objects.create(name='Romblon', name_en='Romblon', country=self.country, sea=self.sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=self.country, region=region)
        self.area, self.sample = self.make_destination(OLD, 0)

    def make_destination(self, old, index):
        current, sample_id = HISTORICAL_SPECIES_REDIRECTS[old]
        species = Species.objects.create(scientific_name=f'Redirectfixture species{index}')
        sample = Sample(owner=self.owner, trip=self.trip, species=species,
                        transfer_id=sample_id, video_url=f'https://youtu.be/{index:011d}')
        sample.save_reviewed()
        area = SpeciesArea.objects.get(species=species)
        area.slug = current
        area.save(update_fields=['slug'])
        return area, sample

    def test_all_37_exact_mappings_redirect_once_to_live_current_pages(self):
        for index, (old, (current, _)) in enumerate(HISTORICAL_SPECIES_REDIRECTS.items(), 1):
            if old != OLD:
                self.make_destination(old, index)
            with self.subTest(old=old):
                self.assertRedirects(self.client.get(f'/species/{old}/'),
                                     f'/species/{current}/', status_code=301)
                page = self.client.get(f'/species/{current}/')
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, f'<link rel="canonical" href="https://seaslugs.org.il/species/{current}/">')

    def test_unknown_and_four_unresolved_aliases_stay_404(self):
        for slug in [stem + '-phillipines-indo-pacific' for stem in UNRESOLVED] + [
                'unknown-phillipines-indo-pacific', OLD + '-2']:
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(f'/species/{slug}/').status_code, 404)

    def test_explicit_english_and_hebrew_parameters_survive_and_render(self):
        for lang in ('en', 'he'):
            with self.subTest(lang=lang):
                response = self.client.get(f'/species/{OLD}/?lang={lang}', follow=True)
                self.assertEqual(response.redirect_chain, [(f'/species/{CURRENT}/?lang={lang}', 301)])
                self.assertEqual(response.status_code, 200)
                canonical = f'https://seaslugs.org.il/species/{CURRENT}/' + ('?lang=en' if lang == 'en' else '')
                self.assertContains(response, f'<link rel="canonical" href="{canonical}">')

    def test_untrusted_query_parameters_cannot_select_a_destination(self):
        for query, suffix in [('lang=en&next=https://example.com/', '?lang=en'),
                              ('lang=invalid&next=//example.com/', ''), ('next=//example.com/', '')]:
            with self.subTest(query=query):
                response = self.client.get(f'/species/{OLD}/?{query}')
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response['Location'], f'/species/{CURRENT}/{suffix}')

    def test_missing_destination_does_not_redirect(self):
        self.area.delete()
        self.assertEqual(self.client.get(f'/species/{OLD}/').status_code, 404)

    def test_unpublished_deleted_and_media_less_destinations_do_not_redirect(self):
        for changes in ({'status': 'pending'}, {'deleted_at': timezone.now()},
                        {'image': '', 'video_url': ''},
                        {'image': '', 'video_url': 'not-a-valid-video'}):
            with self.subTest(changes=changes):
                original = {key: getattr(self.sample, key) for key in changes}
                Sample.objects.filter(pk=self.sample.pk).update(**changes)
                self.assertEqual(self.client.get(f'/species/{OLD}/').status_code, 404)
                Sample.objects.filter(pk=self.sample.pk).update(**original)

    def test_target_with_no_defining_sample_does_not_redirect(self):
        SpeciesArea.objects.filter(pk=self.area.pk).update(defining_sample=None)
        self.assertEqual(self.client.get(f'/species/{OLD}/').status_code, 404)

    def test_wrong_geography_variant_and_incomplete_observations_do_not_redirect(self):
        other_sea = Sea.objects.create(name='Western Pacific')
        for changes in ({'sea_id': other_sea.pk}, {'undetermined_variant': 'B'}):
            with self.subTest(changes=changes):
                original = {key: getattr(self.area, key) for key in changes}
                SpeciesArea.objects.filter(pk=self.area.pk).update(**changes)
                self.assertEqual(self.client.get(f'/species/{OLD}/').status_code, 404)
                SpeciesArea.objects.filter(pk=self.area.pk).update(**original)
        DiveTrip.objects.filter(pk=self.trip.pk).update(year=None)
        self.assertEqual(self.client.get(f'/species/{OLD}/').status_code, 404)

    def test_reused_slug_with_different_sample_uuid_does_not_redirect(self):
        Sample.objects.filter(pk=self.sample.pk).update(transfer_id=uuid4())
        self.assertEqual(self.client.get(f'/species/{CURRENT}/').status_code, 200)
        self.assertEqual(self.client.get(f'/species/{OLD}/').status_code, 404)

    def test_changing_defining_sample_keeps_verified_population_redirect(self):
        replacement = Sample(owner=self.owner, trip=self.trip, species=self.area.species,
                             video_url='https://youtu.be/11111111111')
        replacement.save_reviewed()
        SpeciesArea.objects.filter(pk=self.area.pk).update(defining_sample=replacement)
        self.assertRedirects(self.client.get(f'/species/{OLD}/'), f'/species/{CURRENT}/', status_code=301)

    def test_live_current_source_page_takes_precedence_over_alias(self):
        mapping = {CURRENT: HISTORICAL_SPECIES_REDIRECTS[OLD]}
        with patch('observations.species_redirects.HISTORICAL_SPECIES_REDIRECTS', mapping):
            self.assertEqual(self.client.get(f'/species/{CURRENT}/').status_code, 200)

    def test_stale_historical_area_can_redirect_without_changing_it(self):
        species = Species.objects.create(scientific_name='Stale historical')
        stale = SpeciesArea.objects.create(species=species, country=self.country, sea=self.sea, slug=OLD)
        self.assertRedirects(self.client.get(f'/species/{OLD}/'), f'/species/{CURRENT}/', status_code=301)
        stale.refresh_from_db()
        self.assertEqual(stale.slug, OLD)
        self.assertIsNone(stale.defining_sample_id)

    def test_other_population_with_same_species_name_remains_independent(self):
        country = Country.objects.create(name='Israel', name_en='Israel')
        sea = Sea.objects.create(name='Mediterranean', name_en='Mediterranean')
        region = Region.objects.create(name='Other locality', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Other trip', year=2026, country=country, region=region)
        Sample(owner=self.owner, trip=trip, species=self.area.species,
               video_url='https://youtu.be/11111111111').save_reviewed()
        other = SpeciesArea.objects.get(species=self.area.species, country=country, sea=sea)
        self.assertEqual(self.client.get(f'/species/{other.slug}/').status_code, 200)
        self.assertRedirects(self.client.get(f'/species/{OLD}/'), f'/species/{CURRENT}/', status_code=301)

    def test_sitemap_lists_current_destinations_and_excludes_all_historical_aliases(self):
        for index, old in enumerate(HISTORICAL_SPECIES_REDIRECTS, 1):
            if old != OLD:
                self.make_destination(old, index)
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        locations = {node.text for node in ElementTree.fromstring(response.content).iter(
            '{http://www.sitemaps.org/schemas/sitemap/0.9}loc')}
        for old, (current, _) in HISTORICAL_SPECIES_REDIRECTS.items():
            self.assertNotIn(f'https://seaslugs.org.il/species/{old}/', locations)
            self.assertIn(f'https://seaslugs.org.il/species/{current}/', locations)

    def test_redirect_requests_do_not_write_database_records(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(f'/species/{OLD}/')
        self.assertEqual(response.status_code, 301)
        self.assertTrue(queries.captured_queries)
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT ')
                            for query in queries.captured_queries))
        self.area.refresh_from_db()
        self.assertEqual(self.area.slug, CURRENT)
        self.assertEqual(SpeciesArea.objects.count(), 1)
