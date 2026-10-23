import tempfile
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from .models import Article, Country, Sea, Region, DiveTrip, Sample, TaxonOrder, TaxonFamily, TaxonGenus


class TaxonFilesOnObservationFormTests(TestCase):
    """The edit form of an order / family / genus observation lets a MANAGER also edit what is attached
    to that taxon (the articles it picks from the article library; for a genus also the identification
    file with its caption and source) -- shared page content, so never offered to ordinary members."""
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
        self.article = self.make_article('yonow-2020', 'Red Sea Phyllidiidae')

    def make_article(self, slug, title):
        article = Article(slug=slug, title_he=title, title_en=title)
        article.pdf_en.save(f'{slug}.pdf', ContentFile(self.PDF), save=False)
        article.save()
        return article

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
        for name in ('taxon_articles', 'taxon_identification_file', 'taxon_identification_caption', 'taxon_identification_caption_en', 'taxon_identification_source'):
            self.assertIn(f'name="{name}"', html)
        self.assertNotIn('taxon_article_pdf', html)       # no upload here any more: articles are uploaded once, in the library
        self.assertIn(f'<option value="{self.article.pk}">Red Sea Phyllidiidae</option>', html)
    def test_ordinary_member_does_not_get_the_file_fields(self):
        self.genus_sample.owner = self.member; self.genus_sample.save()
        self.client.force_login(self.member)
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        self.assertNotIn('taxon_articles', html)
        response = self.post(self.genus_sample, taxon_articles=[self.article.pk])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.genus.articles.exists())
    # --- genus ---
    def test_genus_article_and_identification_file_are_saved_from_the_form(self):
        response = self.post(self.genus_sample, taxon_articles=[self.article.pk],
                             taxon_identification_file=self.upload('key.png', self.PNG),
                             taxon_identification_caption='מינים של היפסלודוריס', taxon_identification_caption_en='Species of Hypselodoris',
                             taxon_identification_source='Gosliner 2015')
        self.assertEqual(response.status_code, 302)
        self.genus.refresh_from_db()
        self.assertEqual(list(self.genus.articles.all()), [self.article])
        self.assertTrue(self.genus.identification_file.name.endswith('.png'))
        self.assertEqual((self.genus.identification_caption, self.genus.identification_caption_en, self.genus.identification_source),
                         ('מינים של היפסלודוריס', 'Species of Hypselodoris', 'Gosliner 2015'))
        self.assertEqual(Article.objects.count(), 1)       # picked, not copied
    def test_current_files_are_shown_with_links_through_the_public_views(self):
        self.genus.identification_file.save('key.png', ContentFile(self.PNG), save=True)
        self.genus.articles.add(self.article)
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        self.assertIn('href="/genus/Hypselodoris/identification/"', html)
        self.assertIn(f'<option value="{self.article.pk}" selected>Red Sea Phyllidiidae</option>', html)
    def test_clear_checkbox_removes_a_file_and_unselecting_drops_an_article(self):
        self.genus.identification_file.save('key.png', ContentFile(self.PNG), save=True)
        self.genus.articles.add(self.article)
        self.post(self.genus_sample, **{'taxon_identification_file-clear': 'on'})
        self.genus.refresh_from_db()
        self.assertFalse(self.genus.identification_file)
        self.assertFalse(self.genus.articles.exists())
        self.assertTrue(Article.objects.filter(pk=self.article.pk).exists())     # the article itself stays in the library
    def test_saving_without_touching_the_files_keeps_them(self):
        self.genus.identification_file.save('key.png', ContentFile(self.PNG), save=False)
        self.genus.identification_caption = 'Keep me'
        self.genus.save()
        self.genus.articles.add(self.article)
        # a browser resubmits the selected articles as they are
        self.post(self.genus_sample, taxon_identification_caption='Keep me', taxon_articles=[self.article.pk])
        self.genus.refresh_from_db()
        self.assertTrue(self.genus.identification_file)
        self.assertEqual(list(self.genus.articles.all()), [self.article])
        self.assertEqual(self.genus.identification_caption, 'Keep me')
    def test_replacing_a_file_removes_the_old_one_from_disk(self):
        import os
        self.genus.identification_file.save('a.png', ContentFile(self.PNG), save=True)
        old_path = self.genus.identification_file.path
        self.post(self.genus_sample, taxon_identification_file=self.upload('b.png', self.PNG + b'2'))
        self.genus.refresh_from_db()
        self.assertNotEqual(self.genus.identification_file.path, old_path)
        self.assertFalse(os.path.exists(old_path))
    def test_wrong_file_types_and_unknown_articles_are_rejected(self):
        response = self.post(self.genus_sample, taxon_articles=[self.article.pk + 999])
        self.assertEqual(response.status_code, 200)
        self.post(self.genus_sample, taxon_identification_file=self.upload('a.exe', b'MZ'))
        self.genus.refresh_from_db()
        self.assertFalse(self.genus.articles.exists())
        self.assertFalse(self.genus.identification_file)
    def test_article_pdf_and_identification_file_limit_is_20mb(self):
        from .forms import validate_taxon_file_size
        from .models import validate_article_pdf_size
        from django import forms
        from django.core.exceptions import ValidationError
        mb = 1024 * 1024
        validate_article_pdf_size(SimpleUploadedFile('a.pdf', b'x' * (20 * mb)))          # exactly 20MB: accepted
        with self.assertRaisesMessage(ValidationError, 'עד 20MB'):
            validate_article_pdf_size(SimpleUploadedFile('a.pdf', b'x' * (20 * mb + 1)))
        with self.assertRaisesMessage(forms.ValidationError, 'עד 20MB'):
            validate_taxon_file_size(SimpleUploadedFile('a.pdf', b'x' * (20 * mb + 1)))
    # --- the page texts (description, identification, sources) ---
    def test_texts_are_shown_prefilled_for_genus_family_and_order_and_not_for_members(self):
        self.genus.description_he = 'תיאור הסוג'; self.genus.sources = 'https://example.org/x'; self.genus.save()
        self.family.identification_en = 'Family key'; self.family.save()
        order_sample = self.sample('order', 'ccccccccccc', order='Nudibranchia')
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        for name in ('description_he', 'description_en', 'identification_he', 'identification_en', 'sources'):
            self.assertIn(f'name="taxon_{name}"', html)
        self.assertIn('תיאור הסוג', html)
        self.assertIn('https://example.org/x', html)
        self.assertIn('Family key', self.client.get(f'/observations/{self.family_sample.pk}/edit/').content.decode())
        self.assertIn('name="taxon_description_he"', self.client.get(f'/observations/{order_sample.pk}/edit/').content.decode())
        self.genus_sample.owner = self.member; self.genus_sample.save()
        self.client.force_login(self.member)
        self.assertNotIn('taxon_description_he', self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode())
        self.post(self.genus_sample, taxon_description_he='נסיון')
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.description_he, 'תיאור הסוג')

    def test_texts_are_saved_to_the_genus_family_and_order(self):
        order_sample = self.sample('order', 'ccccccccccc', order='Nudibranchia')
        texts = dict(taxon_description_he='תיאור', taxon_description_en='Description', taxon_identification_he='זיהוי',
                     taxon_identification_en='Key', taxon_sources='https://example.org/a\r\nGosliner 2015')
        for sample, model in ((self.genus_sample, self.genus), (self.family_sample, self.family), (order_sample, self.order)):
            self.assertEqual(self.post(sample, **texts).status_code, 302)
            model.refresh_from_db()
            self.assertEqual((model.description_he, model.description_en, model.identification_he, model.identification_en),
                             ('תיאור', 'Description', 'זיהוי', 'Key'))
            self.assertEqual(model.sources, 'https://example.org/a\nGosliner 2015')     # stored with LF, not the browser's CRLF

    def test_a_text_can_be_cleared_and_an_untouched_text_is_left_alone(self):
        self.genus.description_he = 'שורה א\nשורה ב'; self.genus.description_en = 'Keep'; self.genus.save()
        # resubmitting the stored text (as a browser does, with CRLF) changes nothing
        self.post(self.genus_sample, taxon_description_he='שורה א\r\nשורה ב', taxon_description_en='Keep')
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.description_he, 'שורה א\nשורה ב')
        self.post(self.genus_sample, taxon_description_he='', taxon_description_en='Keep')
        self.genus.refresh_from_db()
        self.assertEqual((self.genus.description_he, self.genus.description_en), ('', 'Keep'))

    def test_a_text_cannot_be_saved_on_a_species_observation_or_a_name_with_no_row(self):
        collection = self.sample('collection', 'ddddddddddd', title='Trip video')
        response = self.post(collection, taxon_description_he='x')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'מתאימים רק לדגימה מסוג סדרה, משפחה או סוג')
        orphan = self.sample('genus', 'eeeeeeeeeee', genus='Nosuchgenus')
        self.assertEqual(self.post(orphan, taxon_description_he='x').status_code, 200)
        self.assertEqual(TaxonGenus.objects.get(name='Hypselodoris').description_he, '')

    # --- family / order / other kinds ---
    def test_family_observation_saves_the_article_but_not_an_identification_file(self):
        self.post(self.family_sample, taxon_articles=[self.article.pk])
        self.assertEqual(list(self.family.articles.all()), [self.article])
        response = self.post(self.family_sample, taxon_identification_caption='nope', taxon_articles=[self.article.pk])
        self.assertEqual(response.status_code, 200)       # rejected with a form error, not saved
        self.assertContains(response, 'זמינים רק בסוג')
    def test_order_observation_saves_the_order_article(self):
        order_sample = self.sample('order', 'ccccccccccc', order='Nudibranchia')
        self.post(order_sample, taxon_articles=[self.article.pk])
        self.assertEqual(list(self.order.articles.all()), [self.article])
    def test_articles_on_a_species_kind_observation_are_rejected(self):
        collection = self.sample('collection', 'ddddddddddd', title='Trip video')
        response = self.post(collection, taxon_articles=[self.article.pk])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'מתאימים רק לדגימה מסוג סדרה, משפחה או סוג')
        for model in (TaxonOrder, TaxonFamily, TaxonGenus):
            self.assertFalse(model.objects.get().articles.exists())
    def test_a_name_with_no_taxonomy_row_cannot_take_a_file(self):
        orphan = self.sample('genus', 'eeeeeeeeeee', genus='Nosuchgenus')
        response = self.post(orphan, taxon_articles=[self.article.pk])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'לא נמצאה שורה בטבלת הטקסונומיה')
        self.assertFalse(TaxonGenus.objects.get(name='Hypselodoris').articles.exists())
    # --- public streaming of family/order articles ---
    def test_family_and_order_articles_are_streamed_and_the_old_addresses_lead_to_them(self):
        self.family.articles.add(self.article)
        self.order.articles.add(self.article)
        response = self.client.get(f'/articles/{self.article.slug}/en.pdf')
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'application/pdf'))
        for url in (f'/family/{self.family.name}/article.pdf', f'/order/{self.order.pk}/article.pdf'):
            self.assertRedirects(self.client.get(url), f'/articles/{self.article.slug}/en.pdf')
    def test_articles_404_without_a_file(self):
        self.assertEqual(self.client.get(f'/family/{self.family.name}/article.pdf').status_code, 404)
        self.assertEqual(self.client.get(f'/order/{self.order.pk}/article.pdf').status_code, 404)

    # --- layout ---
    def test_save_and_delete_button_rows_are_spaced_apart(self):
        html = self.client.get(f'/observations/{self.genus_sample.pk}/edit/').content.decode()
        self.assertIn('class="actions form-actions" style="margin:24px 0"', html)


class ArticleFileHandlingTests(TestCase):
    """Replacing or clearing an article PDF in the admin must not leave the old file on disk, and the
    streamed article must always be re-validated by the browser (the address never changes)."""

    def setUp(self):
        import shutil
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.article = Article(slug='phyllidiidae', title_en='Phyllidiidae')
        self.article.pdf_en.save('old.pdf', ContentFile(b'%PDF-1.4 old'), save=True)

    def test_replacing_the_file_removes_the_old_one(self):
        import os
        old_path = self.article.pdf_en.path
        self.article.pdf_en = SimpleUploadedFile('new.pdf', b'%PDF-1.4 new', content_type='application/pdf')
        self.article.save()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(self.article.pdf_en.path))

    def test_clearing_the_file_removes_it_from_disk(self):
        import os
        old_path = self.article.pdf_en.path
        self.article.pdf_en = ''
        self.article.save()
        self.assertFalse(os.path.exists(old_path))

    def test_an_unrelated_save_keeps_the_file(self):
        import os
        path = self.article.pdf_en.path
        self.article.title_he = 'x'
        self.article.save()
        self.assertTrue(os.path.exists(path))

    def test_the_article_is_revalidated_by_the_browser_and_a_replaced_file_is_served_at_once(self):
        url = '/articles/phyllidiidae/en.pdf'
        first = self.client.get(url)
        self.assertEqual(b''.join(first.streaming_content), b'%PDF-1.4 old')
        self.assertIn('no-cache', first['Cache-Control'])
        self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=first['ETag']).status_code, 304)
        self.article.pdf_en = SimpleUploadedFile('new.pdf', b'%PDF-1.4 new', content_type='application/pdf')
        self.article.save()
        second = self.client.get(url, HTTP_IF_NONE_MATCH=first['ETag'])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(b''.join(second.streaming_content), b'%PDF-1.4 new')
