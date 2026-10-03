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

    def test_files_flags_redundant_images(self):
        # redundant: every referencing Sample is soft-deleted, or there are no referencing
        # samples at all -- except a site image (the homepage photo), which is never
        # redundant even with zero Sample refs, since it's referenced from SiteImage, not
        # Sample.
        from .image_manager import files
        from .models import SiteImage
        sample_row=next(r for r in files() if r['refs'] and r['refs'][0].pk==self.sample.pk)
        self.assertFalse(sample_row['redundant'])
        orphan_path=Path(self.temp.name)/'orphan.jpg'
        Image.new('RGB',(10,10),'red').save(orphan_path,'JPEG')
        orphan_row=next(r for r in files() if r['name']=='orphan.jpg')
        self.assertTrue(orphan_row['redundant']);self.assertEqual(orphan_row['refs'],[])
        site_image=SiteImage(key='intro_photo')
        output=io.BytesIO();Image.new('RGB',(10,10),'blue').save(output,'JPEG')
        site_image.image.save('site.jpg',ContentFile(output.getvalue()),save=True)
        site_row=next(r for r in files() if r['name']==site_image.image.name)
        self.assertFalse(site_row['redundant'])
        self.sample.soft_delete(self.sample.owner)
        sample_row=next(r for r in files() if r['refs'] and r['refs'][0].pk==self.sample.pk)
        self.assertTrue(sample_row['redundant'])

    def test_export_manifest_action_returns_valid_json(self):
        # The export must be a small JSON listing each active, image-bearing sample's own
        # canonical filename (see Sample.canonical_image_name) -- not a hash of the stored
        # file's bytes, which differs between environments even for a successfully
        # transferred photo (the per-image transfer pipeline re-encodes on both legs), and
        # not an opaque id either: once every image is stored under the canonical scheme,
        # the plain filename itself is the stable, meaningful, cross-environment identity.
        import json
        self.client.force_login(self.sample.owner)
        response=self.client.post('/admin/images/',{'action':'export_manifest'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Content-Type'],'application/json; charset=utf-8')
        self.assertIn('attachment; filename="seaslugs-images-',response['Content-Disposition'])
        manifest=json.loads(response.content)
        self.assertEqual(manifest['format'],'seaslugs-image-manifest-v1')
        self.assertEqual(manifest['images'],[self.sample.image.name])

    def test_compare_manifest_action_reports_missing_and_only_here(self):
        # Diffing is by plain filename -- a name this environment doesn't have is "missing
        # here" (needs downloading from the other side); one only this environment has is
        # "only here" (informational, not an automatic deletion or transfer).
        import json
        self.client.force_login(self.sample.owner)
        other_manifest={'format':'seaslugs-image-manifest-v1','exported_at':'2026-01-01T00:00:00+00:00',
                        'images':['observations/elsewhere-species.jpg']}
        upload=SimpleUploadedFile('manifest.json',json.dumps(other_manifest).encode(),content_type='application/json')
        response=self.client.post('/admin/images/',{'action':'compare_manifest','manifest':upload})
        self.assertEqual(response.status_code,200)
        content=response.content.decode()
        self.assertIn('observations/elsewhere-species.jpg',content)
        self.assertIn(self.sample.image.name,content)  # self.sample's own image, reported as only-here

    def test_compare_manifest_treats_a_name_shared_by_both_sides_as_already_synced(self):
        # Regression: comparing by raw file content used to report a successfully
        # transferred photo as missing on both sides at once, because the transfer
        # pipeline re-encodes the image on both the download and the upload leg, so its
        # bytes never match across environments even once it's fully in sync. Comparing by
        # the canonical filename itself (stable across that round trip, since it's built
        # from the trip code + species/title identity rather than from the file's bytes)
        # must treat this as already synced -- it shows up in neither list.
        import json
        self.client.force_login(self.sample.owner)
        other_manifest={'format':'seaslugs-image-manifest-v1','exported_at':'2026-01-01T00:00:00+00:00',
                        'images':[self.sample.image.name]}
        upload=SimpleUploadedFile('manifest.json',json.dumps(other_manifest).encode(),content_type='application/json')
        response=self.client.post('/admin/images/',{'action':'compare_manifest','manifest':upload})
        self.assertEqual(response.status_code,200)
        content=response.content.decode()
        self.assertIn('אין תמונות חסרות כאן',content)
        self.assertIn('אין תמונות שקיימות רק כאן',content)

    def test_compare_manifest_rejects_malformed_file(self):
        self.client.force_login(self.sample.owner)
        upload=SimpleUploadedFile('manifest.json',b'{"format": "wrong"}',content_type='application/json')
        response=self.client.post('/admin/images/',{'action':'compare_manifest','manifest':upload})
        self.assertContains(response,'קובץ השוואה לא תקין')

    def test_compare_manifest_marks_only_here_images_with_a_selectable_data_name(self):
        # The comparison view's "only here" list is informational text, but every image
        # actually sitting in this environment's own gallery below also carries the same
        # plain filename as a data-name attribute on its checkbox, and the "only here"
        # section renders a button plus the name list as JSON -- together these let the
        # page's own script pre-check exactly those boxes (so the admin can select all of
        # them for download in one click) without the view needing a dedicated endpoint.
        import json
        self.client.force_login(self.sample.owner)
        other_manifest={'format':'seaslugs-image-manifest-v1','exported_at':'2026-01-01T00:00:00+00:00','images':[]}
        upload=SimpleUploadedFile('manifest.json',json.dumps(other_manifest).encode(),content_type='application/json')
        response=self.client.post('/admin/images/',{'action':'compare_manifest','manifest':upload})
        content_str=response.content.decode()
        self.assertIn('id="select-only-here"',content_str)
        self.assertIn('id="only-here-names"',content_str)
        self.assertIn(f'data-name="{self.sample.image.name}"',content_str)
        names=json.loads(content_str.split('id="only-here-names" type="application/json">',1)[1].split('</script>',1)[0])
        self.assertEqual(names,[self.sample.image.name])

    def test_compare_manifest_omits_the_select_button_when_nothing_is_only_here(self):
        import json
        self.client.force_login(self.sample.owner)
        other_manifest={'format':'seaslugs-image-manifest-v1','exported_at':'2026-01-01T00:00:00+00:00',
                        'images':[self.sample.image.name]}
        upload=SimpleUploadedFile('manifest.json',json.dumps(other_manifest).encode(),content_type='application/json')
        response=self.client.post('/admin/images/',{'action':'compare_manifest','manifest':upload})
        content_str=response.content.decode()
        self.assertNotIn('id="select-only-here"',content_str)
        self.assertNotIn('id="only-here-names"',content_str)

    def test_images_page_shows_redundant_badge_and_select_button(self):
        self.client.force_login(self.sample.owner)
        content=self.client.get('/admin/images/').content.decode()
        self.assertIn('select-redundant',content)
        self.assertNotIn('תמונה מיותרת —',content)  # self.sample's image is still referenced
        self.sample.soft_delete(self.sample.owner)
        content=self.client.get('/admin/images/').content.decode()
        self.assertIn('תמונה מיותרת —',content)
    def test_image_manager_upload_names_colliding_new_samples_with_a_batch_local_suffix(self):
        # Regression: two brand-new (never matched to anything locally) COLLECTION-kind
        # rows in one upload batch, sharing a trip and a gallery title, would both compute
        # the exact same canonical name (see Sample.canonical_image_name) -- a plain
        # database query can't see the other one's pending name yet (neither is saved), so
        # without extra_used_names they'd collide. Build a real sample just to get a
        # validly EXIF-embedded download, then re-stamp a copy of it with a fresh
        # transfer_id AND video_url (so sample_plan() can't match it back to anything that
        # already exists, by either identity) before re-uploading two such copies together.
        import json,uuid
        from .image_manager import files
        source=Sample(owner=self.sample.owner,trip=self.sample.trip,kind=Sample.Kind.COLLECTION,
            title='Night dive highlights',video_url='https://youtu.be/11111111111')
        output=io.BytesIO();Image.new('RGB',(60,40),'red').save(output,'JPEG')
        source.image.save('source.jpg',ContentFile(output.getvalue()),save=False);source.save_reviewed()
        self.client.force_login(self.sample.owner)
        def restamped_copy(video_id):
            row=next(r for r in files() if source in r['refs'])
            response=self.client.get('/admin/images/file/',{'file':row['token'],'download':'1'})
            raw=b''.join(response.streaming_content);response.close()
            with Image.open(io.BytesIO(raw)) as image:
                metadata=json.loads(image.getexif()[270][len('SeaSlugs:'):])
                metadata['transfer_id']=str(uuid.uuid4());metadata['video_url']=f'https://youtu.be/{video_id}'
                output=io.BytesIO();exif=Image.Exif();exif[270]='SeaSlugs:'+json.dumps(metadata,ensure_ascii=False)
                image.convert('RGB').save(output,'JPEG',exif=exif)
            return output.getvalue()
        upload_a=SimpleUploadedFile('a.jpg',restamped_copy('aaaaaaaaaaa'),content_type='image/jpeg')
        upload_b=SimpleUploadedFile('b.jpg',restamped_copy('bbbbbbbbbbb'),content_type='image/jpeg')
        response=self.client.post('/admin/images/',{'action':'upload','images':[upload_a,upload_b]})
        self.assertEqual(response.status_code,302,response.content)
        names=set(Sample.objects.filter(title='Night dive highlights').values_list('image',flat=True))
        self.assertEqual(len(names),3)  # source (its own non-canonical name) + the two new, canonical ones
        trip_code=self.sample.trip.code
        self.assertIn(f'observations/{trip_code}-night-dive-highlights.jpg',names)
        self.assertIn(f'observations/{trip_code}-night-dive-highlights-2.jpg',names)

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
    def test_deleted_target_with_no_live_replacement_skips_only_that_row(self):
        # When a video's only local representation is a deleted sample (no active
        # replacement exists for it), reviving it -- or silently creating a second,
        # competing sample for the same video -- is an admin judgment call the transfer
        # tool must not make on its own. That row is skipped, with a reason naming the
        # deleted record, but the rest of the file (here, self.sample's own row) still
        # transfers normally -- it must not block the whole table the way a hard error would.
        other_species = Species.objects.create(scientific_name='Other species 4')
        deleted = Sample(owner=self.sample.owner, species=other_species, trip=self.sample.trip,
                         title='Gone', video_url='https://youtu.be/dQw4w9WgXcQ')
        deleted.save_reviewed(actor=deleted.owner, approve=True)
        deleted_pk = deleted.pk
        deleted.soft_delete(deleted.owner)
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        # export_table excludes deleted samples -- reconstruct the row as if it had been
        # exported BEFORE deletion and is only now being re-imported (the realistic shape:
        # the source environment hasn't changed, the target deleted its own copy since).
        deleted_row = dict(doc['rows'][0], transfer_id=str(deleted.transfer_id), video_url=deleted.video_url,
                           title=deleted.title, species=other_species.scientific_name, image='')
        doc['rows'][0]['title'] = 'Updated title'  # self.sample's own row, unrelated
        doc['rows'].append(deleted_row)
        items = plan(doc)  # must not raise
        self.assertEqual(len(items), 2)
        updated = next(i for i in items if i['action'] == 'update')
        self.assertEqual(updated['object'].pk, self.sample.pk)
        skipped = next(i for i in items if i['action'] == 'skipped')
        self.assertIn(f'#{deleted_pk}', skipped['reason'])
        self.assertIn('מסומנת כמחוקה', skipped['reason'])
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        self.sample.refresh_from_db(); self.assertEqual(self.sample.title, 'Updated title')
        deleted.refresh_from_db(); self.assertIsNotNone(deleted.deleted_at)  # left untouched

    def test_missing_photo_skips_only_that_row(self):
        import uuid
        doc=export_table('samples');doc['media_mode']='separate'
        missing=dict(doc['rows'][0],transfer_id=str(uuid.uuid4()),title='Missing image')
        doc['rows'][0]['title']='Changed';doc['rows'].append(missing)
        items=plan(doc);self.assertEqual([i['action'] for i in items],['update','skipped'])
        with patch('observations.table_transfer.create_backup',return_value=Path('backup.sqlite3')):apply(doc,fingerprint())
        self.sample.refresh_from_db();self.assertEqual(self.sample.title,'Changed');self.assertEqual(Sample.objects.count(),1)
    def test_sample_transfer_ignores_a_deleted_sample_sharing_the_same_video(self):
        # Regression test: a soft-deleted sample and a later, active replacement can
        # legitimately share the same YouTube video (the photographer re-entered the
        # observation under a new Sample after the old one was deleted) -- but
        # sample_plan()'s video-URL fallback match didn't exclude deleted samples from
        # its "more than one candidate" check, so this ordinary, already-resolved
        # situation blocked transfer of the ENTIRE samples table the moment any one such
        # video came up, with "לסרטון כמה תצפיות ביעד" -- even though only the still-active sample
        # should ever be considered a match for an incoming row.
        import uuid
        video_url = 'https://youtu.be/dQw4w9WgXcQ'
        # A species distinct from self.sample's own, so this test's two samples are the
        # only ones for this species+trip (self.sample sharing that pair too would trip
        # the unrelated "same species already in this trip" guard once candidate.pk is set).
        other_species = Species.objects.create(scientific_name='Other species')
        deleted = Sample(owner=self.sample.owner, species=other_species, trip=self.sample.trip,
                          video_url=video_url)
        deleted.save_reviewed(actor=deleted.owner, approve=True)
        deleted.soft_delete(deleted.owner)
        active = Sample(owner=self.sample.owner, species=other_species, trip=self.sample.trip,
                         video_url=video_url)
        active.save_reviewed(actor=active.owner, approve=True)
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        row = next(r for r in doc['rows'] if r['video_url'] == video_url)
        # An incoming row for the same video from another environment, with a transfer_id
        # that matches nothing locally (as if this video had never been transferred before).
        row['transfer_id'] = str(uuid.uuid4())
        row['title'] = 'Updated from source'
        items = plan(doc)  # must not raise
        matching = [i for i in items if i['object'] and i['object'].video_url == video_url]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['object'].pk, active.pk)
        self.assertEqual(matching[0]['action'], 'update')

    def test_sample_transfer_resolves_to_the_live_sample_when_transfer_id_points_at_a_deleted_one(self):
        # Regression test: an observation gets transferred once (its transfer_id now matches
        # that same video in every environment), then later deleted locally and re-entered
        # under a brand-new Sample for the same video. The next transfer of that video still
        # carries the ORIGINAL transfer_id (unchanged in the source environment) -- which now
        # points, locally, at the deleted sample, while the video itself points at the live
        # replacement. This must resolve to the live replacement, not raise a conflict: the
        # deleted sample is history, not a competing match.
        other_species = Species.objects.create(scientific_name='Other species 3')
        video_url = 'https://youtu.be/dQw4w9WgXcQ'
        original = Sample(owner=self.sample.owner, species=other_species, trip=self.sample.trip,
                          title='Original', video_url=video_url)
        original.save_reviewed(actor=original.owner, approve=True)
        original_transfer_id = str(original.transfer_id)
        original.soft_delete(original.owner)
        replacement = Sample(owner=self.sample.owner, species=other_species, trip=self.sample.trip,
                             title='Replacement', video_url=video_url)
        replacement.save_reviewed(actor=replacement.owner, approve=True)
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        row = next(r for r in doc['rows'] if r['video_url'] == video_url)
        row['transfer_id'] = original_transfer_id  # as if re-exported from the source, unchanged
        row['title'] = 'Updated from source'
        items = plan(doc)  # must not raise
        matching = [i for i in items if i['object'] and i['object'].video_url == video_url]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['object'].pk, replacement.pk)
        self.assertEqual(matching[0]['action'], 'update')

    def test_sample_transfer_duplicate_video_error_names_the_conflicting_records(self):
        # A genuine duplicate (two ACTIVE samples sharing one video, an actual target-side
        # data problem the admin must fix) should still be rejected -- but the message must
        # name the video and each conflicting sample (pk, title/species, trip), not just say
        # generically that a conflict exists, so the admin knows exactly what to open and fix.
        other_species = Species.objects.create(scientific_name='Other species 2')
        video_url = 'https://youtu.be/dQw4w9WgXcQ'
        # Two ACTIVE samples sharing a video can't normally arise through the app itself --
        # Sample.clean() already blocks that -- but legacy data (a bulk import that bypassed
        # full_clean, or a pre-validation-era row) can still reach this state, and the
        # transfer tool must defend against it independently. Saving directly (bypassing
        # full_clean) constructs that same state on purpose, to exercise that defense.
        first = Sample(owner=self.sample.owner, species=other_species, trip=self.sample.trip,
                       title='First copy', video_url=video_url)
        first.save()
        second = Sample(owner=self.sample.owner, species=other_species, trip=self.sample.trip,
                        title='Second copy', video_url=video_url)
        second.save()
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        row = next(r for r in doc['rows'] if r['video_url'] == video_url)
        import uuid
        row['transfer_id'] = str(uuid.uuid4())
        with self.assertRaises(ValidationError) as ctx:
            plan(doc)
        message = str(ctx.exception)
        self.assertIn('dQw4w9WgXcQ', message)
        self.assertIn(f'#{first.pk}', message); self.assertIn('First copy', message)
        self.assertIn(f'#{second.pk}', message); self.assertIn('Second copy', message)

    def test_edit_view_stores_uploaded_image_by_canonical_name(self):
        # The live per-observation upload must name files by trip code + species (see
        # Sample.canonical_image_name) exactly like the bulk folder importer and the image
        # manager do, so the same observation resolves to the same, human-meaningful
        # filename regardless of which of those upload mechanisms created it, or in which
        # environment.
        output=io.BytesIO();Image.new('RGB',(80,60),'green').save(output,'JPEG');raw=output.getvalue()
        species2=Species.objects.create(scientific_name='Second species')
        species3=Species.objects.create(scientific_name='Third species')
        self.client.force_login(self.sample.owner)
        base={'kind':'species','species_other':'','site':'','site_other':'','day':'','depth':'','video_url':'','title':''}
        response=self.client.post('/observations/new/',dict(base,species=species2.scientific_name,trip=self.sample.trip.pk,
            image=SimpleUploadedFile('photo.jpg',raw,content_type='image/jpeg')))
        self.assertEqual(response.status_code,302)
        created=Sample.objects.get(species=species2)
        self.assertEqual(created.image.name,f'observations/{self.sample.trip.code}-second-species.jpg')
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
        # setUp saved self.existing's image directly as plain 'original.jpg', predating the
        # canonical naming scheme -- the new upload must still land under the CANONICAL name
        # for this trip+species (see Sample.canonical_image_name), not reuse that old name.
        expected_name=self.existing.canonical_image_name()
        output=io.BytesIO();Image.new('RGB',(90,70),'red').save(output,'JPEG');raw=output.getvalue()
        response=self.client.post('/observations/new/',dict(self.base,species=self.species.scientific_name,trip=self.trip.pk,
            image=SimpleUploadedFile('new.jpg',raw,content_type='image/jpeg')))
        self.assertEqual(response.status_code,302)
        self.assertEqual(Sample.objects.filter(species=self.species,trip=self.trip).count(),1)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.image.name,expected_name)
        with Image.open(self.existing.image.path) as stored:
            self.assertEqual(stored.size,(90,70))  # confirms the file content was actually replaced
        # Replacing the photo a SECOND time must keep landing on that same canonical name
        # (overwriting it), not collide with itself and get bumped to a "-2" suffix.
        output2=io.BytesIO();Image.new('RGB',(50,40),'blue').save(output2,'JPEG')
        response=self.client.post(f'/observations/{self.existing.pk}/edit/',dict(self.base,species=self.species.scientific_name,trip=self.trip.pk,
            image=SimpleUploadedFile('newer.jpg',output2.getvalue(),content_type='image/jpeg')))
        self.assertEqual(response.status_code,302)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.image.name,expected_name)
        with Image.open(self.existing.image.path) as stored:
            self.assertEqual(stored.size,(50,40))

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
