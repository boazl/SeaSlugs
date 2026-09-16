from pathlib import Path
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth.models import User
from .models import Sample, Species, Country, Region, Sea, DiveTrip, SpeciesArea
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
        data=dict(owner=owner,species=self.species,trip=self.trip,video_url='https://youtu.be/abcdefghijk')
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
        # A table/bundle transfer applies with a plain .save(), never save_reviewed(), so it
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
