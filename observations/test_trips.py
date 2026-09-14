import json
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import DiveTrip, Sample, Species, Country, Sea, Region
from .forms import SampleForm
from .table_transfer import export_table, plan


class DiveTripTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('owner')
        self.trip=DiveTrip.objects.create(code='V',title='Romblon',species_count=153)
        self.country=Country.objects.create(name='Philippines')
        sea=Sea.objects.create(name='Indo Pacific')
        self.region=Region.objects.create(name='Romblon',country=self.country,sea=sea)
        self.species=Species.objects.create(scientific_name='Test species')

    def collection(self):
        return Sample(owner=self.user,kind='collection',trip=self.trip,title='Trip collection',year=2026,country=self.country,region=self.region,video_url='https://youtu.be/abcdefghijk')

    def test_collection_needs_trip_not_species_and_admin_approval(self):
        sample=self.collection();sample.trip=None
        with self.assertRaises(ValidationError): sample.full_clean()
        sample.trip=self.trip;sample.species=self.species
        with self.assertRaises(ValidationError): sample.full_clean()
        sample.species=None;sample.save_reviewed()
        self.assertEqual(sample.status,'pending')
        sample.save_reviewed(actor=self.user,approve=True)
        self.assertEqual(sample.status,'published')

    def test_public_separation_and_soft_delete(self):
        sample=self.collection();sample.save_reviewed()
        self.assertNotContains(self.client.get('/observations/trips/'),'Trip collection')
        sample.save_reviewed(actor=self.user,approve=True)
        response=self.client.get('/observations/trips/')
        self.assertContains(response,'Trip collection');self.assertContains(response,'153')
        catalog=json.loads(self.client.get('/catalog.js').content.decode().split('=',1)[1].strip().removesuffix(';'))
        self.assertEqual(catalog['videos'],[])
        self.assertEqual(len(catalog['collections']), 1)
        self.assertEqual(catalog['collections'][0]['species_count'], 153)
        self.assertEqual(catalog['collections'][0]['year'], 2026)
        sample.soft_delete(self.user)
        self.assertNotContains(self.client.get('/observations/trips/'),'Trip collection')
        catalog=json.loads(self.client.get('/catalog.js').content.decode().split('=',1)[1].strip().removesuffix(';'))
        self.assertEqual(catalog['collections'], [])

    def test_collection_form_and_transfer(self):
        data={'title':'Collection','kind':'collection','trip':self.trip.pk,'species':'','country':str(self.country.pk),'region':str(self.region.pk),'year':2026,'video_url':'https://youtu.be/abcdefghijk'}
        form=SampleForm(data,instance=Sample(owner=self.user))
        self.assertTrue(form.is_valid(),form.errors)
        sample=form.save(commit=False);sample.save_reviewed(actor=self.user,approve=True)
        self.assertEqual(plan(export_table('trips'))[0]['action'],'same')
        doc=export_table('samples')
        self.assertEqual(doc['rows'][0]['trip'],'V')
        self.assertEqual(plan(doc)[0]['action'],'same')
        doc['rows'][0]['trip']='missing'
        with self.assertRaises(ValidationError): plan(doc)

    def test_single_species_still_requires_identification(self):
        sample=self.collection();sample.kind='species'
        with self.assertRaises(ValidationError):sample.full_clean()

    def test_missing_count_uses_distinct_linked_species(self):
        self.trip.species_count=None;self.trip.save()
        self.assertEqual(self.trip.display_species_count,0)
        for _ in range(2):
            sample=self.collection();sample.kind='species';sample.species=self.species;sample.save()
        removed=self.collection();removed.kind='species'
        removed.species=Species.objects.create(scientific_name='Deleted species')
        removed.save();removed.soft_delete(self.user)
        collection=self.collection();collection.save_reviewed(actor=self.user,approve=True)
        self.assertEqual(self.trip.display_species_count,1)
        catalog=json.loads(self.client.get('/catalog.js').content.decode().split('=',1)[1].strip().removesuffix(';'))
        self.assertEqual(catalog['collections'][0]['species_count'],1)
        self.trip.species_count=0
        self.assertEqual(self.trip.display_species_count,0)
        self.trip.species_count=153
        self.assertEqual(self.trip.display_species_count,153)

    def test_catalog_trip_membership_and_credit(self):
        self.trip.photographer='Trip photographer';self.trip.save()
        collection=self.collection();collection.save_reviewed(actor=self.user,approve=True)
        sample=Sample(owner=self.user,species=self.species,trip=self.trip,year=2026,country=self.country,region=self.region,video_url='https://youtu.be/zyxwvutsrqp')
        sample.save_reviewed()
        data=json.loads(self.client.get('/catalog.js').content.decode().split('=',1)[1].strip().removesuffix(';'))
        self.assertEqual(data['videos'][0]['trip_id'],data['collections'][0]['trip_id'])
        self.assertEqual(data['videos'][0]['photographer'],'Trip photographer')
        sample.trip=None;self.user.first_name='Dana';self.user.save()
        self.assertEqual(sample.photographer_name,'Dana')

    def test_profile_first_name_is_saved(self):
        from .models import Profile
        from .forms import ProfileForm
        profile=Profile.objects.create(user=self.user,display_name='Public name')
        form=ProfileForm({'display_name':'Public name','first_name':'Dana'},instance=profile)
        self.assertTrue(form.is_valid(),form.errors);form.save()
        self.user.refresh_from_db();self.assertEqual(self.user.first_name,'Dana')
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/'),'<bdi>Dana</bdi>')
