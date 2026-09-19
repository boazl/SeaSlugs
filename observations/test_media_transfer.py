import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Sample,Species,Country,Sea,Region,DiveTrip
from .table_transfer import plan,apply,fingerprint,export_table

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
    def test_image_manager_download_upload_and_cleanup(self):
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
    def test_image_manager_sort_alpha_and_taxonomy(self):
        # self.sample's species ("Test species") has no genus or phylogenetic_order set,
        # so it should sort after any species that does specify them.
        from .image_manager import files
        zebra=Species.objects.create(scientific_name='Zzz species',genus='Zebra',species='stripey',phylogenetic_order='50')
        aardvark=Species.objects.create(scientific_name='Aaa species',genus='Aardvark',species='snouty',phylogenetic_order='10')
        def add_sample(species,filename):
            output=io.BytesIO();Image.new('RGB',(60,40),'red').save(output,'JPEG')
            sample=Sample(owner=self.sample.owner,species=species,trip=self.sample.trip)
            sample.image.save(filename,ContentFile(output.getvalue()),save=False)
            sample.save_reviewed();return sample
        add_sample(zebra,'z.jpg');add_sample(aardvark,'a.jpg')

        def names(sort):
            return [row['refs'][0].species.scientific_name for row in files(sort)]

        self.assertEqual(names('alpha'),['Aaa species','Test species','Zzz species'])
        self.assertEqual(names('taxonomy'),['Aaa species','Zzz species','Test species'])
        # file order (the default) is unaffected -- unrelated to species entirely
        self.assertEqual(set(names('file')),{'Aaa species','Test species','Zzz species'})

    def test_image_manager_sort_view_and_redirect(self):
        self.client.force_login(self.sample.owner)
        content=self.client.get('/admin/images/',{'sort':'alpha'}).content.decode()
        self.assertIn('<strong>לפי סדר אלפביתי (סוג ומין)</strong>',content)
        self.assertIn('href="?sort=taxonomy"',content)
        # an invalid value falls back to the default rather than erroring
        content=self.client.get('/admin/images/',{'sort':'bogus'}).content.decode()
        self.assertIn('<strong>לפי שם קובץ</strong>',content)
        # the chosen sort survives an action's redirect back to the page
        from .image_manager import files
        row=files()[0]
        self.sample.video_url='https://youtu.be/abcdefghijk';self.sample.save()
        response=self.client.post('/admin/images/?sort=alpha',{'action':'delete','confirm':'yes','selected':[row['token']]})
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,'/admin/images/?sort=alpha')

    def test_image_manager_lists_using_observations_with_region_and_status(self):
        # Each image card must show which observation(s) actually use it -- with enough
        # detail (region, and a status flag when it isn't a normal published sample) to
        # tell otherwise-identical entries apart.
        self.client.force_login(self.sample.owner)
        content=self.client.get('/admin/images/').content.decode()
        self.assertIn('<ul>',content);self.assertIn(f'/observations/{self.sample.pk}/edit/',content)
        self.assertIn('Eilat',content)  # the region name, from self.sample.trip
        self.assertNotIn('ממתינה לאישור',content)  # self.sample is published -- no status suffix

        self.sample.status='pending';self.sample.save()
        content=self.client.get('/admin/images/').content.decode()
        self.assertIn('ממתינה לאישור',content)

        self.sample.soft_delete(self.sample.owner)
        content=self.client.get('/admin/images/').content.decode()
        self.assertIn('תצפית מחוקה',content);self.assertNotIn('ממתינה לאישור',content)  # deleted wins over status

    def test_image_manager_authorization(self):
        self.assertEqual(self.client.get('/admin/images/').status_code,302)
        self.client.force_login(User.objects.create_user('staff',is_staff=True))
        self.assertEqual(self.client.get('/admin/images/').status_code,403)
    def test_json_export_and_update_preserves_destination_image(self):
        import json
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
        import uuid
        doc=export_table('samples');doc['media_mode']='separate'
        missing=dict(doc['rows'][0],transfer_id=str(uuid.uuid4()),title='Missing image')
        doc['rows'][0]['title']='Changed';doc['rows'].append(missing)
        items=plan(doc);self.assertEqual([i['action'] for i in items],['update','skipped'])
        with patch('observations.table_transfer.create_backup',return_value=Path('backup.sqlite3')):apply(doc,fingerprint())
        self.sample.refresh_from_db();self.assertEqual(self.sample.title,'Changed');self.assertEqual(Sample.objects.count(),1)
    def test_edit_view_stores_uploaded_image_by_content_hash(self):
        # The live per-observation upload must name files exactly like the bulk
        # folder importer and the image manager do (SHA256 of the content), so
        # the same photo resolves to the same reference regardless of which of
        # the two upload mechanisms created it, or in which environment.
        output=io.BytesIO();Image.new('RGB',(80,60),'green').save(output,'JPEG');raw=output.getvalue()
        species2=Species.objects.create(scientific_name='Second species')
        species3=Species.objects.create(scientific_name='Third species')
        self.client.force_login(self.sample.owner)
        base={'kind':'species','species_other':'','site':'','site_other':'','day':'','depth':'','video_url':'','title':''}
        response=self.client.post('/observations/new/',dict(base,species=species2.scientific_name,trip=self.sample.trip.pk,
            image=SimpleUploadedFile('photo.jpg',raw,content_type='image/jpeg')))
        self.assertEqual(response.status_code,302)
        created=Sample.objects.get(species=species2)
        self.assertRegex(created.image.name,r'^observations/transfer/[0-9a-f]{64}\.jpg$')
        # Uploading the exact same bytes again, for a different sample, must reuse
        # the same stored file rather than create a second copy.
        response=self.client.post('/observations/new/',dict(base,species=species3.scientific_name,trip=self.sample.trip.pk,
            image=SimpleUploadedFile('photo-again.jpg',raw,content_type='image/jpeg')))
        self.assertEqual(response.status_code,302)
        other=Sample.objects.get(species=species3)
        self.assertEqual(other.image.name,created.image.name)
