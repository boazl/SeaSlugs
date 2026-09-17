import hashlib
import io
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from . import maintenance
from .db_replace import cleanup_orphaned_images, pending_path


def build_fixture(path, images=()):
    from django.db.migrations.loader import MigrationLoader
    migrations = list(MigrationLoader(None, ignore_no_migrations=True).disk_migrations.keys())
    conn = sqlite3.connect(str(path))
    try:
        conn.execute('CREATE TABLE django_migrations (id INTEGER PRIMARY KEY, app TEXT, name TEXT)')
        conn.executemany('INSERT INTO django_migrations (app,name) VALUES (?,?)', migrations)
        conn.execute('CREATE TABLE observations_species (id INTEGER PRIMARY KEY, scientific_name TEXT)')
        conn.execute('CREATE TABLE dive_trips (id INTEGER PRIMARY KEY, title TEXT, year INTEGER)')
        conn.execute('CREATE TABLE samples (id INTEGER PRIMARY KEY, image TEXT, deleted_at TEXT, species_id INTEGER, species_other TEXT, trip_id INTEGER)')
        for i, name in enumerate(images):
            conn.execute('INSERT INTO samples (id,image,deleted_at) VALUES (?,?,NULL)', (i, name))
        conn.commit()
    finally:
        conn.close()


class DbReplaceTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.override = override_settings(DATA_DIR=self.temp.name, MEDIA_ROOT=self.temp.name + '/media')
        self.override.enable(); self.addCleanup(self.override.disable)
        self.addCleanup(maintenance.unlock)
        self.user = User.objects.create_superuser('admin', password='testing')

    def test_middleware_blocks_anonymous_only_while_locked(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        maintenance.lock()
        response = self.client.get('/')
        self.assertEqual(response.status_code, 503)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_healthz_is_never_blocked_by_maintenance_mode(self):
        # Render's health check hits /healthz with no auth; if that 503s while the
        # site is locked, Render concludes the instance itself crashed and restarts
        # it -- a real incident this caused once already. Must stay 200 regardless.
        self.assertEqual(self.client.get('/healthz').status_code, 200)
        maintenance.lock()
        self.assertEqual(self.client.get('/healthz').status_code, 200)

    def test_lock_requires_confirm_and_creates_backup(self):
        self.client.force_login(self.user)
        with patch('observations.db_replace.create_backup') as backup:
            self.client.post('/admin/db-replace/', {'action': 'lock'})
            self.assertFalse(maintenance.is_locked())
            response = self.client.post('/admin/db-replace/', {'action': 'lock', 'confirm': 'yes'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(maintenance.is_locked())
        backup.assert_called_once()

    def test_unlock_clears_flag_and_pending_file(self):
        maintenance.lock()
        pending_path().write_bytes(b'x')
        self.client.force_login(self.user)
        response = self.client.post('/admin/db-replace/', {'action': 'unlock'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(maintenance.is_locked())
        self.assertFalse(pending_path().exists())

    def test_unlock_button_appears_on_admin_index_and_admin_tool_pages_only_when_locked(self):
        # / is served from a standalone dist/index.html, not base.html, so this checks
        # the admin index and an ordinary base.html-based admin tool page instead.
        self.client.force_login(self.user)
        response = self.client.get('/admin/')
        self.assertNotContains(response, 'ביטול נעילה')
        response = self.client.get('/admin/releases/')
        self.assertNotContains(response, 'ביטול נעילה')
        maintenance.lock()
        response = self.client.get('/admin/')
        self.assertContains(response, 'ביטול נעילה')
        response = self.client.get('/admin/releases/')
        self.assertContains(response, 'ביטול נעילה')
        response = self.client.post('/admin/db-replace/', {'action': 'unlock'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(maintenance.is_locked())

    def test_preview_rejected_when_not_locked(self):
        self.client.force_login(self.user)
        response = self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', b'x')})
        self.assertContains(response, 'לנעול')

    def test_preview_rejects_non_sqlite_file(self):
        maintenance.lock(); self.client.force_login(self.user)
        response = self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', b'not sqlite')})
        self.assertContains(response, 'אינו קובץ SQLite')

    def test_preview_rejects_migration_mismatch(self):
        maintenance.lock(); self.client.force_login(self.user)
        path = Path(self.temp.name) / 'bad.sqlite3'
        build_fixture(path, images=[])
        conn = sqlite3.connect(str(path))
        conn.execute('DELETE FROM django_migrations WHERE rowid = (SELECT rowid FROM django_migrations LIMIT 1)')
        conn.commit(); conn.close()
        response = self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        self.assertContains(response, 'אינה תואמת לקוד')
        self.assertFalse(pending_path().exists())

    def test_preview_accepts_valid_file_and_reports_missing_images(self):
        maintenance.lock(); self.client.force_login(self.user)
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=['observations/transfer/' + 'a' * 64 + '.jpg'])
        response = self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(pending_path().exists())
        response = self.client.get('/admin/db-replace/')
        self.assertEqual(response.context['needed_count'], 1)
        self.assertEqual(response.context['missing_count'], 1)

    def test_preview_missing_images_are_labeled_by_species_and_trip(self):
        # A missing image is just a content hash -- meaningless to a human -- so the
        # page must show which sample it belongs to instead of only a bare count.
        maintenance.lock(); self.client.force_login(self.user)
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=[])
        conn = sqlite3.connect(str(path))
        conn.execute("INSERT INTO observations_species (id, scientific_name) VALUES (1, 'Chromodoris annulata')")
        conn.execute("INSERT INTO dive_trips (id, title, year) VALUES (1, 'Anilao', 2025)")
        conn.execute(
            "INSERT INTO samples (id, image, deleted_at, species_id, trip_id) VALUES (1, ?, NULL, 1, 1)",
            ('observations/transfer/' + 'b' * 64 + '.jpg',),
        )
        conn.commit(); conn.close()
        self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        response = self.client.get('/admin/db-replace/')
        self.assertContains(response, 'Chromodoris annulata')
        self.assertContains(response, 'Anilao')

    def test_upload_images_accepts_a_hash_named_target_with_matching_content(self):
        maintenance.lock(); self.client.force_login(self.user)
        output = io.BytesIO(); Image.new('RGB', (10, 8), 'red').save(output, 'JPEG'); raw = output.getvalue()
        name = 'observations/transfer/' + hashlib.sha256(raw).hexdigest() + '.jpg'
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=[name, 'observations/transfer/' + 'b' * 64 + '.jpg'])
        self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        response = self.client.post('/admin/db-replace/', {
            'action': 'upload_images', 'target': name,
            'image': SimpleUploadedFile('x.jpg', raw, content_type='image/jpeg'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(default_storage.exists(name))
        response = self.client.get('/admin/db-replace/')
        self.assertEqual(response.context['missing_count'], 1)

    def test_upload_images_with_target_saves_legacy_non_hash_names(self):
        # Samples whose image predates content-hash naming keep names like
        # observations/<uuid>.jpg -- there's no hash in that name to verify a re-upload
        # against automatically, so those are uploaded one at a time through their own
        # dedicated button, which declares exactly which missing name it's filling.
        maintenance.lock(); self.client.force_login(self.user)
        output = io.BytesIO(); Image.new('RGB', (10, 8), 'green').save(output, 'JPEG'); raw = output.getvalue()
        legacy_name = 'observations/6c239d15efe44d16a6a9cbe889123a53.jpg'
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=[legacy_name])
        self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        response = self.client.get('/admin/db-replace/')
        self.assertTrue(response.context['missing_list'][0]['legacy'])
        response = self.client.post('/admin/db-replace/', {
            'action': 'upload_images', 'target': legacy_name,
            'image': SimpleUploadedFile('whatever-name.jpg', raw, content_type='image/jpeg'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(default_storage.exists(legacy_name))
        response = self.client.get('/admin/db-replace/')
        self.assertEqual(response.context['missing_count'], 0)

    def test_upload_images_with_target_rejects_content_mismatch_for_hash_names(self):
        # A hash-style target still gets its integrity guarantee: uploading the wrong
        # file through the per-image button must not be accepted just because the admin
        # declared that target explicitly.
        maintenance.lock(); self.client.force_login(self.user)
        output = io.BytesIO(); Image.new('RGB', (10, 8), 'blue').save(output, 'JPEG'); wrong_raw = output.getvalue()
        hash_name = 'observations/transfer/' + 'c' * 64 + '.jpg'
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=[hash_name])
        self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        response = self.client.post('/admin/db-replace/', {
            'action': 'upload_images', 'target': hash_name,
            'image': SimpleUploadedFile('x.jpg', wrong_raw, content_type='image/jpeg'),
        })
        self.assertContains(response, 'אינו תואם')
        self.assertFalse(default_storage.exists(hash_name))

    def test_upload_images_with_target_rejects_a_no_longer_needed_name(self):
        maintenance.lock(); self.client.force_login(self.user)
        output = io.BytesIO(); Image.new('RGB', (10, 8), 'green').save(output, 'JPEG'); raw = output.getvalue()
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=[])
        self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        response = self.client.post('/admin/db-replace/', {
            'action': 'upload_images', 'target': 'observations/nonexistent.jpg',
            'image': SimpleUploadedFile('x.jpg', raw, content_type='image/jpeg'),
        })
        self.assertContains(response, 'כבר אינה נדרשת')

    def test_commit_blocked_while_images_missing(self):
        maintenance.lock(); self.client.force_login(self.user)
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=['observations/transfer/' + 'a' * 64 + '.jpg'])
        self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        response = self.client.post('/admin/db-replace/', {'action': 'commit', 'confirm': 'yes'})
        self.assertContains(response, 'חסרות')
        self.assertTrue(maintenance.is_locked())

    def test_commit_swaps_and_unlocks_and_cleans_up(self):
        maintenance.lock(); self.client.force_login(self.user)
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=[])
        self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        with patch('observations.db_replace.create_backup'), \
             patch('observations.db_replace.replace_live_database') as swap, \
             patch('observations.db_replace.cleanup_orphaned_images', return_value=3) as cleanup:
            response = self.client.post('/admin/db-replace/', {'action': 'commit', 'confirm': 'yes', 'cleanup': 'yes'})
        self.assertEqual(response.status_code, 302)
        swap.assert_called_once()
        cleanup.assert_called_once()
        self.assertFalse(maintenance.is_locked())

    def test_commit_without_cleanup_flag_does_not_delete_images(self):
        maintenance.lock(); self.client.force_login(self.user)
        path = Path(self.temp.name) / 'good.sqlite3'
        build_fixture(path, images=[])
        self.client.post('/admin/db-replace/', {'action': 'preview', 'database': SimpleUploadedFile('db.sqlite3', path.read_bytes())})
        with patch('observations.db_replace.create_backup'), \
             patch('observations.db_replace.replace_live_database'), \
             patch('observations.db_replace.cleanup_orphaned_images') as cleanup:
            self.client.post('/admin/db-replace/', {'action': 'commit', 'confirm': 'yes'})
        cleanup.assert_not_called()

    def test_download_requires_lock(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/admin/db-replace/download/').status_code, 403)
        maintenance.lock()
        backup_path = Path(self.temp.name) / 'x.sqlite3'
        backup_path.write_bytes(b'data')
        with patch('observations.db_replace.create_backup', return_value=backup_path):
            response = self.client.get('/admin/db-replace/download/')
        self.assertEqual(response.status_code, 200)

    def test_cleanup_orphaned_images_keeps_referenced_and_site_image(self):
        from .models import Sample, SiteImage, Species, Country, Sea, Region, DiveTrip
        country = Country.objects.create(name='Israel'); sea = Sea.objects.create(name='Red Sea')
        region = Region.objects.create(name='Eilat', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name='Test species')
        sample = Sample(owner=self.user, species=species, trip=trip)
        output = io.BytesIO(); Image.new('RGB', (10, 8), 'blue').save(output, 'JPEG')
        sample.image.save('kept.jpg', ContentFile(output.getvalue()), save=False)
        sample.save_reviewed()
        site = SiteImage.objects.create(key='intro_photo')
        site.image.save('home.jpg', ContentFile(output.getvalue()), save=True)
        default_storage.save('observations/transfer/orphan.jpg', ContentFile(b'orphan bytes'))
        removed = cleanup_orphaned_images()
        self.assertEqual(removed, 1)
        self.assertTrue(default_storage.exists(sample.image.name))
        self.assertTrue(default_storage.exists(site.image.name))
        self.assertFalse(default_storage.exists('observations/transfer/orphan.jpg'))


class ImageManagerSiteImageTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.temp.name, DATA_DIR=self.temp.name)
        self.override.enable(); self.addCleanup(self.override.disable)
        self.user = User.objects.create_superuser('admin2', password='testing')

    def test_site_image_is_never_listed_as_deletable_and_cannot_be_deleted(self):
        from .models import SiteImage
        from .image_manager import files
        output = io.BytesIO(); Image.new('RGB', (10, 8), 'blue').save(output, 'JPEG')
        site = SiteImage.objects.create(key='intro_photo')
        site.image.save('home.jpg', ContentFile(output.getvalue()), save=True)
        rows = files()
        row = next(r for r in rows if r['name'] == site.image.name)
        self.assertTrue(row['blocked'])
        self.client.force_login(self.user)
        response = self.client.post('/admin/images/', {'action': 'delete', 'confirm': 'yes', 'selected': [row['token']]})
        self.assertContains(response, 'תמונת הבית')
        self.assertTrue(Path(site.image.path).exists())
