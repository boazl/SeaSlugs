import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Sample, Species, Country, Sea, Region, DiveTrip
from .table_transfer import export_table, plan, apply, fingerprint


class ReleaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('boaz', password='test-password')
        country = Country.objects.create(name='Israel')
        sea = Sea.objects.create(name='Red Sea')
        region = Region.objects.create(name='Eilat', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Eilat trip', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name='Test species')
        self.sample = Sample(owner=self.user, species=species, trip=trip, video_url='https://youtu.be/abcdefghijk')
        self.sample.save_reviewed()

    def test_transfer_idempotency_preview_and_update(self):
        doc = export_table('samples')
        self.assertEqual(plan(doc)[0]['action'], 'same')
        doc['rows'][0]['title'] = 'Changed title'
        self.assertEqual(plan(doc)[0]['action'], 'update')
        created = self.sample.created_at
        with patch('observations.table_transfer.create_backup', return_value=Path('backup.sqlite3')):
            apply(doc, fingerprint())
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.title, 'Changed title')
        self.assertEqual(self.sample.created_at, created)
        self.assertEqual(plan(doc)[0]['action'], 'same')

    def test_missing_user_and_deleted_target_block(self):
        doc = export_table('samples')
        doc['rows'][0]['owner'] = 'missing-user'
        with self.assertRaises(ValidationError): plan(doc)
        doc['rows'][0]['owner'] = self.user.username
        self.sample.soft_delete(self.user)
        with self.assertRaises(ValidationError): plan(doc)

    def test_incomplete_draft_can_transfer_but_not_publish(self):
        doc = export_table('samples')
        doc['rows'][0].update(trip=None, species=None, status='pending')
        self.assertEqual(plan(doc)[0]['action'], 'update')
        doc['rows'][0]['status'] = 'published'
        with self.assertRaises(ValidationError): plan(doc)

    def test_release_page_access_and_backup_contents(self):
        self.assertEqual(self.client.get('/admin/releases/').status_code, 302)
        member = User.objects.create_user('member', is_staff=True)
        self.client.force_login(member)
        self.assertEqual(self.client.get('/admin/releases/').status_code, 403)
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/admin/releases/'), 'Publish SeaSlugs.command')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); backup = root/'backup.sqlite3'; backup.write_bytes(b'test-db')
            media = root/'media'; media.mkdir(); (media/'picture.jpg').write_bytes(b'test-image')
            with override_settings(MEDIA_ROOT=media), patch('observations.release_views.create_backup',return_value=backup):
                response = self.client.post('/admin/releases/', {'action':'backup'})
                import io
                with zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content))) as archive:
                    self.assertEqual(archive.read('db.sqlite3'), b'test-db')
                    self.assertEqual(archive.read('media/picture.jpg'), b'test-image')
                response.close()
