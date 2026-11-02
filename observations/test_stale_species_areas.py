"""A gallery area (SpeciesArea) is shown only while it has observations of its own. When a trip moves to another
country/region, or a region's sea changes, its observations' areas follow at once: the new area is created and
the one left behind gives up its defining sample. (The case: Goniobranchus geminus showed twice on the genus page,
"Djibouti · Gulf of Eilat" and "Djibouti · Bab el-Mandeb", for one observation.)"""
import importlib

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from .gallery_data import area_is_live
from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea
from .species_redirects import HISTORICAL_SPECIES_REDIRECTS


class StaleSpeciesAreaTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('admin', password='testing')
        self.djibouti = Country.objects.create(name='Djibouti')
        self.eilat_sea = Sea.objects.create(name='Red Sea - Gulf of Aqaba')
        self.mandeb_sea = Sea.objects.create(name='Red Sea - Bab el-Mandeb')
        self.wrong = Region.objects.create(name='Wrong region', country=self.djibouti, sea=self.eilat_sea)
        self.mandeb = Region.objects.create(name='Bab el-Mandeb', country=self.djibouti, sea=self.mandeb_sea)
        self.trip = DiveTrip.objects.create(code='W', title='Djibouti 2022', year=2022, country=self.djibouti, region=self.wrong)
        self.species = Species.objects.create(scientific_name='Goniobranchus geminus', genus='Goniobranchus', species='geminus', author='(Rudman, 1987)')
        self.sample = Sample(owner=self.owner, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species,
                             status=Sample.Status.PUBLISHED, video_url='https://youtu.be/11111111111')
        self.sample.save_reviewed()
        self.old_area = SpeciesArea.objects.get(species=self.species, sea=self.eilat_sea)

    def test_moving_the_trip_moves_the_area(self):
        self.trip.region = self.mandeb; self.trip.save()
        self.old_area.refresh_from_db()
        self.assertIsNone(self.old_area.defining_sample_id)
        new = SpeciesArea.objects.get(species=self.species, sea=self.mandeb_sea)
        self.assertEqual(new.defining_sample_id, self.sample.pk)
        self.assertFalse(area_is_live(self.old_area)); self.assertTrue(area_is_live(new))

    def test_changing_the_region_sea_moves_the_area(self):
        self.wrong.sea = self.mandeb_sea; self.wrong.save()
        self.old_area.refresh_from_db()
        self.assertIsNone(self.old_area.defining_sample_id)
        self.assertTrue(SpeciesArea.objects.filter(species=self.species, sea=self.mandeb_sea, defining_sample=self.sample).exists())

    def test_stale_area_with_a_defining_sample_is_not_live(self):
        # the state found in the database: the trip moved without the area following
        DiveTrip.objects.filter(pk=self.trip.pk).update(region=self.mandeb)
        self.old_area.refresh_from_db()
        self.assertEqual(self.old_area.defining_sample_id, self.sample.pk)
        self.assertFalse(area_is_live(self.old_area))

    def test_genus_page_shows_one_card(self):
        from .models import TaxonGenus, TaxonFamily, TaxonOrder
        order = TaxonOrder.objects.create(name='Nudibranchia')
        family = TaxonFamily.objects.create(order=order, name='Chromodorididae')
        TaxonGenus.objects.create(family=family, name='Goniobranchus', defining_sample=self.sample)
        Species.objects.filter(pk=self.species.pk).update(family='Chromodorididae', order='Nudibranchia')
        DiveTrip.objects.filter(pk=self.trip.pk).update(region=self.mandeb)   # stale area left behind
        SpeciesArea.objects.create(species=self.species, country=self.djibouti, sea=self.mandeb_sea, defining_sample=self.sample)
        html = self.client.get('/genus/Goniobranchus/').content.decode()
        self.assertEqual(html.count('/species/goniobranchus-geminus-'), html.count(f'/species/{SpeciesArea.objects.get(sea=self.mandeb_sea).slug}/'))
        self.assertNotIn(f'/species/{self.old_area.slug}/', html)

    def test_migration_removes_only_an_empty_area(self):
        migration = importlib.import_module('observations.migrations.0085_remove_djibouti_gulf_of_eilat_area')
        SpeciesArea.objects.filter(pk=self.old_area.pk).update(slug=migration.SLUG)
        migration.forwards(apps, None)
        self.assertTrue(SpeciesArea.objects.filter(pk=self.old_area.pk).exists())   # still has its observation
        DiveTrip.objects.filter(pk=self.trip.pk).update(region=self.mandeb)
        migration.forwards(apps, None)
        self.assertFalse(SpeciesArea.objects.filter(pk=self.old_area.pk).exists())

    def test_old_address_redirects(self):
        self.assertEqual(HISTORICAL_SPECIES_REDIRECTS['goniobranchus-geminus-djibouti-red-sea-gulf-of-aqaba'][0],
                         'goniobranchus-geminus-djibouti-red-sea-bab-el-mandeb-strait-gulf-of-aden')
