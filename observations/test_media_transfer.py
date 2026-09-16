import io
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from .models import Sample,Species,Country,Sea,Region,DiveTrip
from .media_transfer import export_bundle,read_bundle
from .table_transfer import plan,apply,fingerprint

class MediaTransferTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.settings_override=override_settings(MEDIA_ROOT=self.temp.name,DATA_DIR=self.temp.name)
        self.settings_override.enable();self.addCleanup(self.settings_override.disable)
        user=User.objects.create_superuser('admin',password='testing')
        country=Country.objects.create(name='Israel');sea=Sea.objects.create(name='Red Sea')
        region=Region.objects.create(name='Eilat',country=country,sea=sea)
        trip=DiveTrip.objects.create(title='Eilat trip',year=2026,country=country,region=region)
        species=Species.objects.create(scientific_name='Test species')
        self.sample=Sample(owner=user,species=species,trip=trip)
        output=io.BytesIO();Image.new('RGB',(100,80),'blue').save(output,'JPEG')
        self.sample.image.save('original.jpg',ContentFile(output.getvalue()),save=False)
        self.sample.save_reviewed()
    def test_photo_only_update_repeat_and_old_file_retained(self):
        old=self.sample.image.path
        doc,images=read_bundle(export_bundle());doc['rows'][0]['title']='Updated photo'
        self.assertEqual(plan(doc)[0]['action'],'update')
        with patch('observations.table_transfer.create_backup',return_value=Path('backup.sqlite3')):
            apply(doc,fingerprint(),images=images)
        self.sample.refresh_from_db();self.assertEqual(self.sample.title,'Updated photo')
        self.assertTrue(Path(old).exists());self.assertTrue(Path(self.sample.image.path).exists())
        self.assertEqual(plan(doc)[0]['action'],'same');self.assertEqual(Sample.objects.count(),1)
    def test_new_target_and_missing_media(self):
        doc,images=read_bundle(export_bundle());self.sample.delete()
        self.assertEqual(plan(doc)[0]['action'],'new')
        with patch('observations.table_transfer.create_backup',return_value=Path('backup.sqlite3')):
            apply(doc,fingerprint(),images=images)
        self.assertEqual(Sample.objects.count(),1)
    def test_unsafe_zip_and_stale_preview(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('table.json','{"table":"samples","rows":[]}')
            archive.writestr('../escape.jpg',b'bad')
        with self.assertRaises(ValidationError):read_bundle(output.getvalue())
        doc,images=read_bundle(export_bundle());before=fingerprint()
        self.sample.title='Changed';self.sample.save()
        with patch('observations.table_transfer.create_backup',return_value=Path('backup.sqlite3')):
            with self.assertRaises(ValidationError):apply(doc,before,images=images)
    def test_view_preview_and_confirm(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.sample.owner)
        response=self.client.post('/admin/table-transfer/',{'action':'preview','file':SimpleUploadedFile('samples.zip',export_bundle())})
        self.assertEqual(response.status_code,200);self.assertIn('token',response.context)
        with patch('observations.table_transfer.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/table-transfer/',{'action':'apply','confirm':'yes','token':response.context['token']})
        self.assertEqual(response.status_code,302)
    def test_image_manager_download_upload_and_cleanup(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .image_manager import files
        self.client.force_login(self.sample.owner)
        old=Path(self.sample.image.path);row=files()[0]
        response=self.client.get('/admin/images/file/',{'file':row['token'],'download':'1'})
        raw=b''.join(response.streaming_content);response.close()
        response=self.client.post('/admin/images/',{'action':'upload','replace':'yes','images':SimpleUploadedFile('transfer.jpg',raw,content_type='image/jpeg')})
        self.assertEqual(response.status_code,302)
        self.sample.refresh_from_db();self.assertFalse(old.exists());self.assertTrue(Path(self.sample.image.path).exists())
        self.assertEqual(Sample.objects.count(),1)
    def test_image_manager_blocks_last_media_and_deletes_unused(self):
        from .image_manager import files
        self.client.force_login(self.sample.owner);row=files()[0]
        response=self.client.post('/admin/images/',{'action':'delete','confirm':'yes','selected':[row['token']]})
        self.assertContains(response,'המדיה היחידה');self.assertTrue(Path(self.sample.image.path).exists())
        self.sample.video_url='https://youtu.be/abcdefghijk';self.sample.save()
        response=self.client.post('/admin/images/',{'action':'delete','confirm':'yes','selected':[row['token']]})
        self.assertEqual(response.status_code,302);self.sample.refresh_from_db();self.assertFalse(self.sample.image)
        self.assertEqual(files(),[])
    def test_image_manager_authorization(self):
        self.assertEqual(self.client.get('/admin/images/').status_code,302)
        self.client.force_login(User.objects.create_user('staff',is_staff=True))
        self.assertEqual(self.client.get('/admin/images/').status_code,403)
    def test_json_export_and_update_preserves_destination_image(self):
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.sample.owner)
        response=self.client.post('/admin/table-transfer/',{'action':'export','table':'samples'})
        self.assertEqual(response['Content-Type'],'application/json; charset=utf-8')
        doc=json.loads(response.content);doc['rows'][0]['title']='Table update'
        doc['rows'][0]['image']='different/source/file.jpg'
        original=self.sample.image.name
        response=self.client.post('/admin/table-transfer/',{'action':'preview','file':SimpleUploadedFile('table.json',json.dumps(doc).encode())})
        self.assertIn('token',response.context)
        with patch('observations.table_transfer.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/table-transfer/',{'action':'apply','confirm':'yes','token':response.context['token']})
        self.assertEqual(response.status_code,302)
        self.sample.refresh_from_db();self.assertEqual(self.sample.title,'Table update');self.assertEqual(self.sample.image.name,original)
        self.assertTrue(Path(self.sample.image.path).exists())
    def test_missing_photo_skips_only_that_row(self):
        from .table_transfer import export_table
        import uuid
        doc=export_table('samples');doc['media_mode']='separate'
        missing=dict(doc['rows'][0],transfer_id=str(uuid.uuid4()),title='Missing image')
        doc['rows'][0]['title']='Changed';doc['rows'].append(missing)
        items=plan(doc);self.assertEqual([i['action'] for i in items],['update','skipped'])
        with patch('observations.table_transfer.create_backup',return_value=Path('backup.sqlite3')):apply(doc,fingerprint())
        self.sample.refresh_from_db();self.assertEqual(self.sample.title,'Changed');self.assertEqual(Sample.objects.count(),1)
