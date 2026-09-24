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
        self.country=Country.objects.create(name='Philippines')
        sea=Sea.objects.create(name='Indo Pacific')
        self.region=Region.objects.create(name='Romblon',country=self.country,sea=sea)
        self.trip=DiveTrip.objects.create(code='V',title='Romblon',species_count=153,year=2026,country=self.country,region=self.region)
        self.species=Species.objects.create(scientific_name='Test species')

    def collection(self):
        return Sample(owner=self.user,kind='collection',trip=self.trip,title='Trip collection',video_url='https://youtu.be/abcdefghijk')

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
        # species_count (the field) is deliberately left at 153 (set in setUp) to prove the
        # displayed/catalog count ignores it and reflects only real published species samples.
        for name in ['Species A','Species B','Species C','Species D']:
            species_sample=Sample(owner=self.user,kind='species',trip=self.trip,species=Species.objects.create(scientific_name=name),video_url='https://youtu.be/abcdefghijk')
            species_sample.save_reviewed()
        sample=self.collection();sample.save_reviewed()
        self.assertNotContains(self.client.get('/observations/trips/'),'Trip collection')
        sample.save_reviewed(actor=self.user,approve=True)
        response=self.client.get('/observations/trips/')
        self.assertContains(response,'Trip collection');self.assertContains(response,'<strong>4</strong>')
        catalog=json.loads(self.client.get('/catalog.js').content.decode().split('=',1)[1].strip().removesuffix(';'))
        self.assertEqual(len(catalog['species']), 4)
        self.assertEqual(len(catalog['collections']), 1)
        self.assertEqual(catalog['collections'][0]['species_count'], 4)
        self.assertEqual(catalog['collections'][0]['year'], 2026)
        sample.soft_delete(self.user)
        self.assertNotContains(self.client.get('/observations/trips/'),'Trip collection')
        catalog=json.loads(self.client.get('/catalog.js').content.decode().split('=',1)[1].strip().removesuffix(';'))
        self.assertEqual(catalog['collections'], [])

    def test_collection_form_and_transfer(self):
        data={'title':'Collection','kind':'collection','trip':self.trip.pk,'species':'','video_url':'https://youtu.be/abcdefghijk'}
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

    def test_species_count_is_computed_from_published_species_only(self):
        self.trip.species_count=None;self.trip.save()
        self.assertEqual(self.trip.display_species_count,0)
        # a pending (unreviewed) species sample must not count yet
        pending=self.collection();pending.kind='species';pending.species=self.species;pending.save()
        self.assertEqual(self.trip.display_species_count,0)
        # publishing it (species samples auto-publish once complete) makes it count
        pending.save_reviewed()
        self.assertEqual(self.trip.display_species_count,1)
        # a second published sample of the SAME species must not double-count
        dup=self.collection();dup.kind='species';dup.species=self.species;dup.save_reviewed()
        self.assertEqual(self.trip.display_species_count,1)
        # a soft-deleted species sample must not count
        removed=self.collection();removed.kind='species'
        removed.species=Species.objects.create(scientific_name='Deleted species')
        removed.save_reviewed();removed.soft_delete(self.user)
        self.assertEqual(self.trip.display_species_count,1)
        collection=self.collection();collection.save_reviewed(actor=self.user,approve=True)
        catalog=json.loads(self.client.get('/catalog.js').content.decode().split('=',1)[1].strip().removesuffix(';'))
        self.assertEqual(catalog['collections'][0]['species_count'],1)
        # the manually-reported species_count field must never affect the displayed/computed number
        self.trip.species_count=999;self.trip.save()
        self.assertEqual(self.trip.display_species_count,1)
        self.trip.species_count=0;self.trip.save()
        self.assertEqual(self.trip.display_species_count,1)

    def test_catalog_trip_membership_and_credit(self):
        self.trip.photographer='Trip photographer';self.trip.save()
        collection=self.collection();collection.save_reviewed(actor=self.user,approve=True)
        sample=Sample(owner=self.user,species=self.species,trip=self.trip,video_url='https://youtu.be/zyxwvutsrqp')
        sample.save_reviewed()
        data=json.loads(self.client.get('/catalog.js').content.decode().split('=',1)[1].strip().removesuffix(';'))
        self.assertEqual(data['species'][0]['samples'][0]['trip_id'],data['collections'][0]['trip_id'])
        self.assertEqual(data['species'][0]['samples'][0]['photographer'],'Trip photographer')
        sample.trip=None;self.user.first_name='Dana';self.user.save()
        self.assertEqual(sample.photographer_name,'Dana')

    def test_profile_form_saves_hebrew_first_and_last_name(self):
        # first_name/last_name are not real Profile fields -- the form piggybacks
        # them and syncs onto the linked User model, which is where the Hebrew name
        # actually lives.
        from .models import Profile
        from .forms import ProfileForm
        profile=Profile.objects.create(user=self.user)
        form=ProfileForm({'first_name':'Dana','last_name':'Cohen'},instance=profile)
        self.assertTrue(form.is_valid(),form.errors);form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name,'Dana')
        self.assertEqual(self.user.last_name,'Cohen')

    def test_nav_greeting_uses_hebrew_first_name(self):
        self.user.first_name='דנה';self.user.save()
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/'),'<bdi>דנה</bdi>')

    def test_nav_greeting_prefers_english_first_name_in_english_mode(self):
        from .models import Profile
        self.user.first_name='דנה';self.user.save()
        Profile.objects.create(user=self.user,first_name_en='Dana')
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/?lang=en'),'<bdi>Dana</bdi>')
        self.assertContains(self.client.get('/?lang=he'),'<bdi>דנה</bdi>')

    def test_nav_greeting_falls_back_to_other_language_when_one_is_missing(self):
        from .models import Profile
        self.user.first_name='דנה';self.user.save()
        Profile.objects.create(user=self.user)  # no first_name_en set
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/?lang=en'),'<bdi>דנה</bdi>')

    def test_logout_label_translates_in_english_mode(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/'),'>יציאה<')
        self.assertContains(self.client.get('/?lang=en'),'>Logout<')

    def test_photographer_credit_resolves_registered_user_by_language(self):
        # DiveTrip.photographer is free text (an admin can credit a guest photographer
        # with no account here) -- but when it matches a registered user's full name,
        # the credit should resolve through that user's profile the same way the nav
        # greeting does, so it too has an English form.
        from .models import Profile
        self.user.first_name='בעז';self.user.last_name='ליבס';self.user.save()
        Profile.objects.create(user=self.user,first_name_en='Boaz',last_name_en='Liebes')
        self.trip.photographer='בעז ליבס';self.trip.save()
        sample=Sample(owner=self.user,species=self.species,trip=self.trip,video_url='https://youtu.be/zyxwvutsrqp')
        self.assertEqual(sample.photographer_display_name('he'),'בעז ליבס')
        self.assertEqual(sample.photographer_display_name('en'),'Boaz Liebes')

    def test_photographer_credit_leaves_unregistered_name_unchanged(self):
        # A guest photographer with no account has no profile to resolve against, so
        # the free text is shown as-is regardless of language.
        self.trip.photographer='Bart Adams';self.trip.save()
        sample=Sample(owner=self.user,species=self.species,trip=self.trip,video_url='https://youtu.be/zyxwvutsrqp')
        self.assertEqual(sample.photographer_display_name('he'),'Bart Adams')
        self.assertEqual(sample.photographer_display_name('en'),'Bart Adams')

    def test_profile_english_names_and_phone_are_saved(self):
        from .models import Profile
        from .forms import ProfileForm
        profile=Profile.objects.create(user=self.user)
        form=ProfileForm({'first_name':'Dana','first_name_en':'Dana','last_name_en':'Cohen','phone':'+972 50-123-4567'},instance=profile)
        self.assertTrue(form.is_valid(),form.errors);form.save()
        profile.refresh_from_db()
        self.assertEqual(profile.first_name_en,'Dana')
        self.assertEqual(profile.last_name_en,'Cohen')
        self.assertEqual(profile.phone,'+972 50-123-4567')

    def test_profile_phone_validator_rejects_garbage(self):
        from .models import Profile
        from .forms import ProfileForm
        profile=Profile.objects.create(user=self.user)
        form=ProfileForm({'first_name':'','phone':'not a phone number!!'},instance=profile)
        self.assertFalse(form.is_valid())
        self.assertIn('phone',form.errors)

    def test_user_admin_change_page_shows_profile_fields(self):
        admin_user=User.objects.create_superuser('admin','admin@example.com','pw')
        self.client.force_login(admin_user)
        response=self.client.get(f'/admin/auth/user/{self.user.pk}/change/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'name="profile-0-first_name_en"')
        self.assertContains(response,'name="profile-0-last_name_en"')
        self.assertContains(response,'name="profile-0-phone"')
