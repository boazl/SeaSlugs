import tempfile
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from .models import Country, Sea, Region, DiveTrip, Sample, TaxonOrder, TaxonFamily, TaxonGenus


class TaxonFilesOnObservationFormTests(TestCase):
    """The edit form of an order / family / genus observation lets a MANAGER also edit the
    files attached to that taxon (article PDF; for a genus also the identification file with
    its caption and source) -- shared page content, so never offered to ordinary members."""
    PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 20
    PDF = b'%PDF-1.4 test'

    def setUp(self):
        self.manager = User.objects.create_superuser('manager', password='x')
        self.member = User.objects.create_user('member', password='x')
        country = Country.objects.create(name='ישראל', name_en='Israel'); sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        self.order = TaxonOrder.objects.create(name='Nudibranchia')
        self.family = TaxonFamily.objects.create(name='Chromodorididae', order=self.order)
        self.genus = TaxonGenus.objects.create(name='Hypselodoris', family=self.family)
        self.genus_sample = self.sample('genus', 'aaaaaaaaaaa', genus='Hypselodoris', family='Chromodorididae', order='Nudibranchia')
        self.family_sample = self.sample('family', 'bbbbbbbbbbb', family='Chromodorididae', order='Nudibranchia')
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.manager)

    def sample(self, kind, video, **names):
        sample = Sample(owner=self.manager, kind=kind, trip=self.trip, video_url=f'https://youtu.be/{video}', **names)
        sample.save_reviewed(actor=self.manager, approve=True)
        return sample

    def post(self, sample, **extra):
        data = {'kind': sample.kind, 'order': sample.order, 'family': sample.family, 'genus': sample.genus,
                'trip': str(self.trip.pk), 'video_url': sample.video_url}
        data.update(extra)
        return self.client.post(f'/observations/{sample.pk}/edit/', data)

    def upload(self, name, data):
        return SimpleUploadedFile(name, data)

    # --- who sees the fields ---
    def test_manager_sees_the_file_fields_on_a_genus_observation(self):
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        for name in ('taxon_article_pdf', 'taxon_identification_file', 'taxon_identification_caption', 'taxon_identification_caption_en', 'taxon_identification_source'):
            self.assertIn(f'name="{name}"', html)

    def test_ordinary_member_does_not_get_the_file_fields(self):
        self.genus_sample.owner = self.member; self.genus_sample.save()
        self.client.force_login(self.member)
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        self.assertNotIn('taxon_article_pdf', html)
        response = self.post(self.genus_sample, taxon_article_pdf=self.upload('a.pdf', self.PDF))
        self.assertEqual(response.status_code, 302)
        self.genus.refresh_from_db()
        self.assertFalse(self.genus.article_pdf)

    # --- genus ---
    def test_genus_article_and_identification_file_are_saved_from_the_form(self):
        response = self.post(self.genus_sample, taxon_article_pdf=self.upload('a.pdf', self.PDF),
                             taxon_identification_file=self.upload('key.png', self.PNG),
                             taxon_identification_caption='מינים של היפסלודוריס', taxon_identification_caption_en='Species of Hypselodoris',
                             taxon_identification_source='Gosliner 2015')
        self.assertEqual(response.status_code, 302)
        self.genus.refresh_from_db()
        self.assertTrue(self.genus.article_pdf.name.endswith('.pdf'))
        self.assertTrue(self.genus.identification_file.name.endswith('.png'))
        self.assertEqual((self.genus.identification_caption, self.genus.identification_caption_en, self.genus.identification_source),
                         ('מינים של היפסלודוריס', 'Species of Hypselodoris', 'Gosliner 2015'))

    def test_current_files_are_shown_with_links_through_the_public_views(self):
        self.genus.identification_file.save('key.png', ContentFile(self.PNG), save=False)
        self.genus.article_pdf.save('a.pdf', ContentFile(self.PDF), save=True)
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        self.assertIn('href="/genus/Hypselodoris/identification/"', html)
        self.assertIn('href="/genus/Hypselodoris/article.pdf"', html)
        self.assertIn('name="taxon_article_pdf-clear"', html)

    def test_clear_checkbox_removes_a_file(self):
        self.genus.article_pdf.save('a.pdf', ContentFile(self.PDF), save=True)
        self.post(self.genus_sample, **{'taxon_article_pdf-clear': 'on'})
        self.genus.refresh_from_db()
        self.assertFalse(self.genus.article_pdf)

    def test_saving_without_touching_the_files_keeps_them(self):
        self.genus.article_pdf.save('a.pdf', ContentFile(self.PDF), save=False)
        self.genus.identification_caption = 'Keep me'
        self.genus.save()
        self.post(self.genus_sample, taxon_identification_caption='Keep me')
        self.genus.refresh_from_db()
        self.assertTrue(self.genus.article_pdf)
        self.assertEqual(self.genus.identification_caption, 'Keep me')

    def test_replacing_a_file_removes_the_old_one_from_disk(self):
        import os
        self.genus.article_pdf.save('a.pdf', ContentFile(self.PDF), save=True)
        old_path = self.genus.article_pdf.path
        self.post(self.genus_sample, taxon_article_pdf=self.upload('b.pdf', self.PDF + b'2'))
        self.genus.refresh_from_db()
        self.assertNotEqual(self.genus.article_pdf.path, old_path)
        self.assertFalse(os.path.exists(old_path))

    def test_wrong_file_types_are_rejected(self):
        self.post(self.genus_sample, taxon_article_pdf=self.upload('a.png', self.PNG))
        self.post(self.genus_sample, taxon_identification_file=self.upload('a.exe', b'MZ'))
        self.genus.refresh_from_db()
        self.assertFalse(self.genus.article_pdf)
        self.assertFalse(self.genus.identification_file)

    # --- family / order / other kinds ---
    def test_family_observation_saves_the_article_but_not_an_identification_file(self):
        self.post(self.family_sample, taxon_article_pdf=self.upload('f.pdf', self.PDF))
        self.family.refresh_from_db()
        self.assertTrue(self.family.article_pdf)
        response = self.post(self.family_sample, taxon_identification_caption='nope')
        self.assertEqual(response.status_code, 200)       # rejected with a form error, not saved
        self.assertContains(response, 'זמינים רק בסוג')

    def test_order_observation_saves_the_order_article(self):
        order_sample = self.sample('order', 'ccccccccccc', order='Nudibranchia')
        self.post(order_sample, taxon_article_pdf=self.upload('o.pdf', self.PDF))
        self.order.refresh_from_db()
        self.assertTrue(self.order.article_pdf)

    def test_upload_on_a_species_kind_observation_is_rejected(self):
        collection = self.sample('collection', 'ddddddddddd', title='Trip video')
        response = self.post(collection, taxon_article_pdf=self.upload('a.pdf', self.PDF))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'מתאימים רק לדגימה מסוג סדרה, משפחה או סוג')
        for model in (TaxonOrder, TaxonFamily, TaxonGenus):
            self.assertFalse(model.objects.get().article_pdf)

    def test_a_name_with_no_taxonomy_row_cannot_take_a_file(self):
        orphan = self.sample('genus', 'eeeeeeeeeee', genus='Nosuchgenus')
        response = self.post(orphan, taxon_article_pdf=self.upload('a.pdf', self.PDF))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'לא נמצאה שורה בטבלת הטקסונומיה')
        self.assertFalse(TaxonGenus.objects.get(name='Hypselodoris').article_pdf)

    # --- public streaming of family/order articles ---
    def test_family_and_order_articles_are_streamed_and_linked_from_their_pages(self):
        self.family.article_pdf.save('f.pdf', ContentFile(self.PDF), save=True)
        self.order.article_pdf.save('o.pdf', ContentFile(self.PDF), save=True)
        for url in (f'/family/{self.family.name}/article.pdf', f'/order/{self.order.pk}/article.pdf'):
            response = self.client.get(url)
            self.assertEqual((response.status_code, response['Content-Type']), (200, 'application/pdf'))

    def test_articles_404_without_a_file(self):
        self.assertEqual(self.client.get(f'/family/{self.family.name}/article.pdf').status_code, 404)
        self.assertEqual(self.client.get(f'/order/{self.order.pk}/article.pdf').status_code, 404)

    # --- layout ---
    def test_save_and_delete_button_rows_are_spaced_apart(self):
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        self.assertIn('class="actions form-actions" style="margin:24px 0"', html)
