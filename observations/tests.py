import tempfile
from io import BytesIO
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from .models import Country, Sea, Region, Site, Species, Sample
from .forms import SampleForm

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class WorkflowTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('owner',password='a-valid-password-927')
        self.other=User.objects.create_user('other',password='a-valid-password-927')
        self.country=Country.objects.create(name='Israel')
        self.sea=Sea.objects.create(name='Mediterranean')
        self.region=Region.objects.create(name='Akhziv',country=self.country,sea=self.sea)
        self.species=Species.objects.create(scientific_name='Test species')
    def record(self,**kwargs):
        data=dict(owner=self.user,species=self.species,country=self.country,region=self.region,year=2026,video_url='https://youtu.be/abcdefghijk')
        data.update(kwargs)
        item=Sample(**data);item.save_reviewed();return item
    def data(self):
        return dict(species=str(self.species.pk),country=str(self.country.pk),region=str(self.region.pk),site='',year=2026,video_url='https://youtu.be/abcdefghijk')
    def test_first_repeat_other_and_approval(self):
        self.assertEqual(self.record().status,'published')
        repeat=self.record();self.assertEqual(repeat.status,'pending')
        repeat.save_reviewed(actor=self.user,approve=True);self.assertEqual(repeat.status,'published')
        unknown=self.record(species=None,species_other='Unknown');self.assertEqual(unknown.status,'pending')
        with self.assertRaises(ValidationError):unknown.save_reviewed(actor=self.user,approve=True)
    def test_form_other_and_invalid_hierarchy_date(self):
        d=self.data();d.update(species='other',species_other='New species')
        form=SampleForm(d,instance=Sample(owner=self.user));self.assertTrue(form.is_valid(),form.errors)
        form.save(commit=False).save_reviewed()
        d=self.data();d.update(day=30,month=2)
        self.assertFalse(SampleForm(d,instance=Sample(owner=self.user)).is_valid())
        foreign=Country.objects.create(name='Other country');d=self.data();d['country']=foreign.pk
        self.assertFalse(SampleForm(d,instance=Sample(owner=self.user)).is_valid())
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
        image=Image.open(form.cleaned_data['image']);self.assertLessEqual(max(image.size),1600);self.assertEqual(image.format,'JPEG')
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
