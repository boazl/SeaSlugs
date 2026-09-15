from .folder_import import match_species,plan_row
from .models import Species,DiveTrip,Sample
from django.core.exceptions import ValidationError
from pathlib import Path
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from .models import Country,Sea,Region
from PIL import Image
import tempfile,io

class FolderImportTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        settings=override_settings(DATA_DIR=self.temp.name,MEDIA_ROOT=self.temp.name+'/media');settings.enable();self.addCleanup(settings.disable)
        self.user=User.objects.create_superuser('importer',password='test')
        self.country=Country.objects.create(name='Philippines');sea=Sea.objects.create(name='Pacific')
        self.region=Region.objects.create(name='Romblon',country=self.country,sea=sea)
        self.trip=DiveTrip.objects.create(title='Trip',year=2026,month=1,country_name='Philippines',region_name='Romblon')
        self.species=Species.objects.create(scientific_name='Micromelo undatus')
    def photo(self):
        output=io.BytesIO();Image.new('RGB',(40,30),'blue').save(output,'JPEG')
        return SimpleUploadedFile('002-Micromelo undatus 2025.jpg',output.getvalue(),content_type='image/jpeg')
    def test_matching_keeps_species_identifiers(self):
        species=[self.species,Species.objects.create(scientific_name='Elysia sp.'),Species.objects.create(scientific_name='Elysia sp. 5')]
        self.assertEqual(match_species('002-Micromelo undatus (Author, 1900).jpg',species),self.species.pk)
        self.assertEqual(match_species('C16-Elysia sp. 5 2025.jpg',species),species[-1].pk)
        self.assertIsNone(match_species('C16-Elysia sp. 7.jpg',species))
    def test_preview_then_create_from_trip_not_filename_year(self):
        self.client.force_login(self.user)
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':self.photo()})
        self.assertEqual(Sample.objects.count(),0);self.assertIn('token',response.context)
        with patch('observations.folder_import.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/images/folder/',{'action':'apply','token':response.context['token'],'selected':['0'],'species_0':self.species.pk,'confirm':'yes'})
        self.assertEqual(response.status_code,302)
        item=Sample.objects.get();self.assertEqual(item.year,2026);self.assertEqual(item.month,1);self.assertIsNone(item.day);self.assertTrue(item.image);self.assertEqual(item.trip,self.trip)
    def test_other_trip_conflict_and_same_trip_update(self):
        item=Sample(owner=self.user,species=self.species,trip=self.trip,country=self.country,region=self.region,year=2026,video_url='https://youtu.be/abcdefghijk');item.save_reviewed()
        self.assertEqual(plan_row(self.trip,self.species.pk,self.user)[1],'update')
        other=DiveTrip.objects.create(title='Other',year=2026,country_name='Philippines',region_name='Romblon')
        with self.assertRaises(ValidationError):plan_row(other,self.species.pk,self.user)
    def test_duplicate_selection_keeps_first_and_skips_second(self):
        import hashlib
        from django.core import signing
        self.client.force_login(self.user)
        second=self.photo();second.name='002-Micromelo undatus 2026.jpg'
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':[self.photo(),second]})
        token=response.context['token']
        first_digest=response.context['rows'][0]['digest']
        with patch('observations.folder_import.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/images/folder/',{'action':'apply','token':token,'selected':['1','0'],'species_0':self.species.pk,'species_1':self.species.pk,'confirm':'yes'},follow=True)
        self.assertEqual(Sample.objects.count(),1)
        item=Sample.objects.get()
        self.assertEqual(hashlib.sha256(Path(item.image.path).read_bytes()).hexdigest(),first_digest)
        self.assertContains(response,'דולגו 1 תמונות כפולות')
    def test_large_folder_and_confirmation_fit_request_limits(self):
        from django.conf import settings
        from django.test import RequestFactory
        self.assertGreaterEqual(settings.DATA_UPLOAD_MAX_NUMBER_FILES,500)
        request=RequestFactory().post('/admin/images/folder/',{'images':[self.photo() for _ in range(500)]})
        self.assertEqual(len(request.FILES.getlist('images')),500)
        data={'action':'apply','token':'test','confirm':'yes','selected':[str(i) for i in range(500)]}
        data.update({f'species_{i}':str(self.species.pk) for i in range(500)})
        request=RequestFactory().post('/admin/images/folder/',data)
        self.assertEqual(len(request.POST.getlist('selected')),500)
    def test_create_missing_species_once_only_after_confirmation(self):
        self.client.force_login(self.user)
        photo=self.photo();photo.name='205-Thecacera picta-Baba, 1972.jpeg'
        second=self.photo();second.name='205-Thecacera picta 2025.jpg'
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':[photo,second]})
        self.assertEqual(response.context['rows'][0]['proposed'],'Thecacera picta')
        self.assertFalse(Species.objects.filter(scientific_name='Thecacera picta').exists())
        with patch('observations.folder_import.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/images/folder/',{'action':'apply','token':response.context['token'],'selected':['0','1'],'species_0':'new','species_1':'new','new_name_0':'Thecacera picta','new_name_1':'Thecacera picta','confirm':'yes'},follow=True)
        species=Species.objects.get(scientific_name='Thecacera picta')
        self.assertEqual(species.genus,'Thecacera');self.assertEqual(species.species,'picta');self.assertEqual(species.phylogenetic_order,'205')
        self.assertEqual(Sample.objects.filter(species=species).count(),1)
        self.assertContains(response,'דולגו 1 תמונות כפולות')
