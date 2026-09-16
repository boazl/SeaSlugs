import tempfile
from io import BytesIO
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
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
        return dict(species=str(self.species.pk),trip=str(self.trip.pk),site='',video_url='https://youtu.be/abcdefghijk')
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
    def test_form_other_and_invalid_date(self):
        d=self.data();d.update(species='other',species_other='New species')
        form=SampleForm(d,instance=Sample(owner=self.user));self.assertTrue(form.is_valid(),form.errors)
        form.save(commit=False).save_reviewed()
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
        d=self.data();d.update(species='other',species_other='Needs identification')
        self.assertEqual(self.client.post(f'/observations/{item.pk}/edit/',d).status_code,302)
        item.refresh_from_db();self.assertEqual(item.status,'pending')
        self.client.logout();self.assertEqual(self.client.get('/observations/').status_code,302)
