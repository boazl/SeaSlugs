from pathlib import Path
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth.models import User
from .models import Sample, Species, Country, Region, Sea, Site, DiveTrip, SpeciesArea, Photographer
from .table_transfer import export_table, plan, apply, fingerprint


class SpeciesAreaTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('manager',password='test-password')
        self.other=User.objects.create_user('other')
        self.country=Country.objects.create(name='Israel')
        self.sea=Sea.objects.create(name='Mediterranean')
        self.region=Region.objects.create(name='Akhziv',country=self.country,sea=self.sea)
        self.trip=DiveTrip.objects.create(title='Trip',year=2026,country=self.country,region=self.region)
        self.species=Species.objects.create(scientific_name='Test species')
        self.first=self.record(self.user)

    def record(self,owner,**kwargs):
        if 'video_url' not in kwargs and 'image' not in kwargs:
            self._video_counter=getattr(self,'_video_counter',0)+1
            kwargs=dict(kwargs,video_url=f'https://youtu.be/{str(self._video_counter).zfill(11)}')
        data=dict(owner=owner,species=self.species,trip=self.trip)
        data.update(kwargs)
        item=Sample(**data);item.save_reviewed();return item

    def test_first_sample_creates_area_and_becomes_defining(self):
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertEqual(area.defining_sample_id,self.first.pk)

    def test_second_sample_same_area_publishes_freely_without_moving_defining_sample(self):
        second=self.record(self.other)
        self.assertEqual(second.status,'published')
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertEqual(area.defining_sample_id,self.first.pk)
        self.assertEqual(SpeciesArea.objects.filter(species=self.species).count(),1)

    def test_another_region_same_country_sea_shares_one_area(self):
        other_region=Region.objects.create(name='Caesarea',country=self.country,sea=self.sea)
        other_trip=DiveTrip.objects.create(title='Other trip',year=2026,country=self.country,region=other_region)
        self.record(self.other,trip=other_trip)
        self.assertEqual(SpeciesArea.objects.filter(species=self.species).count(),1)

    def test_different_country_creates_a_second_area(self):
        other_country=Country.objects.create(name='Philippines')
        other_sea=Sea.objects.create(name='Indo Pacific')
        other_region=Region.objects.create(name='Romblon',country=other_country,sea=other_sea)
        other_trip=DiveTrip.objects.create(title='Abroad',year=2026,country=other_country,region=other_region)
        self.record(self.other,trip=other_trip)
        self.assertEqual(SpeciesArea.objects.filter(species=self.species).count(),2)

    def test_admin_can_reassign_defining_sample(self):
        second=self.record(self.other)
        self.client.force_login(self.user)
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        response=self.client.post(f'/admin/observations/speciesarea/{area.pk}/change/',
            {'species':self.species.pk,'country':self.country.pk,'sea':self.sea.pk,'defining_sample':second.pk})
        self.assertEqual(response.status_code,302)
        area.refresh_from_db();self.assertEqual(area.defining_sample_id,second.pk)

    def test_soft_delete_repoints_defining_sample_to_another_valid_sample(self):
        second=self.record(self.other)
        self.first.soft_delete(self.user)
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertEqual(area.defining_sample_id,second.pk)

    def test_soft_delete_clears_defining_sample_when_no_replacement_exists(self):
        self.first.soft_delete(self.user)
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertIsNone(area.defining_sample_id)

    def test_publishing_again_after_deletion_self_heals_a_cleared_area(self):
        self.first.soft_delete(self.user)
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertIsNone(area.defining_sample_id)
        third=self.record(self.other)
        area.refresh_from_db();self.assertEqual(area.defining_sample_id,third.pk)

    def test_rebuild_recreates_areas_from_published_samples_and_drops_stale_rows(self):
        stale=Species.objects.create(scientific_name='No longer published')
        SpeciesArea.objects.create(species=stale,country=self.country,sea=self.sea)
        count=SpeciesArea.rebuild()
        self.assertEqual(count,1)
        self.assertFalse(SpeciesArea.objects.filter(species=stale).exists())
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertEqual(area.defining_sample_id,self.first.pk)

    def test_rebuild_is_not_confused_by_samples_with_different_created_at(self):
        # Regression: Sample's default ordering (Meta.ordering=['-created_at']) used to leak
        # into rebuild()'s DISTINCT query, so two samples sharing one species+country+sea but
        # recorded at different times produced two "distinct" keys and crashed on the
        # SpeciesArea unique constraint. Force distinct timestamps so this reproduces even
        # when both samples are created in the same test tick.
        second=self.record(self.other)
        from django.utils import timezone
        import datetime
        Sample.objects.filter(pk=self.first.pk).update(created_at=timezone.now()-datetime.timedelta(days=1))
        Sample.objects.filter(pk=second.pk).update(created_at=timezone.now())
        count=SpeciesArea.rebuild()
        self.assertEqual(count,1)
        self.assertEqual(SpeciesArea.objects.filter(species=self.species,country=self.country,sea=self.sea).count(),1)

    def test_rebuild_admin_action_rebuilds_regardless_of_selection(self):
        self.client.force_login(self.user)
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        # corrupt it first, to prove the action truly rebuilds rather than trusting existing rows
        area.defining_sample=None;area.save(update_fields=['defining_sample'])
        with patch('observations.table_transfer.create_backup',return_value=Path('test.sqlite3')):
            response=self.client.post('/admin/observations/speciesarea/',{'action':'rebuild_all','_selected_action':[str(area.pk)]})
        self.assertEqual(response.status_code,302)
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertEqual(area.defining_sample_id,self.first.pk)

    def test_import_allows_republishing_same_species_elsewhere(self):
        self.record(self.other)
        doc=export_table('samples')
        row=next(r for r in doc['rows'] if r['status']=='published')
        doc['rows']=[dict(row,video_url='https://youtu.be/12345678901')]
        import uuid
        doc['rows'][0]['transfer_id']=str(uuid.uuid4())
        result=plan(doc)
        self.assertEqual(result[0]['action'],'new')

    def test_applying_a_samples_transfer_creates_species_area_like_save_reviewed_would(self):
        # A table transfer applies with a plain .save(), never save_reviewed(), so it
        # must independently register the same SpeciesArea side effect -- otherwise a species
        # imported this way would silently never show up in the public gallery.
        imported_species=Species.objects.create(scientific_name='Imported species')
        doc=export_table('samples')
        row=next(r for r in doc['rows'] if r['status']=='published')
        import uuid
        doc['rows']=[dict(row,species=imported_species.scientific_name,
                           transfer_id=str(uuid.uuid4()),video_url='https://youtu.be/zzzzzzzzzzz')]
        self.assertFalse(SpeciesArea.objects.filter(species=imported_species).exists())
        with patch('observations.table_transfer.create_backup',return_value=Path('test.sqlite3')):
            apply(doc,fingerprint())
        area=SpeciesArea.objects.get(species=imported_species,country=self.country,sea=self.sea)
        self.assertEqual(area.defining_sample.species_id,imported_species.pk)

    def test_applying_a_samples_transfer_does_not_duplicate_an_existing_area(self):
        doc=export_table('samples')
        row=next(r for r in doc['rows'] if r['status']=='published')
        import uuid
        doc['rows']=[dict(row,transfer_id=str(uuid.uuid4()),video_url='https://youtu.be/yyyyyyyyyyy')]
        with patch('observations.table_transfer.create_backup',return_value=Path('test.sqlite3')):
            apply(doc,fingerprint())
        self.assertEqual(SpeciesArea.objects.filter(species=self.species).count(),1)
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertEqual(area.defining_sample_id,self.first.pk)


class DiveTripSeaReserveFieldsTests(TestCase):
    """DiveTrip.resolved_sea (region.sea wins when there is a region, otherwise the sea
    picked directly on the trip) and the new site/photographer_fk lookup fields added
    alongside the existing free-text reserve/photographer fields."""

    def setUp(self):
        self.user = User.objects.create_superuser('manager', password='test-password')
        self.country = Country.objects.create(name='Israel')
        self.med = Sea.objects.create(name='Mediterranean')
        self.red = Sea.objects.create(name='Red Sea')
        self.region = Region.objects.create(name='Akhziv', country=self.country, sea=self.med)
        self.species = Species.objects.create(scientific_name='Resolved sea species')

    def test_resolved_sea_prefers_region_sea_over_own_sea_field(self):
        trip = DiveTrip.objects.create(title='With region', year=2026, country=self.country,
                                        region=self.region, sea=self.red)
        self.assertEqual(trip.resolved_sea, self.med)
        self.assertEqual(trip.resolved_sea_id, self.med.pk)

    def test_resolved_sea_falls_back_to_own_sea_field_without_region(self):
        trip = DiveTrip.objects.create(title='No region', year=2026, country=self.country, sea=self.red)
        self.assertEqual(trip.resolved_sea, self.red)
        self.assertEqual(trip.resolved_sea_id, self.red.pk)

    def test_resolved_sea_is_none_without_region_or_sea(self):
        trip = DiveTrip.objects.create(title='Neither', year=2026, country=self.country)
        self.assertIsNone(trip.resolved_sea)
        self.assertIsNone(trip.resolved_sea_id)

    def test_publishing_a_sample_on_a_region_less_trip_still_creates_a_species_area(self):
        # Before resolved_sea existed, the SpeciesArea side effect in Sample.save_reviewed
        # was gated on trip.region_id, so a trip with no region (only a directly-chosen sea)
        # never got its species into the public gallery at all.
        trip = DiveTrip.objects.create(title='No region', year=2026, country=self.country, sea=self.red)
        sample = Sample(owner=self.user, species=self.species, trip=trip,
                         video_url='https://youtu.be/abcdefghijk')
        sample.save_reviewed()
        area = SpeciesArea.objects.get(species=self.species, country=self.country, sea=self.red)
        self.assertEqual(area.defining_sample_id, sample.pk)

    def test_rebuild_also_covers_region_less_trips(self):
        # SpeciesArea.rebuild() regenerates the whole table from scratch (used by an admin
        # action); it used to only look at samples whose trip had a region.
        trip = DiveTrip.objects.create(title='No region', year=2026, country=self.country, sea=self.red)
        sample = Sample(owner=self.user, species=self.species, trip=trip,
                         video_url='https://youtu.be/abcdefghijk')
        sample.save_reviewed()
        SpeciesArea.objects.all().delete()
        SpeciesArea.rebuild()
        area = SpeciesArea.objects.get(species=self.species, country=self.country, sea=self.red)
        self.assertEqual(area.defining_sample_id, sample.pk)

    def test_site_and_photographer_lookup_fields_are_independent_of_free_text_fields(self):
        # site reuses the existing Site table (region-scoped) instead of a separate
        # reserve table -- the free-text reserve field is unaffected by it either way.
        site = Site.objects.create(name='Akhziv reef', region=self.region)
        photographer = Photographer.objects.create(name='Jane Diver')
        trip = DiveTrip.objects.create(title='Lookup fields', year=2026, country=self.country,
                                        reserve='Ras Mohammed (as typed)', site=site,
                                        photographer='Jane D.', photographer_fk=photographer)
        trip.refresh_from_db()
        self.assertEqual(trip.reserve, 'Ras Mohammed (as typed)')
        self.assertEqual(trip.site, site)
        self.assertEqual(trip.photographer, 'Jane D.')
        self.assertEqual(trip.photographer_fk, photographer)

    def test_divetrip_locations_endpoint_returns_region_and_site_mappings(self):
        site = Site.objects.create(name='Akhziv reef', region=self.region)
        self.client.force_login(self.user)
        response = self.client.get('/admin/observations/divetrip-locations/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        region_row = next(r for r in data['regions'] if r['id'] == self.region.pk)
        self.assertEqual(region_row['country_id'], self.country.pk)
        self.assertEqual(region_row['sea_id'], self.med.pk)
        site_row = next(s for s in data['sites'] if s['id'] == site.pk)
        self.assertEqual(site_row['region_id'], self.region.pk)

    def test_divetrip_locations_endpoint_requires_staff(self):
        outsider = User.objects.create_user('diver')
        self.client.force_login(outsider)
        response = self.client.get('/admin/observations/divetrip-locations/')
        self.assertNotEqual(response.status_code, 200)

    def test_applying_a_samples_transfer_on_a_region_less_trip_still_creates_a_species_area(self):
        # table_transfer.apply() has its own copy of the SpeciesArea side effect (it applies
        # with a plain .save(), never save_reviewed()) -- it must also use resolved_sea, or a
        # trip with no region (only a directly-chosen sea) imported this way would silently
        # never get its species into the public gallery. The side effect only fires for
        # new/updated rows (see apply()), so -- like the equivalent pre-existing test for a
        # trip WITH a region -- this imports a new species observation rather than
        # re-transferring the unchanged one.
        trip = DiveTrip.objects.create(title='No region', year=2026, country=self.country, sea=self.red)
        sample = Sample(owner=self.user, species=self.species, trip=trip,
                         video_url='https://youtu.be/abcdefghijk')
        sample.save_reviewed()
        imported_species = Species.objects.create(scientific_name='Imported region-less species')
        doc = export_table('samples')
        row = next(r for r in doc['rows'] if r['status'] == 'published')
        import uuid
        doc['rows'] = [dict(row, species=imported_species.scientific_name,
                             transfer_id=str(uuid.uuid4()), video_url='https://youtu.be/zzzzzzzzzzz')]
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        area = SpeciesArea.objects.get(species=imported_species, country=self.country, sea=self.red)
        self.assertEqual(area.defining_sample.species_id, imported_species.pk)


class RegionCountryMismatchDataFixTests(TestCase):
    """Regression for a real production bug: duplicate Region rows sharing the same name
    under two different countries (e.g. two separate "Romblon" rows -- one correctly under
    Philippines, one mistakenly created under Solomon Islands with a different sea) let a
    trip end up pointing at the WRONG one. That silently sent the trip's samples into the
    wrong country+sea gallery area -- real, published species quietly stopped showing up
    under the area a site visitor expected, with no error anywhere. Migration 0027 repoints
    any such trip to the region that actually matches its own country. These tests exercise
    that migration's fix function directly (the same technique Django's own migration runner
    uses to import a numbered migration module) rather than replaying the whole migration
    history, since the fix only touches plain, long-standing fields."""

    def fix(self):
        import importlib
        from django.apps import apps as live_apps
        module = importlib.import_module(
            'observations.migrations.0027_fix_trips_pointing_at_a_region_under_the_wrong_country')
        module.fix_region_country_mismatches(live_apps, None)

    def test_repoints_a_trip_whose_region_belongs_to_a_different_country_than_the_trip(self):
        philippines = Country.objects.create(name='פיליפינים')
        solomon = Country.objects.create(name='איי שלמה')
        sea_correct = Sea.objects.create(name='Indo Pacific')
        sea_wrong = Sea.objects.create(name='Indo Pacific - Western Pacific')
        correct_region = Region.objects.create(name='רומבלון', country=philippines, sea=sea_correct)
        wrong_region = Region.objects.create(name='רומבלון', country=solomon, sea=sea_wrong)
        trip = DiveTrip.objects.create(title='Romblon trip', year=2026, country=philippines, region=wrong_region)

        self.fix()

        trip.refresh_from_db()
        self.assertEqual(trip.region_id, correct_region.pk)

    def test_leaves_a_trip_alone_when_no_same_named_region_exists_under_its_own_country(self):
        # Nothing safe to repoint to -- this needs a human decision, not a guess.
        solomon = Country.objects.create(name='איי שלמה')
        sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='Anilao', country=solomon, sea=sea)
        philippines = Country.objects.create(name='פיליפינים')
        trip = DiveTrip.objects.create(title='Mismatched, unresolved', year=2026, country=philippines, region=region)

        self.fix()

        trip.refresh_from_db()
        self.assertEqual(trip.region_id, region.pk)

    def test_leaves_a_consistent_trip_untouched(self):
        philippines = Country.objects.create(name='פיליפינים')
        sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='אנילאו', country=philippines, sea=sea)
        trip = DiveTrip.objects.create(title='Consistent trip', year=2026, country=philippines, region=region)

        self.fix()

        trip.refresh_from_db()
        self.assertEqual(trip.region_id, region.pk)


class UnanimousRegionCountryDataFixTests(TestCase):
    """Regression for the same real bug as RegionCountryMismatchDataFixTests, but for a
    database that never had a duplicate region row -- only ONE "Romblon"-named region exists,
    tagged with the wrong country outright. Migration 0028 covers that case: when every trip
    that actually uses a region unanimously disagrees with the region's own country, the
    region's country is corrected to match them, rather than leaving it stuck with no
    duplicate to repoint to (which is what 0027 alone would do here)."""

    def fix(self):
        import importlib
        from django.apps import apps as live_apps
        module = importlib.import_module(
            'observations.migrations.0028_fix_region_country_when_all_its_trips_disagree')
        module.fix_region_country_when_its_trips_unanimously_disagree(live_apps, None)

    def test_corrects_a_region_whose_trips_unanimously_disagree_with_it(self):
        solomon = Country.objects.create(name='איי שלמה')
        philippines = Country.objects.create(name='פיליפינים')
        sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='רומבלון', country=solomon, sea=sea)
        DiveTrip.objects.create(title='Trip A', year=2026, country=philippines, region=region)
        DiveTrip.objects.create(title='Trip B', year=2026, country=philippines, region=region)

        self.fix()

        region.refresh_from_db()
        self.assertEqual(region.country_id, philippines.pk)

    def test_leaves_a_region_alone_when_its_trips_disagree_with_each_other(self):
        # Some trips agree with the region, some don't -- a real judgment call, not something
        # to guess at automatically.
        solomon = Country.objects.create(name='איי שלמה')
        philippines = Country.objects.create(name='פיליפינים')
        sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='אנילאו', country=solomon, sea=sea)
        DiveTrip.objects.create(title='Trip A', year=2026, country=philippines, region=region)
        DiveTrip.objects.create(title='Trip B', year=2026, country=solomon, region=region)

        self.fix()

        region.refresh_from_db()
        self.assertEqual(region.country_id, solomon.pk)

    def test_leaves_a_region_with_no_referencing_trips_alone(self):
        solomon = Country.objects.create(name='איי שלמה')
        sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='Unused region', country=solomon, sea=sea)

        self.fix()

        region.refresh_from_db()
        self.assertEqual(region.country_id, solomon.pk)
