import io
from PIL import Image
from .models import TaxonGenus
from . import test_taxon_files_form as _base
from django.test import TestCase


def pdf(*colors):
    """A PDF with one plain page per colour."""
    pages = [Image.new('RGB', (200, 280), color) for color in colors]
    buffer = io.BytesIO()
    pages[0].save(buffer, 'PDF', save_all=True, append_images=pages[1:])
    return buffer.getvalue()


def colour_of(jpeg):
    return Image.open(io.BytesIO(jpeg)).convert('RGB').getpixel((10, 10))


class BilingualIdentificationFileTests(TestCase):
    """A genus has an identification file in Hebrew and in English; each language's page shows its own
    (else the other one), as a preview of a chosen PDF page that also opens the PDF at that page."""
    setUp = _base.TaxonFilesOnObservationFormTests.setUp; make_article = _base.TaxonFilesOnObservationFormTests.make_article; sample = _base.TaxonFilesOnObservationFormTests.sample; post = _base.TaxonFilesOnObservationFormTests.post; upload = _base.TaxonFilesOnObservationFormTests.upload
    PNG = _base.TaxonFilesOnObservationFormTests.PNG; PDF = _base.TaxonFilesOnObservationFormTests.PDF

    def test_both_files_and_their_pages_are_saved_from_the_observation_form(self):
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        for name in ('taxon_identification_file', 'taxon_identification_page', 'taxon_identification_file_en', 'taxon_identification_page_en'):
            self.assertIn(f'name="{name}"', html)
        response = self.post(self.genus_sample,
                             taxon_identification_file=self.upload('he.pdf', pdf('red', 'blue')), taxon_identification_page='2',
                             taxon_identification_file_en=self.upload('en.pdf', pdf('green')), taxon_identification_page_en='1')
        self.assertEqual(response.status_code, 302)
        genus = TaxonGenus.objects.get(pk=self.genus.pk)
        self.assertTrue(genus.identification_file and genus.identification_file_en)
        self.assertEqual((genus.identification_page, genus.identification_page_en), (2, 1))
        self.assertTrue(genus.identification_thumb and genus.identification_thumb_en)   # previews made on save

    def test_preview_is_the_chosen_page_and_follows_a_page_change(self):
        self.post(self.genus_sample, taxon_identification_file=self.upload('he.pdf', pdf('red', 'blue')), taxon_identification_page='2')
        preview = b''.join(self.client.get('/genus/Hypselodoris/identification/he/preview.jpg').streaming_content)
        r, g, b = colour_of(preview); self.assertGreater(b, 200); self.assertLess(r, 60)       # blue = page 2
        old_thumb = TaxonGenus.objects.get(pk=self.genus.pk).identification_thumb.name
        self.post(self.genus_sample, taxon_identification_page='1')
        genus = TaxonGenus.objects.get(pk=self.genus.pk)
        self.assertNotEqual(genus.identification_thumb.name, old_thumb)
        self.assertFalse(genus.identification_thumb.storage.exists(old_thumb))                # the old preview is removed
        r, g, b = colour_of(b''.join(self.client.get('/genus/Hypselodoris/identification/he/preview.jpg').streaming_content))
        self.assertGreater(r, 200)                                                            # red = page 1

    def test_each_language_gets_its_own_file_else_the_other(self):
        from .views import genus_identification_context
        self.post(self.genus_sample, taxon_identification_file=self.upload('he.pdf', pdf('red', 'blue')), taxon_identification_page='2')
        genus = TaxonGenus.objects.get(pk=self.genus.pk)
        self.assertEqual(genus_identification_context(genus, 'en')['identification_url'], '/genus/Hypselodoris/identification/#page=2')
        self.post(self.genus_sample, taxon_identification_file_en=self.upload('en.pdf', pdf('green')))
        genus = TaxonGenus.objects.get(pk=self.genus.pk)
        en, he = genus_identification_context(genus, 'en'), genus_identification_context(genus, 'he')
        self.assertEqual(en['identification_url'], '/genus/Hypselodoris/identification/en/')
        self.assertEqual(en['identification_preview_url'], '/genus/Hypselodoris/identification/en/preview.jpg')
        self.assertEqual(he['identification_url'], '/genus/Hypselodoris/identification/#page=2')
        self.assertEqual(self.client.get('/genus/Hypselodoris/identification/en/')['Content-Type'], 'application/pdf')

    def test_an_image_file_is_its_own_preview(self):
        self.post(self.genus_sample, taxon_identification_file_en=self.upload('plate.png', self.PNG))
        genus = TaxonGenus.objects.get(pk=self.genus.pk)
        self.assertFalse(genus.identification_thumb_en)
        self.assertEqual(self.client.get('/genus/Hypselodoris/identification/en/preview.jpg')['Content-Type'], 'image/png')

    def test_empty_page_box_on_a_family_observation_is_not_an_edit(self):
        response = self.post(self.family_sample, taxon_identification_page='', taxon_identification_page_en='')
        self.assertEqual(response.status_code, 302)
