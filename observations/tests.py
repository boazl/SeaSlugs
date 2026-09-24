import tempfile
from io import BytesIO
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from .models import Country, Sea, Region, Site, Species, Sample, DiveTrip, SpeciesArea
from .forms import SampleForm, DiveTripForm

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class WorkflowTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('owner',password='a-valid-password-927')
        self.other=User.objects.create_user('other',password='a-valid-password-927')
        self.country=Country.objects.create(name='Israel')
        self.sea=Sea.objects.create(name='Mediterranean')
        self.region=Region.objects.create(name='Akhziv',country=self.country,sea=self.sea)
        self.trip=DiveTrip.objects.create(title='Akhziv dive',year=2026,month=2,country=self.country,region=self.region)
        self.species=Species.objects.create(scientific_name='Test species')
    def record(self,**kwargs):
        data=dict(owner=self.user,species=self.species,trip=self.trip,video_url='https://youtu.be/abcdefghijk')
        data.update(kwargs)
        item=Sample(**data);item.save_reviewed();return item
    def data(self):
        return dict(species=self.species.scientific_name,trip=str(self.trip.pk),site='',video_url='https://youtu.be/abcdefghijk')
    def test_first_repeat_other_and_approval(self):
        first=self.record();self.assertEqual(first.status,'published')
        area=SpeciesArea.objects.get(species=self.species,country=self.country,sea=self.sea)
        self.assertEqual(area.defining_sample_id,first.pk)
        repeat=self.record();self.assertEqual(repeat.status,'published')
        # a second published sample of the same species+area is allowed, and does not
        # change which sample defines the species in the gallery
        area.refresh_from_db();self.assertEqual(area.defining_sample_id,first.pk)
        unknown=self.record(species=None,species_other='Unknown');self.assertEqual(unknown.status,'pending')
        with self.assertRaises(ValidationError):unknown.save_reviewed(actor=self.user,approve=True)
    def test_genus_kind_sample_with_species_other_can_be_approved_and_published(self):
        # A GENUS-kind sample identifies only a genus (via species_other, e.g. "Chromodoris"),
        # never a specific species -- unlike a SPECIES-kind sample's "other" escape hatch, this
        # is a deliberate, permanent identification, not an unresolved placeholder, so approval
        # must succeed even though species_other is set and species stays unlinked.
        genus_sample = Sample(owner=self.user, kind=Sample.Kind.GENUS, species_other='Chromodoris',
                               trip=self.trip, video_url='https://youtu.be/abcdefghijk')
        genus_sample.save_reviewed(actor=self.user, approve=True)
        self.assertEqual(genus_sample.status, 'published')
        self.assertEqual(genus_sample.species_other, 'Chromodoris')
        self.assertIsNone(genus_sample.species_id)
    def test_genus_kind_sample_publication_reasons_omit_the_species_other_warning(self):
        genus_sample = Sample.objects.create(owner=self.user, kind=Sample.Kind.GENUS, species_other='Chromodoris',
                                              trip=self.trip, video_url='https://youtu.be/abcdefghijk')
        reasons = genus_sample.publication_reasons()
        self.assertFalse(any('להחליף את ערך המין' in reason for reason in reasons))
    def test_species_kind_sample_with_species_other_still_blocks_approval(self):
        # Unchanged regression coverage: the GENUS-kind exception must not leak into the
        # default SPECIES kind, where species_other remains an incomplete placeholder.
        species_other_sample = Sample(owner=self.user, species=None, species_other='Unknown species',
                                       trip=self.trip, video_url='https://youtu.be/abcdefghijk')
        species_other_sample.save_reviewed()
        self.assertEqual(species_other_sample.status, 'pending')
        with self.assertRaises(ValidationError):
            species_other_sample.save_reviewed(actor=self.user, approve=True)
        reasons = species_other_sample.publication_reasons()
        self.assertTrue(any('להחליף את ערך המין' in reason for reason in reasons))
    def test_form_other_and_invalid_date(self):
        d=self.data();d.update(species='',species_other='New species')
        form=SampleForm(d,instance=Sample(owner=self.user));self.assertTrue(form.is_valid(),form.errors)
        saved=form.save(commit=False);self.assertIsNone(saved.species_id);self.assertEqual(saved.species_other,'New species')
        saved.save_reviewed()
        d=self.data();d.update(day=30)  # self.trip is in February; the 30th does not exist
        self.assertFalse(SampleForm(d,instance=Sample(owner=self.user)).is_valid())
    def test_trip_form_rejects_mismatched_region(self):
        foreign=Country.objects.create(name='Other country')
        form=DiveTripForm(dict(title='Bad trip',country=str(foreign.pk),region=str(self.region.pk),year='2026'))
        self.assertFalse(form.is_valid())
    def test_trip_new_view_creates_trip_and_redirects_with_selection(self):
        self.client.force_login(self.user)
        other_region=Region.objects.create(name='Caesarea',country=self.country,sea=self.sea)
        response=self.client.post('/observations/trips/new/?next=/observations/new/',
            {'title':'New local dive','country':str(self.country.pk),'region':str(other_region.pk),'year':'2026','next':'/observations/new/'})
        self.assertEqual(response.status_code,302)
        new_trip=DiveTrip.objects.get(title='New local dive')
        self.assertEqual(response.url,f'/observations/new/?trip={new_trip.pk}')
        self.assertEqual(new_trip.region_id,other_region.pk)
    def test_ownership_visibility_and_soft_delete(self):
        item=self.record()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(f'/observations/{item.pk}/remove/').status_code,404)
        self.assertEqual(self.client.get(f'/observations/{item.pk}/edit/').status_code,404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/observations/{item.pk}/remove/').status_code,405)
        self.assertEqual(self.client.post(f'/observations/{item.pk}/remove/').status_code,302)
        item.refresh_from_db();self.assertIsNotNone(item.deleted_at)
        self.client.logout();self.assertEqual(self.client.get('/observations/').status_code,302)
        manager=User.objects.create_superuser('admin','admin@example.com','valid-password-912')
        self.client.force_login(manager);self.assertContains(self.client.get('/observations/'),'מחוקה')

    def test_admin_approve_skips_deleted_samples_with_a_warning(self):
        # A soft-deleted sample still shows its last status (e.g. "מפורסמת") in the admin
        # list -- easy to mistake for "already fine" -- but approving it is a deliberate
        # no-op; it must say so instead of leaving the deletion unexplained.
        manager=User.objects.create_superuser('admin','admin@example.com','valid-password-912')
        item=self.record();item.soft_delete(self.user)
        self.client.force_login(manager)
        response=self.client.post('/admin/observations/sample/',
            {'action':'approve','_selected_action':[str(item.pk)],'index':'0'},follow=True)
        item.refresh_from_db();self.assertIsNotNone(item.deleted_at)
        self.assertContains(response,'שחזור לבדיקה מחדש')

        response=self.client.post('/admin/observations/sample/',
            {'action':'restore','_selected_action':[str(item.pk)],'index':'0'},follow=True)
        item.refresh_from_db();self.assertIsNone(item.deleted_at);self.assertEqual(item.status,'published')

    def test_manager_can_edit_any_or_deleted_sample_but_others_cannot(self):
        # The image manager (and the observations list) point a manager straight at the
        # app's own edit form for any sample, including someone else's or an already
        # soft-deleted one -- everyone else stays limited to their own, active samples.
        item=self.record()
        manager=User.objects.create_superuser('admin','admin@example.com','valid-password-912')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/observations/{item.pk}/edit/').status_code,404)
        self.client.force_login(manager)
        self.assertEqual(self.client.get(f'/observations/{item.pk}/edit/').status_code,200)
        item.soft_delete(self.user)
        self.assertEqual(self.client.get(f'/observations/{item.pk}/edit/').status_code,200)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/observations/{item.pk}/edit/').status_code,404)  # owner, but now deleted
    def test_form_upload_compressed(self):
        output=BytesIO();Image.new('RGB',(2000,1800),'blue').save(output,'PNG')
        form=SampleForm(self.data(),{'image':SimpleUploadedFile('test.png',output.getvalue(),content_type='image/png')},instance=Sample(owner=self.user))
        self.assertTrue(form.is_valid(),form.errors)
        image=Image.open(form.cleaned_data['image']);self.assertLessEqual(image.width,1920);self.assertLessEqual(image.height,1080);self.assertEqual(image.format,'JPEG')
    def test_photo_only_gallery_and_permissions(self):
        import json
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            output=BytesIO();Image.new('RGB',(3840,2160),'blue').save(output,'JPEG')
            data=self.data();data['video_url']=''
            form=SampleForm(data,{'image':SimpleUploadedFile('photo.jpg',output.getvalue(),content_type='image/jpeg')},instance=Sample(owner=self.user))
            self.assertTrue(form.is_valid(),form.errors)
            self.assertEqual(Image.open(form.cleaned_data['image']).size,(1920,1080))
            item=form.save(commit=False);item.save_reviewed()
            catalog=json.loads(self.client.get('/catalog.js').content.decode().removeprefix('window.SEASLUGS = ').removesuffix(';'))
            entry=catalog['species'][0]
            self.assertIsNone(entry['video_id']);self.assertEqual(entry['thumbnail'],entry['image_url'])
            url=f'/observations/{item.pk}/photo/'
            response=self.client.get(url);self.assertEqual(response.status_code,200);response.close()
            item.status='pending';item.save()
            self.assertEqual(self.client.get(url).status_code,404)
            self.client.force_login(self.user)
            response=self.client.get(url);self.assertEqual(response.status_code,200);response.close()
            cleared=dict(data,**{'image-clear':'on'})
            self.assertFalse(SampleForm(cleared,instance=item).is_valid())
            self.client.force_login(self.other);self.assertEqual(self.client.get(url).status_code,404)

    def test_media_required_and_small_photo_not_enlarged(self):
        data=self.data();data['video_url']=''
        form=SampleForm(data,instance=Sample(owner=self.user))
        self.assertFalse(form.is_valid());self.assertIn('video_url',form.errors)
        output=BytesIO();Image.new('RGB',(400,600),'blue').save(output,'PNG')
        form=SampleForm(data,{'image':SimpleUploadedFile('small.png',output.getvalue(),content_type='image/png')},instance=Sample(owner=self.user))
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(Image.open(form.cleaned_data['image']).size,(400,600))

    def test_routes_signup_no_privilege_escalation(self):
        for url in ['/observations/login/','/observations/signup/']:
            self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.get('/observations/new/').status_code,302)
        response=self.client.post('/observations/signup/',dict(username='fresh',email='fresh@example.com',password1='really-unusual-password-731',password2='really-unusual-password-731',is_staff='1',is_superuser='1'))
        self.assertEqual(response.status_code,302)
        user=User.objects.get(username='fresh');self.assertFalse(user.is_staff);self.assertFalse(user.is_superuser)
        self.assertEqual(self.client.get('/observations/profile/').status_code,200)
        self.assertEqual(self.client.get('/observations/partners/').status_code,200)
    def test_post_and_edit_rechecks_publication(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/observations/new/',self.data()).status_code,302)
        item=Sample.objects.get();self.assertEqual(item.status,'published')
        d=self.data();d.update(species='',species_other='Needs identification')
        self.assertEqual(self.client.post(f'/observations/{item.pk}/edit/',d).status_code,302)
        item.refresh_from_db();self.assertEqual(item.status,'pending')
        self.client.logout();self.assertEqual(self.client.get('/observations/').status_code,302)

    def test_species_search_browses_all_when_query_is_empty(self):
        # The species picker on the observation form opens as a browsable dropdown on
        # focus/click, before anything is typed -- so the endpoint it calls must return
        # results for an empty query too, not just for an actual search term.
        self.client.force_login(self.user)
        Species.objects.create(scientific_name='Aaa species')
        labels = self.client.get('/observations/species-search/').json()['results']
        labels = [row['label'] for row in labels]
        self.assertIn('Test species', labels)
        self.assertIn('Aaa species', labels)
        self.assertLess(labels.index('Aaa species'), labels.index('Test species'))

    def test_species_search_still_filters_by_query(self):
        self.client.force_login(self.user)
        Species.objects.create(scientific_name='Aaa species')
        results = self.client.get('/observations/species-search/?q=Test').json()['results']
        self.assertEqual([row['label'] for row in results], ['Test species'])

    def test_species_area_status_endpoint(self):
        # Drives the live "does this observation define the species / does the species
        # appear in the gallery" message on the edit form, which re-checks whenever the
        # species or trip field changes (a SpeciesArea is keyed by species+country+sea).
        self.client.force_login(self.user)
        resp = self.client.get('/observations/species-area-status/', {'species': 'Nope', 'trip': '999'}).json()
        self.assertEqual(resp, {'matched': False})

        first = self.record()  # the first published sample of a species+area becomes defining
        resp = self.client.get('/observations/species-area-status/',
            {'species': self.species.scientific_name, 'trip': self.trip.pk, 'sample': first.pk}).json()
        # no other sample of the species exists yet, so releasing it would leave the area empty
        self.assertEqual(resp, {'matched': True, 'is_defining': True, 'appears': True, 'next': {'kind': 'single'}})

        second = self.record()  # a second published sample of the same species+area is not
        resp = self.client.get('/observations/species-area-status/',
            {'species': self.species.scientific_name, 'trip': self.trip.pk, 'sample': second.pk}).json()
        self.assertEqual(resp, {'matched': True, 'is_defining': False, 'appears': True, 'next': None})

        # a species with no published sample anywhere in this trip's area yet
        Species.objects.create(scientific_name='Not yet published')
        resp = self.client.get('/observations/species-area-status/',
            {'species': 'Not yet published', 'trip': self.trip.pk}).json()
        self.assertEqual(resp, {'matched': True, 'is_defining': False, 'appears': False, 'next': None})

    def test_next_candidate_prefers_most_recent_with_media_then_falls_back(self):
        first = self.record()
        self.assertEqual(SpeciesArea.next_candidate(self.species.pk, self.country.pk, self.sea, first.pk), {'kind': 'single'})

        # a media-less sample can exist (bulk-imported data bypasses Sample.clean, which a
        # plain .save()/.create() does not run) -- next_candidate should notice it exists
        # without treating it as a usable replacement
        medialess = Sample.objects.create(owner=self.user, species=self.species, trip=self.trip,
            kind=Sample.Kind.SPECIES, status=Sample.Status.PUBLISHED, video_url='', image='')
        self.assertEqual(SpeciesArea.next_candidate(self.species.pk, self.country.pk, self.sea, first.pk), {'kind': 'without_media'})

        third = self.record()
        result = SpeciesArea.next_candidate(self.species.pk, self.country.pk, self.sea, first.pk)
        self.assertEqual(result, {'kind': 'with_media', 'sample': third})

        fourth = self.record()  # more recently created than third -- should now be preferred
        result = SpeciesArea.next_candidate(self.species.pk, self.country.pk, self.sea, first.pk)
        self.assertEqual(result, {'kind': 'with_media', 'sample': fourth})

    def test_species_field_matches_case_insensitively_and_edit_prefills_scientific_name(self):
        d=self.data();d.update(species=self.species.scientific_name.upper())
        form=SampleForm(d,instance=Sample(owner=self.user));self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['species'],self.species)
        item=form.save(commit=False);item.save_reviewed()
        # editing an existing item must show its scientific name in the field, not its pk
        self.assertEqual(SampleForm(instance=item).initial['species'],self.species.scientific_name)

    def test_species_options_datalist_and_visible_species_other(self):
        self.client.force_login(self.user)
        content=self.client.get('/observations/new/').content.decode()
        self.assertIn('<datalist id="species-options">',content)
        self.assertIn(f'<option value="{self.species.scientific_name}">',content)
        self.assertIn('list="species-options"',content)
        # species_other is a distinct, always-visible field -- the deliberate manual
        # override for a species that isn't in the table -- not something derived
        # silently from the species search box.
        self.assertIn('type="text" name="species_other"',content)

    def test_species_must_match_the_catalog_unless_other_is_specified(self):
        d=self.data();d.update(species='Nonexistent name')
        form=SampleForm(d,instance=Sample(owner=self.user))
        self.assertFalse(form.is_valid())
        self.assertIn('species',form.errors)
        d=self.data();d.update(species='Nonexistent name',species_other='Nonexistent name')
        form=SampleForm(d,instance=Sample(owner=self.user))
        self.assertTrue(form.is_valid(),form.errors)
        self.assertIsNone(form.cleaned_data['species'])
        self.assertEqual(form.cleaned_data['species_other'],'Nonexistent name')

    def test_observation_form_shows_image_thumbnail_preview(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self.client.force_login(self.user)
            output=BytesIO();Image.new('RGB',(400,600),'blue').save(output,'PNG')
            data=dict(self.data(),image=SimpleUploadedFile('a.png',output.getvalue(),content_type='image/png'))
            self.assertEqual(self.client.post('/observations/new/',data).status_code,302)
            item=Sample.objects.get()
            content=self.client.get(f'/observations/{item.pk}/edit/').content.decode()
            self.assertIn(f'<img src="/observations/{item.pk}/photo/"',content)
            # a fresh, unsaved form has no existing image yet -- nothing to preview
            content=self.client.get('/observations/new/').content.decode()
            self.assertNotIn('<img src="/observations/',content)

    def test_observation_form_wires_up_the_live_defining_status_check(self):
        self.client.force_login(self.user)
        content=self.client.get('/observations/new/').content.decode()
        self.assertIn('id="defining-status"',content)
        self.assertIn('/observations/species-area-status/',content)
        self.assertIn('const sampleId=null;',content)  # new/unsaved sample
        # the release/delete-image/delete-video actions only make sense for a saved sample
        self.assertNotIn('id="release-species-form"',content)
        self.assertNotIn('id="delete-image-btn"',content)
        item=self.record()
        content=self.client.get(f'/observations/{item.pk}/edit/').content.decode()
        self.assertIn(f'const sampleId={item.pk};',content)
        self.assertIn(f'/observations/{item.pk}/action/',content)
        self.assertIn('id="release-species-form" hidden',content)  # hidden until the live check confirms it
        self.assertIn('id="delete-image-btn" data-has-image="" disabled',content)  # self.record() has no image
        self.assertIn('id="delete-video-btn" data-has-video="1" >',content)  # self.record() has a video_url, so not disabled

    def test_observation_action_requires_ownership_and_post(self):
        item = self.record()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(f'/observations/{item.pk}/action/', {'action': 'release_species'}).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/observations/{item.pk}/action/').status_code, 405)
        response = self.client.post(f'/observations/{item.pk}/action/', {'action': 'nonsense'}, follow=True)
        self.assertContains(response, 'פעולה לא מוכרת.')

    def test_observation_action_release_species_hands_off_to_next_candidate(self):
        self.client.force_login(self.user)
        first = self.record()
        second = self.record()
        area = SpeciesArea.objects.get(species=self.species, country=self.country, sea=self.sea)
        self.assertEqual(area.defining_sample_id, first.pk)

        # releasing a sample that isn't currently defining the species is a no-op with an error
        response = self.client.post(f'/observations/{second.pk}/action/', {'action': 'release_species'}, follow=True)
        self.assertContains(response, 'התצפית אינה מגדירה את המין כרגע.')
        area.refresh_from_db();self.assertEqual(area.defining_sample_id, first.pk)

        response = self.client.post(f'/observations/{first.pk}/action/', {'action': 'release_species'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'/observations/{first.pk}/edit/')
        # first is released; second is still published, so it takes over as defining
        area.refresh_from_db();self.assertEqual(area.defining_sample_id, second.pk)

        # once second is the only published sample left (first has been withdrawn entirely,
        # not merely released), releasing it clears the area rather than handing off to first
        first.soft_delete(self.user)
        response = self.client.post(f'/observations/{second.pk}/action/', {'action': 'release_species'}, follow=True)
        self.assertContains(response, 'המין שנבחר אינו מופיע בגלריה.')
        area.refresh_from_db();self.assertIsNone(area.defining_sample_id)

    def test_observation_action_delete_image_and_video_blocked_while_defining(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self.client.force_login(self.user)
            output = BytesIO();Image.new('RGB', (400, 600), 'blue').save(output, 'PNG')
            data = dict(self.data(), image=SimpleUploadedFile('a.png', output.getvalue(), content_type='image/png'))
            self.assertEqual(self.client.post('/observations/new/', data).status_code, 302)
            item = Sample.objects.get()
            self.assertTrue(item.image);image_name = item.image.name
            self.assertTrue(default_storage.exists(image_name))
            area = SpeciesArea.objects.get(species=self.species, country=self.country, sea=self.sea)
            self.assertEqual(area.defining_sample_id, item.pk)  # the only sample -- currently defining

            for action, message in [('delete_image', 'לא ניתן למחוק את התמונה כאשר התצפית מגדירה את המין. יש להסיר קודם את התצפית מהמין.'),
                                     ('delete_video', 'לא ניתן למחוק את קישור הסרטון כאשר התצפית מגדירה את המין. יש להסיר קודם את התצפית מהמין.')]:
                response = self.client.post(f'/observations/{item.pk}/action/', {'action': action}, follow=True)
                self.assertContains(response, message)
            item.refresh_from_db()
            self.assertTrue(item.image);self.assertTrue(item.video_url);self.assertTrue(default_storage.exists(image_name))

            self.client.post(f'/observations/{item.pk}/action/', {'action': 'release_species'})
            area.refresh_from_db();self.assertIsNone(area.defining_sample_id)

            # no longer defining -- the file is genuinely deleted since nothing else uses it
            response = self.client.post(f'/observations/{item.pk}/action/', {'action': 'delete_image'}, follow=True)
            self.assertContains(response, 'התמונה נמחקה.')
            item.refresh_from_db();self.assertFalse(item.image);self.assertFalse(default_storage.exists(image_name))

            response = self.client.post(f'/observations/{item.pk}/action/', {'action': 'delete_video'}, follow=True)
            self.assertContains(response, 'קישור הסרטון נמחק.')
            item.refresh_from_db();self.assertEqual(item.video_url, '')

            # deleting again reports there is nothing left to delete rather than erroring
            response = self.client.post(f'/observations/{item.pk}/action/', {'action': 'delete_image'}, follow=True)
            self.assertContains(response, 'לתצפית זו אין תמונה.')

    def test_observation_action_delete_image_keeps_file_when_another_sample_shares_it(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            name = default_storage.save('observations/transfer/shared.jpg', ContentFile(b'fake-bytes'))
            a = Sample.objects.create(owner=self.user, species=self.species, trip=self.trip, image=name,
                video_url='', kind=Sample.Kind.SPECIES, status=Sample.Status.PUBLISHED)
            b = Sample.objects.create(owner=self.user, species=self.species, trip=self.trip, image=name,
                video_url='https://youtu.be/abcdefghijk', kind=Sample.Kind.SPECIES, status=Sample.Status.PUBLISHED)
            # created directly (not through save_reviewed), so no SpeciesArea claims either one yet
            self.assertFalse(SpeciesArea.objects.filter(species=self.species).exists())
            self.client.force_login(self.user)
            response = self.client.post(f'/observations/{a.pk}/action/', {'action': 'delete_image'}, follow=True)
            self.assertContains(response, 'התמונה נמחקה.')
            a.refresh_from_db();self.assertFalse(a.image)
            b.refresh_from_db();self.assertEqual(b.image, name)
            self.assertTrue(default_storage.exists(name))  # b still references it

    def test_listing_defaults_to_alphabetical_species_order(self):
        # The list is mainly used to find one specific observation to edit, which is much
        # easier scanning alphabetically than scanning by creation date.
        self.client.force_login(self.user)
        z_species = Species.objects.create(scientific_name='Zzz species')
        self.record()  # self.species is "Test species"
        self.record(species=z_species, species_other='')
        response = self.client.get('/observations/')
        self.assertEqual(response.context['sort'], 'species')
        names = [item.species.scientific_name for item in response.context['observations']]
        self.assertEqual(names, sorted(names))

    def test_edit_redirects_back_to_the_list_url_it_came_from(self):
        # Without an explicit ?next=, fall back to the plain list -- scrolled to the
        # saved observation rather than dropped at the top with no idea where it is.
        self.client.force_login(self.user)
        item = self.record()
        response = self.client.post(f'/observations/{item.pk}/edit/', self.data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'/observations/#obs-{item.pk}')

        # With ?next= pointing at the exact filtered/sorted list URL the "עריכה" link on
        # that page carries (and the hidden `next` field resubmitting it), land back on
        # that same URL, still anchored to this observation.
        list_url = '/observations/?sort=oldest&mine=1'
        data = self.data(); data['next'] = list_url
        response = self.client.post(f'/observations/{item.pk}/edit/?next={list_url}', data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'{list_url}#obs-{item.pk}')

    def test_edit_rejects_an_unsafe_next_url(self):
        # `next` is attacker-influenceable (it round-trips through the URL and a hidden
        # form field), so an off-site target must never be honored.
        self.client.force_login(self.user)
        item = self.record()
        data = self.data(); data['next'] = 'https://evil.example/phish'
        response = self.client.post(f'/observations/{item.pk}/edit/?next=https://evil.example/phish', data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'/observations/#obs-{item.pk}')
