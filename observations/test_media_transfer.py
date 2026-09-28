import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
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
        def add_sample(species,filename,color):
            # A distinct color per call -- Sample.clean() now blocks two active samples
            # from sharing the exact same image, and two identically-sized same-color
            # JPEGs hash identically.
            output=io.BytesIO();Image.new('RGB',(60,40),color).save(output,'JPEG')
            sample=Sample(owner=self.sample.owner,species=species,trip=self.sample.trip)
            sample.image.save(filename,ContentFile(output.getvalue()),save=False)
            sample.save_reviewed();return sample
        add_sample(zebra,'z.jpg','red');add_sample(aardvark,'a.jpg','green')

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
    def test_image_manager_upload_accepts_published_genus_kind_with_species_other(self):
        # Regression test: sample_plan() used to reject every published GENUS-kind sample
        # during transfer, because species_other holds the genus name itself -- the sample's
        # actual, permanent identification, not a placeholder "other" value awaiting a species
        # match -- and the 'אין לפרסם רשומה עם ערכי אחר' check didn't carve out the same GENUS
        # exception that Sample.publication_reasons()/save_reviewed() already do.
        from .image_manager import files
        genus_sample=Sample(owner=self.sample.owner,kind=Sample.Kind.GENUS,species_other='Chelidonura',trip=self.sample.trip)
        output=io.BytesIO();Image.new('RGB',(60,40),'yellow').save(output,'JPEG')
        genus_sample.image.save('genus.jpg',ContentFile(output.getvalue()),save=False)
        genus_sample.save_reviewed(actor=genus_sample.owner,approve=True)
        self.assertEqual(genus_sample.status,'published')
        self.client.force_login(genus_sample.owner)
        row=next(r for r in files() if genus_sample in r['refs'])
        response=self.client.get('/admin/images/file/',{'file':row['token'],'download':'1'})
        raw=b''.join(response.streaming_content);response.close()
        response=self.client.post('/admin/images/',{'action':'upload','replace':'yes','images':SimpleUploadedFile('transfer.jpg',raw,content_type='image/jpeg')})
        self.assertEqual(response.status_code,302)
        genus_sample.refresh_from_db()
        self.assertEqual(genus_sample.status,'published');self.assertEqual(genus_sample.species_other,'Chelidonura')

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
    def test_sample_transfer_names_the_missing_species_instead_of_a_generic_message(self):
        # A samples-table row referencing a species that doesn't exist in this environment's
        # species table (e.g. transferred in from an environment where it does) must say so
        # by name -- not a generic "missing reference value" -- so whoever is importing knows
        # exactly what to add to the species table (or fix) before importing again.
        from .table_transfer import plan
        doc=export_table('samples');doc['media_mode']='separate';doc['rows'][0]['species']='Nonexistent species'
        with self.assertRaises(ValidationError) as ctx:
            plan(doc)
        self.assertIn('Nonexistent species',str(ctx.exception))
        self.assertIn('אינו קיים בטבלת המינים',str(ctx.exception))
    def test_table_transfer_preview_reports_the_missing_species_by_name(self):
        # Same check, exercised through the actual file-upload endpoint (a samples-table
        # JSON file), rather than calling plan() directly -- the preview step must surface
        # the same specific message, and never reach an apply that could import the row.
        import json
        self.client.force_login(self.sample.owner)
        response=self.client.post('/admin/table-transfer/',{'action':'export','table':'samples'})
        doc=json.loads(response.content);doc['rows'][0]['species']='Nonexistent species'
        response=self.client.post('/admin/table-transfer/',{'action':'preview','file':SimpleUploadedFile('table.json',json.dumps(doc).encode())})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Nonexistent species')
        self.assertContains(response,'אינו קיים בטבלת המינים')
        self.assertNotIn('token',response.context)
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
        # Regression: uploading the exact same bytes again, for a different sample, used to
        # silently reuse the same stored file -- now Sample.clean() blocks it outright (the
        # same photo may not be entered twice, full stop), so no second sample is created.
        response=self.client.post('/observations/new/',dict(base,species=species3.scientific_name,trip=self.sample.trip.pk,
            image=SimpleUploadedFile('photo-again.jpg',raw,content_type='image/jpeg')))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'התמונה הזו כבר קיימת בתצפית אחרת')
        self.assertFalse(Sample.objects.filter(species=species3).exists())


class DuplicateSpeciesInTripTests(TestCase):
    """A new observation for a species already observed on the same trip must not create a
    second row for it: views.edit folds it into the existing observation instead, updating
    whichever of image/video the new submission actually supplies (see views.edit and
    Sample.clean())."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.settings_override=override_settings(MEDIA_ROOT=self.temp.name,DATA_DIR=self.temp.name)
        self.settings_override.enable();self.addCleanup(self.settings_override.disable)
        self.owner=User.objects.create_superuser('admin2',password='testing')
        country=Country.objects.create(name='Israel');sea=Sea.objects.create(name='Red Sea')
        region=Region.objects.create(name='Eilat',country=country,sea=sea)
        self.trip=DiveTrip.objects.create(title='Eilat trip',year=2026,country=country,region=region)
        self.species=Species.objects.create(scientific_name='Test species')
        self.existing=Sample(owner=self.owner,species=self.species,trip=self.trip)
        output=io.BytesIO();Image.new('RGB',(100,80),'blue').save(output,'JPEG')
        self.existing.image.save('original.jpg',ContentFile(output.getvalue()),save=False)
        self.existing.save_reviewed()
        self.client.force_login(self.owner)
        self.base={'kind':'species','species_other':'','site':'','site_other':'','day':'','depth':'','video_url':'','title':''}

    def test_new_observation_of_same_species_and_trip_updates_the_existing_image_instead_of_duplicating(self):
        original_name=self.existing.image.name
        output=io.BytesIO();Image.new('RGB',(90,70),'red').save(output,'JPEG');raw=output.getvalue()
        response=self.client.post('/observations/new/',dict(self.base,species=self.species.scientific_name,trip=self.trip.pk,
            image=SimpleUploadedFile('new.jpg',raw,content_type='image/jpeg')))
        self.assertEqual(response.status_code,302)
        self.assertEqual(Sample.objects.filter(species=self.species,trip=self.trip).count(),1)
        self.existing.refresh_from_db()
        # The uploaded image is re-encoded by SampleForm.clean_image (resized/re-saved as
        # JPEG) before it's hashed, so its stored name won't match a hash of the raw upload
        # bytes -- just confirm it's a real, freshly content-hashed file, distinct from the
        # sample's original image.
        self.assertRegex(self.existing.image.name,r'^observations/transfer/[0-9a-f]{64}\.jpg$')
        self.assertNotEqual(self.existing.image.name,original_name)

    def test_new_observation_of_same_species_and_trip_updates_the_existing_video_instead_of_duplicating(self):
        response=self.client.post('/observations/new/',dict(self.base,species=self.species.scientific_name,trip=self.trip.pk,
            video_url='https://youtu.be/22222222222'))
        self.assertEqual(response.status_code,302)
        self.assertEqual(Sample.objects.filter(species=self.species,trip=self.trip).count(),1)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.video_url,'https://youtu.be/22222222222')

    def test_same_species_on_a_different_trip_is_not_merged(self):
        other_trip=DiveTrip.objects.create(title='Other trip',year=2026,country=self.trip.country,region=self.trip.region)
        response=self.client.post('/observations/new/',dict(self.base,species=self.species.scientific_name,trip=other_trip.pk,
            video_url='https://youtu.be/33333333333'))
        self.assertEqual(response.status_code,302)
        self.assertEqual(Sample.objects.filter(species=self.species).count(),2)

    def test_editing_a_different_sample_into_a_collision_is_rejected_not_merged(self):
        other_species=Species.objects.create(scientific_name='Other species')
        other=Sample(owner=self.owner,species=other_species,trip=self.trip)
        output=io.BytesIO();Image.new('RGB',(60,40),'green').save(output,'JPEG')
        other.image.save('other.jpg',ContentFile(output.getvalue()),save=False)
        other.save_reviewed()
        response=self.client.post(f'/observations/{other.pk}/edit/',dict(self.base,species=self.species.scientific_name,trip=self.trip.pk,
            video_url='https://youtu.be/44444444444'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'כבר נקלט למסע זה')
        other.refresh_from_db();self.existing.refresh_from_db()
        self.assertEqual(other.species_id,other_species.pk)
        self.assertNotEqual(self.existing.video_url,'https://youtu.be/44444444444')
