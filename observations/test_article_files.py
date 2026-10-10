"""Admin page "קבצי מאמרים": lists every article PDF, marks the unused ones and deletes only those."""
import os
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from .models import TaxonFamily, TaxonGenus


class ArticleFilesPageTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.admin = User.objects.create_superuser('boss', 'b@example.org', 'x')
        self.staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.family = TaxonFamily.objects.create(name='Phyllidiidae')
        self.family.article_pdf.save('used.pdf', ContentFile(b'%PDF-1.4 used'), save=True)
        self.orphan_name = 'articles/families/zookeys-770-009.pdf'
        os.makedirs(os.path.join(self.media, 'articles/families'), exist_ok=True)
        with open(os.path.join(self.media, self.orphan_name), 'wb') as f:
            f.write(b'%PDF-1.4 orphan')
        self.client.force_login(self.admin)

    def test_lists_files_marks_orphans_and_links_the_row_that_uses_a_file(self):
        response = self.client.get('/admin/article-files/')
        self.assertContains(response, self.orphan_name)
        self.assertContains(response, self.family.article_pdf.name)
        self.assertContains(response, 'Phyllidiidae')
        self.assertContains(response, f'/admin/observations/taxonfamily/{self.family.pk}/change/')
        self.assertContains(response, "1 מהם יתומים")
        # exactly one delete form: the orphan's
        self.assertEqual(response.content.decode().count('action="/admin/article-files/delete/"'), 1)

    def test_only_superusers_can_use_the_page(self):
        self.client.force_login(self.staff)
        for url in ('/admin/article-files/', f'/admin/article-files/open/?name={self.orphan_name}'):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post('/admin/article-files/delete/', {'name': self.orphan_name}).status_code, 403)
        self.assertTrue(os.path.exists(os.path.join(self.media, self.orphan_name)))
        self.client.logout()
        self.assertEqual(self.client.get('/admin/article-files/').status_code, 302)

    def test_an_orphan_can_be_opened_and_deleted(self):
        opened = self.client.get('/admin/article-files/open/', {'name': self.orphan_name})
        self.assertEqual(b''.join(opened.streaming_content), b'%PDF-1.4 orphan')
        response = self.client.post('/admin/article-files/delete/', {'name': self.orphan_name}, follow=True)
        self.assertFalse(os.path.exists(os.path.join(self.media, self.orphan_name)))
        self.assertContains(response, 'הקובץ נמחק')

    def test_a_file_in_use_is_never_deleted_here(self):
        path = self.family.article_pdf.path
        response = self.client.post('/admin/article-files/delete/', {'name': self.family.article_pdf.name}, follow=True)
        self.assertTrue(os.path.exists(path))
        self.assertContains(response, 'הקובץ בשימוש')

    def test_paths_outside_the_articles_folder_are_refused(self):
        with open(os.path.join(self.media, 'secret.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4 secret')
        for name in ('secret.pdf', 'articles/../secret.pdf', '../secret.pdf', '/etc/passwd', 'articles/families/'):
            self.assertEqual(self.client.get('/admin/article-files/open/', {'name': name}).status_code, 404, name)
            self.client.post('/admin/article-files/delete/', {'name': name})
        self.assertTrue(os.path.exists(os.path.join(self.media, 'secret.pdf')))

    def test_a_row_whose_file_is_missing_from_the_disk_is_reported(self):
        os.remove(self.family.article_pdf.path)
        response = self.client.get('/admin/article-files/')
        self.assertContains(response, 'שורות שהקובץ שלהן חסר בדיסק')

    def test_the_admin_index_links_to_the_page(self):
        self.assertContains(self.client.get('/admin/'), '/admin/article-files/')

    def test_delete_requires_post(self):
        self.assertEqual(self.client.get('/admin/article-files/delete/').status_code, 405)


class TestsNeverTouchTheRealMediaFolderTests(TestCase):
    def test_media_root_is_a_throw_away_folder_while_testing(self):
        from django.conf import settings
        self.assertIn('seaslugs-test-media-', str(settings.MEDIA_ROOT))


class IdentificationFilesOnThePageTests(TestCase):
    """The genus identification file lives under media/identification/genera and must show up on the page too."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(User.objects.create_superuser('boss', 'b@example.org', 'x'))
        self.genus = TaxonGenus.objects.create(name='Coryphellina')
        self.genus.identification_file.save('key.pdf', ContentFile(b'%PDF-1.4 key'), save=True)
        self.genus.article_pdf.save('art.pdf', ContentFile(b'%PDF-1.4 art'), save=True)
        os.makedirs(os.path.join(self.media, 'identification/genera'), exist_ok=True)
        self.orphan = 'identification/genera/old.png'
        with open(os.path.join(self.media, self.orphan), 'wb') as f:
            f.write(b'\x89PNG fake')

    def test_identification_and_article_files_are_both_listed_with_their_kind_and_row(self):
        page = self.client.get('/admin/article-files/').content.decode()
        self.assertIn(self.genus.identification_file.name, page)
        self.assertIn(self.genus.article_pdf.name, page)
        self.assertIn(self.orphan, page)
        self.assertIn('זיהוי', page)
        self.assertIn(f'/admin/observations/taxongenus/{self.genus.pk}/change/', page)
        self.assertIn('1 מהם יתומים', page)

    def test_an_identification_image_opens_with_its_content_type_and_an_orphan_one_can_be_deleted(self):
        opened = self.client.get('/admin/article-files/open/', {'name': self.orphan})
        self.assertEqual(opened['Content-Type'], 'image/png')
        self.client.post('/admin/article-files/delete/', {'name': self.orphan})
        self.assertFalse(os.path.exists(os.path.join(self.media, self.orphan)))

    def test_an_identification_file_in_use_is_not_deleted_here(self):
        path = self.genus.identification_file.path
        self.client.post('/admin/article-files/delete/', {'name': self.genus.identification_file.name})
        self.assertTrue(os.path.exists(path))

    def test_the_public_identification_file_is_revalidated_by_the_browser(self):
        first = self.client.get('/genus/Coryphellina/identification/')
        self.assertEqual(first.status_code, 200)
        self.assertIn('no-cache', first['Cache-Control'])
        self.assertEqual(self.client.get('/genus/Coryphellina/identification/', HTTP_IF_NONE_MATCH=first['ETag']).status_code, 304)
