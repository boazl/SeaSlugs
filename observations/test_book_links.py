import tempfile
from pathlib import Path

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase, override_settings
from django.urls import reverse

from .book_links import FILES, linked_citations, pdf_page


class BookLinksTests(TestCase):
    """Citations of Gosliner et al. with a page number get links to the owner's PDF of that edition (both languages,
    the page's language first) at the right PDF page -- only for a superuser and only when the PDFs are on this computer
    (settings.BOOK_PDF_DIR). The edition is the nearest edition mark before the page; a page without one gets no link.
    A link opens a page viewer (the page as an image, previous / next, the other language, the whole PDF) in one named
    tab; the viewer, the page image and the PDF are for superusers only. Everyone else sees the plain text."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        for name in FILES.values():
            Path(self.folder.name, name).write_bytes(b'%PDF-1.4 test')
        self.boss = User.objects.create_superuser('boss', password='x')
        self.staff = User.objects.create_user('staff', password='x', is_staff=True)

    def tearDown(self):
        self.folder.cleanup()

    def test_pdf_pages(self):
        self.assertEqual(pdf_page('2', 279), 280)
        self.assertEqual((pdf_page('3', 320), pdf_page('3', 321), pdf_page('3', 4)), (162, 162, 4))

    def test_links_for_the_superuser(self):
        text = ('במהדורה השנייה: Eubranchus sp. 15 (עמ\' 279). במהדורה השלישית: Eubranchus sp. 17 (עמ\' 320-321).\n'
                'Plain <b> text')
        with override_settings(BOOK_PDF_DIR=self.folder.name):
            html = linked_citations(text, self.boss, 'he')
            self.assertIn(reverse('book-page', args=['2', 'he', 280]), html)
            self.assertIn(reverse('book-page', args=['3', 'en', 162]), html)
            self.assertLess(html.index('/2/he/'), html.index('/2/en/'))   # the page's language first
            self.assertIn('&lt;b&gt;', html)                               # the text itself stays escaped
            self.assertIn('<br>', html)
            self.assertNotIn('book-link', linked_citations(text, self.staff, 'he'))
            self.assertNotIn('book-link', linked_citations(text, AnonymousUser(), 'he'))
            self.assertNotIn('book-link', linked_citations('Size 7 mm (עמ\' 12)', self.boss, 'he'))  # no edition mark
        with override_settings(BOOK_PDF_DIR=''):
            self.assertNotIn('book-link', linked_citations(text, self.boss, 'he'))

    def test_english_citation(self):
        text = 'About 7 mm. (after Gosliner, Valdés & Behrens 2026, 3rd ed., pp. 320-321, as Eubranchus sp. 17)'
        with override_settings(BOOK_PDF_DIR=self.folder.name):
            html = linked_citations(text, self.boss, 'en')
        self.assertIn(reverse('book-page', args=['3', 'en', 162]), html)
        self.assertLess(html.index('/3/en/'), html.index('/3/he/'))

    def test_page_viewer(self):
        import pypdfium2 as pdfium
        document = pdfium.PdfDocument.new()
        for _ in range(3):
            document.new_page(300, 400)
        for name in FILES.values():
            document.save(str(Path(self.folder.name, name)))
        document.close()
        with override_settings(BOOK_PDF_DIR=self.folder.name):
            self.client.force_login(self.staff)
            self.assertEqual(self.client.get(reverse('book-page', args=['3', 'he', 2])).status_code, 403)
            self.client.force_login(self.boss)
            page = self.client.get(reverse('book-page', args=['3', 'he', 2])).content.decode()
            self.assertIn(reverse('book-page-image', args=['3', 'he', 2]), page)
            self.assertIn(reverse('book-page', args=['3', 'he', 1]), page)     # previous
            self.assertIn(reverse('book-page', args=['3', 'he', 3]), page)     # next
            self.assertIn(reverse('book-page', args=['3', 'en', 2]), page)     # the other language
            image = self.client.get(reverse('book-page-image', args=['3', 'he', 2]))
            self.assertEqual((image.status_code, image['Content-Type']), (200, 'image/jpeg'))
            self.assertEqual(self.client.get(reverse('book-page-image', args=['3', 'he', 9])).status_code, 404)
            self.assertIn('מתוך 3', self.client.get(reverse('book-page', args=['3', 'he', 99])).content.decode())

    def test_pdf_view_superusers_only(self):
        url = reverse('book-pdf', args=['3', 'he'])
        with override_settings(BOOK_PDF_DIR=self.folder.name):
            self.client.force_login(self.staff)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(self.boss)
            response = self.client.get(url)
            self.assertEqual((response.status_code, response['Content-Type']), (200, 'application/pdf'))
            self.assertEqual(self.client.get(reverse('book-pdf', args=['9', 'he'])).status_code, 404)
        with override_settings(BOOK_PDF_DIR=''):
            self.assertEqual(self.client.get(url).status_code, 404)
