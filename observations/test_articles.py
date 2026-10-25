"""The article library: an article (its PDF in Hebrew and/or English) is uploaded once and picked by the
species, orders, families, genera and dive trips it concerns; the "מאמרים" / "Articles" section on their
pages, the /articles/ list, the menu item, the home page, the species+area page note, and migration 0077
that moved the old one-file-per-row PDFs into the library."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase, override_settings

from .models import (Article, Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea, TaxonFamily,
                     TaxonGenus, TaxonOrder)
from .names import italicize_names
from . import seo_text

PDF = b'%PDF-1.4 test'


class MediaMixin:
    def use_temp_media(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

    def make_article(self, slug, title_he='', title_en='', he=False, en=True, **extra):
        article = Article(slug=slug, title_he=title_he, title_en=title_en, **extra)
        if he:
            article.pdf_he.save(f'{slug}-he.pdf', ContentFile(PDF), save=False)
        if en:
            article.pdf_en.save(f'{slug}-en.pdf', ContentFile(PDF), save=False)
        article.save()
        return article


class ArticleFixture(MediaMixin, TestCase):
    """Phyllidia ocellata observed in two areas (two species pages) and P. undula in one."""

    def setUp(self):
        self.use_temp_media()
        self.owner = User.objects.create_superuser('manager', password='x')
        israel = Country.objects.create(name='ישראל', name_en='Israel')
        red = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        eilat = Region.objects.create(name='אילת', name_en='Eilat', country=israel, sea=red)
        solomons = Country.objects.create(name='איי שלמה', name_en='Solomon Islands')
        pacific = Sea.objects.create(name='האוקיינוס השקט', name_en='Pacific Ocean')
        gizo = Region.objects.create(name='גיזו', name_en='Gizo', country=solomons, sea=pacific)
        self.eilat_trip = DiveTrip.objects.create(title='אילת', year=2017, country=israel, region=eilat)
        self.solomon_trip = DiveTrip.objects.create(title='איי שלמה', year=2023, country=solomons, region=gizo)
        self.order = TaxonOrder.objects.create(name='Nudibranchia')
        self.family = TaxonFamily.objects.create(name='Phyllidiidae', order=self.order)
        self.genus = TaxonGenus.objects.create(name='Phyllidia', family=self.family)
        self.ocellata = Species.objects.create(genus='Phyllidia', species='ocellata', author='Cuvier, 1804')
        self.undula = Species.objects.create(genus='Phyllidia', species='undula', author='Yonow, 1986')
        for species, trip, video in ((self.ocellata, self.eilat_trip, 'aaaaaaaaaaa'), (self.ocellata, self.solomon_trip, 'bbbbbbbbbbb'),
                                     (self.undula, self.eilat_trip, 'ccccccccccc')):
            Sample(owner=self.owner, trip=trip, species=species, video_url=f'https://youtu.be/{video}').save_reviewed()
        self.ocellata_eilat = SpeciesArea.objects.get(species=self.ocellata, country=israel)
        self.ocellata_solomons = SpeciesArea.objects.get(species=self.ocellata, country=solomons)
        self.undula_eilat = SpeciesArea.objects.get(species=self.undula)

    def page(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()


class ArticleModelTests(ArticleFixture):
    def test_an_article_needs_a_title(self):
        # (its content -- a PDF or sections written on the site -- is required by the admin form, see WrittenArticleTests)
        with self.assertRaisesMessage(ValidationError, 'כותרת'):
            Article(slug='x').full_clean()
        self.make_article('ok', title_en='Paper').full_clean()

    def test_the_pdf_of_the_page_language_else_the_other_one(self):
        both = self.make_article('both', 'מאמר', 'Paper', he=True, en=True)
        english = self.make_article('english', title_en='Paper')
        self.assertEqual((both.pdf_lang('he'), both.pdf_lang('en')), ('he', 'en'))
        self.assertEqual((english.pdf_lang('he'), english.pdf_lang('en')), ('en', 'en'))
        self.assertEqual(english.pdf_url('he'), '/articles/english/en.pdf')
        self.assertEqual((english.title('he'), english.title('en')), ('Paper', 'Paper'))

    def test_the_pdf_is_streamed_and_missing_ones_are_404(self):
        self.make_article('paper', title_en='Paper')
        response = self.client.get('/articles/paper/en.pdf')
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'application/pdf'))
        self.assertEqual(b''.join(response.streaming_content), PDF)
        for url in ('/articles/paper/he.pdf', '/articles/paper/fr.pdf', '/articles/nosuch/en.pdf'):
            self.assertEqual(self.client.get(url).status_code, 404, url)


class SpeciesPageArticlesTests(ArticleFixture):
    def test_one_article_picked_by_two_species_shows_on_all_their_pages_uploaded_once(self):
        article = self.make_article('phyllidia-ocellata-complex', 'Phyllidia ocellata — מין אחד או קומפלקס?',
                                    'Phyllidia ocellata — one species or a complex?', he=True, en=True)
        self.ocellata.articles.add(article)
        self.undula.articles.add(article)
        for area in (self.ocellata_eilat, self.ocellata_solomons, self.undula_eilat):
            html = self.page(f'/species/{area.slug}/')
            self.assertIn('<section class="species-section" id="articles">', html)
            self.assertIn('href="/articles/phyllidia-ocellata-complex/he.pdf"', html)
            self.assertIn('<i>Phyllidia ocellata</i> — מין אחד או קומפלקס?', html)
            # below the description section
            self.assertLess(html.index('<h2>תיאור</h2>'), html.index('id="articles"'))
        self.assertEqual(Article.objects.count(), 1)

    def test_the_english_page_shows_the_english_title_and_pdf_only(self):
        article = self.make_article('paper', 'מאמר בעברית', 'English paper', he=True, en=True)
        self.ocellata.articles.add(article)
        html = self.page(f'/species/{self.ocellata_eilat.slug}/?lang=en')
        self.assertIn('<h2>Articles</h2>', html)
        self.assertIn('href="/articles/paper/en.pdf"', html)
        self.assertNotIn('מאמר בעברית', html)
        self.assertNotIn('/articles/paper/he.pdf', html)

    def test_a_pdf_only_in_the_other_language_says_so(self):
        self.ocellata.articles.add(self.make_article('english-only', title_en='Paper'))
        self.assertIn('<small>(באנגלית)</small>', self.page(f'/species/{self.ocellata_eilat.slug}/'))
        self.ocellata.articles.set([self.make_article('hebrew-only', title_he='מאמר', he=True, en=False)])
        self.assertIn('<small>(in Hebrew)</small>', self.page(f'/species/{self.ocellata_eilat.slug}/?lang=en'))

    def test_no_section_without_articles(self):
        self.assertNotIn('id="articles"', self.page(f'/species/{self.ocellata_eilat.slug}/'))

    def test_genus_family_order_and_trip_pages_show_their_articles(self):
        article = self.make_article('yonow-2020', title_en='Red Sea Phyllidiidae')
        for row in (self.genus, self.family, self.order, self.eilat_trip):
            row.articles.add(article)
        for url in (f'/genus/{self.genus.name}/', f'/family/{self.family.name}/', f'/order/{self.order.pk}/',
                    '/observations/trips/'):
            html = self.page(url)
            self.assertIn('href="/articles/yonow-2020/en.pdf"', html, url)


class SpeciesAreaNoteTests(ArticleFixture):
    HE = 'הזיהוי אינו ודאי: ייתכן שזהו מופע של Phyllidia undula, שתועד באותו אתר — ראו מאמר.'
    EN = 'Identification uncertain: this may be a form of Phyllidia undula, recorded at the same site — see article.'

    def setUp(self):
        super().setUp()
        self.ocellata_eilat.note_he, self.ocellata_eilat.note_en = self.HE, self.EN
        self.ocellata_eilat.save()

    def test_the_note_shows_on_its_own_page_only_with_names_in_italics(self):
        html = self.page(f'/species/{self.ocellata_eilat.slug}/')
        self.assertIn('class="species-note"', html)
        self.assertIn('ייתכן שזהו מופע של <i>Phyllidia undula</i>, שתועד', html)
        self.assertNotIn('class="species-note"', self.page(f'/species/{self.ocellata_solomons.slug}/'))

    def test_see_article_links_to_the_species_article(self):
        self.assertIn('— ראו מאמר.', self.page(f'/species/{self.ocellata_eilat.slug}/'))   # no article yet: plain text
        self.ocellata.articles.add(self.make_article('complex', 'מאמר', 'Paper', he=True, en=True))
        self.assertIn('<a href="/articles/complex/he.pdf">ראו מאמר</a>', self.page(f'/species/{self.ocellata_eilat.slug}/'))
        english = self.page(f'/species/{self.ocellata_eilat.slug}/?lang=en')
        self.assertIn('may be a form of <i>Phyllidia undula</i>, recorded', english)
        self.assertIn('<a href="/articles/complex/en.pdf">see article</a>', english)
        self.assertNotIn('הזיהוי אינו ודאי', english)

    def test_several_articles_link_to_the_articles_section(self):
        self.ocellata.articles.add(self.make_article('one', title_he='א', he=True, en=False),
                                   self.make_article('two', title_he='ב', he=True, en=False))
        self.assertIn('<a href="#articles">ראו מאמר</a>', self.page(f'/species/{self.ocellata_eilat.slug}/'))

    def test_a_note_in_one_language_is_shown_in_both(self):
        self.ocellata_eilat.note_en = ''
        self.ocellata_eilat.save()
        self.assertIn('הזיהוי אינו ודאי', self.page(f'/species/{self.ocellata_eilat.slug}/?lang=en'))

    def test_rebuilding_the_species_areas_keeps_the_notes(self):
        SpeciesArea.rebuild()
        area = SpeciesArea.objects.get(species=self.ocellata, country__name='ישראל')
        self.assertEqual((area.note_he, area.note_en), (self.HE, self.EN))
        self.assertEqual(SpeciesArea.objects.get(species=self.undula).note_he, '')

    def test_the_note_is_editable_in_the_admin(self):
        self.client.force_login(self.owner)
        html = self.page(f'/admin/observations/speciesarea/{self.ocellata_eilat.pk}/change/')
        self.assertIn('name="note_he"', html)
        self.assertIn('name="note_en"', html)


class ItalicNamesInTextTests(ArticleFixture):
    def test_only_catalog_names_genus_and_epithet_with_cf_roman(self):
        html = str(italicize_names('A P. cf. ocellata and Phyllidia undula. This species, Phyllidia ocellata Cuvier, 1804.'))
        self.assertEqual(html, 'A <i>P.</i> cf. <i>ocellata</i> and <i>Phyllidia undula</i>. This species, '
                               '<i>Phyllidia ocellata</i> Cuvier, 1804.')

    def test_text_is_escaped(self):
        self.assertEqual(str(italicize_names('<b>x</b>')), '&lt;b&gt;x&lt;/b&gt;')


class ArticleListAndMenuTests(ArticleFixture):
    def test_the_list_shows_each_article_with_its_pdf_and_the_pages_that_pick_it(self):
        article = self.make_article('complex', 'Phyllidia ocellata — מין אחד?', 'Phyllidia ocellata — one species?',
                                    he=True, en=True, source='Liebes, B. (2026)')
        self.ocellata.articles.add(article)
        self.genus.articles.add(article)
        html = self.page('/articles/')
        self.assertIn('<li id="complex">', html)
        self.assertIn('<i>Phyllidia ocellata</i> — מין אחד?', html)
        self.assertIn('href="/articles/complex/he.pdf"', html)
        self.assertIn('Liebes, B. (2026)', html)
        self.assertIn(f'href="/species/{self.ocellata_eilat.slug}/"', html)
        self.assertIn(f'href="/species/{self.ocellata_solomons.slug}/"', html)
        self.assertIn('href="/genus/Phyllidia/"', html)
        english = self.page('/articles/?lang=en')
        self.assertIn('<h1>Articles</h1>', english)
        self.assertIn('href="/articles/complex/en.pdf"', english)
        self.assertIn(f'href="/species/{self.ocellata_eilat.slug}/?lang=en"', english)
        self.assertNotIn('מין אחד', english)

    def test_an_empty_list(self):
        self.assertIn('עדיין אין מאמרים באתר.', self.page('/articles/'))
        self.assertIn('No articles on the site yet.', self.page('/articles/?lang=en'))

    def test_the_menu_has_articles_in_both_languages_everywhere(self):
        for url in ('/', '/articles/', f'/species/{self.ocellata_eilat.slug}/', '/observations/trips/'):
            self.assertIn('data-he="מאמרים" data-en="Articles"', self.page(url), url)
        self.assertIn('href="/articles/?lang=en"', self.page('/articles/?lang=en'))

    def test_the_admin_lists_articles_and_species_pick_them(self):
        article = self.make_article('paper', title_en='Paper')
        self.client.force_login(self.owner)
        self.assertIn('Paper', self.page('/admin/observations/article/'))
        self.assertIn('name="articles"', self.page(f'/admin/observations/species/{self.ocellata.pk}/change/'))
        self.assertIn('name="articles"', self.page(f'/admin/observations/taxongenus/{self.genus.pk}/change/'))
        self.assertIn('name="pdf_he"', self.page(f'/admin/observations/article/{article.pk}/change/'))


def real_pdf(width=200, height=300):
    """A genuine one-page PDF (blank), which pypdfium2 can render."""
    import io
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument.new()
    document.new_page(width, height)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class ArticlePreviewTests(ArticleFixture):
    def make_real(self, slug='complex', **extra):
        article = Article(slug=slug, title_he='מאמר', title_en='Paper', **extra)
        article.pdf_he.save('he.pdf', ContentFile(real_pdf()), save=False)
        article.pdf_en.save('en.pdf', ContentFile(real_pdf(300, 200)), save=False)
        article.save()
        return Article.objects.get(pk=article.pk)

    def test_uploading_a_pdf_makes_a_preview_of_its_first_page(self):
        article = self.make_real()
        self.assertTrue(article.thumb_he.name.startswith('articles/thumbs/complex-he'))
        self.assertTrue(article.thumb_en.name.startswith('articles/thumbs/complex-en'))
        response = self.client.get('/articles/complex/he.jpg')
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'image/jpeg'))
        from PIL import Image
        import io
        image = Image.open(io.BytesIO(b''.join(response.streaming_content)))
        self.assertEqual(image.size, (200, 300))
        width, height = Image.open(article.thumb_en.path).size
        self.assertEqual(width, 200)
        self.assertIn(height, (133, 134))     # the page's own proportions (300 x 200)

    def test_replacing_or_removing_a_pdf_replaces_or_removes_its_preview(self):
        import os
        from PIL import Image
        article = self.make_real()
        folder = os.path.dirname(article.thumb_he.path)
        article.pdf_he.save('new.pdf', ContentFile(real_pdf(100, 100)), save=False)
        article.pdf_en = ''
        article.save()
        article = Article.objects.get(pk=article.pk)
        self.assertEqual(os.listdir(folder), [os.path.basename(article.thumb_he.path)])    # no old preview left behind
        self.assertEqual(Image.open(article.thumb_he.path).size, (200, 200))              # made from the new (square) page
        self.assertFalse(article.thumb_en)
        self.assertEqual(self.client.get('/articles/complex/en.jpg').status_code, 404)

    def test_an_unrelated_save_keeps_the_preview(self):
        article = self.make_real()
        name = article.thumb_he.name
        article.title_he = 'כותרת חדשה'
        article.save()
        self.assertEqual(Article.objects.get(pk=article.pk).thumb_he.name, name)

    def test_an_older_article_gets_its_preview_the_first_time_it_is_asked_for(self):
        article = self.make_real()
        Article.objects.filter(pk=article.pk).update(thumb_he='')
        self.assertEqual(self.client.get('/articles/complex/he.jpg')['Content-Type'], 'image/jpeg')
        self.assertTrue(Article.objects.get(pk=article.pk).thumb_he)

    def test_a_pdf_that_cannot_be_rendered_shows_a_document_icon(self):
        self.make_article('broken', title_en='Broken')            # its "PDF" is not a real one
        self.assertFalse(Article.objects.get(slug='broken').thumb_en)
        response = self.client.get('/articles/broken/en.jpg')
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'image/svg+xml'))

    def test_the_preview_is_shown_next_to_the_article_everywhere(self):
        article = self.make_real(show_on_home=True)
        self.ocellata.articles.add(article)
        species = self.page(f'/species/{self.ocellata_eilat.slug}/')
        self.assertIn('<a class="article-thumb" href="/articles/complex/he.pdf"', species)
        self.assertIn('<img src="/articles/complex/he.jpg"', species)
        self.assertIn('<img src="/articles/complex/en.jpg"', self.page(f'/species/{self.ocellata_eilat.slug}/?lang=en'))
        self.assertIn('<img src="/articles/complex/he.jpg"', self.page('/articles/?lang=he'))
        self.assertIn('src="/articles/complex/he.jpg"', self.page('/?lang=he'))

    def test_the_preview_of_an_english_only_article_on_a_hebrew_page_is_the_english_one(self):
        article = Article(slug='english', title_en='Paper')
        article.pdf_en.save('en.pdf', ContentFile(real_pdf()), save=False)
        article.save()
        self.ocellata.articles.add(article)
        self.assertIn('<img src="/articles/english/en.jpg"', self.page(f'/species/{self.ocellata_eilat.slug}/'))


class SpeciesFormNoteTests(ArticleFixture):
    def test_the_species_form_lists_its_areas_with_their_notes_and_saves_them(self):
        self.ocellata_eilat.note_he = 'הערה קיימת'
        self.ocellata_eilat.save()
        self.client.force_login(self.owner)
        url = f'/admin/observations/species/{self.ocellata.pk}/change/'
        html = self.page(url)
        self.assertIn('הערות לעמודי המין באזורים', html)
        self.assertIn(f'href="/species/{self.ocellata_eilat.slug}/"', html)
        self.assertIn(f'href="/species/{self.ocellata_solomons.slug}/"', html)
        self.assertIn('הערה קיימת', html)
        self.assertNotIn('name="areas-0-DELETE"', html)
        self.assertNotIn('הוספת מין באזור', html)
        # save the form as the browser sends it, with a new English note for the first area
        response = self.client.get(url)
        data = {}
        form = response.context['adminform'].form
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                data[name] = [getattr(v, 'pk', v) for v in value]
            elif hasattr(value, 'pk'):
                data[name] = value.pk
            elif isinstance(value, bool):
                if value:
                    data[name] = 'on'
            else:
                data[name] = value
        formset = response.context['inline_admin_formsets'][0].formset
        data.update({f'{formset.prefix}-{k}': v for k, v in formset.management_form.initial.items()})
        for i, area_form in enumerate(formset.forms):
            data[f'{formset.prefix}-{i}-id'] = area_form.instance.pk
            data[f'{formset.prefix}-{i}-species'] = self.ocellata.pk
            data[f'{formset.prefix}-{i}-note_he'] = area_form.instance.note_he
            data[f'{formset.prefix}-{i}-note_en'] = 'New note' if area_form.instance.pk == self.ocellata_eilat.pk else ''
        data['_save'] = 'שמירה'
        saved = self.client.post(url, data)
        self.assertEqual(saved.status_code, 302, getattr(saved, 'context', None) and saved.context.get('errors'))
        self.ocellata_eilat.refresh_from_db()
        self.assertEqual((self.ocellata_eilat.note_he, self.ocellata_eilat.note_en), ('הערה קיימת', 'New note'))


class HomePageArticlesTests(ArticleFixture):
    def test_only_articles_ticked_for_the_home_page_are_shown_in_both_languages(self):
        self.make_article('home', 'מאמר לדף הבית', 'Home article', he=True, en=True, show_on_home=True)
        self.make_article('hidden', 'מאמר נסתר', 'Hidden article', he=True)
        html = self.page('/')
        self.assertIn('data-home-section="articles"', html)
        self.assertIn('href="/articles/home/he.pdf"', html)
        self.assertIn('Home article', html)                  # the English version waits in the language-button data
        self.assertNotIn('מאמר נסתר', html)
        self.assertIn('href="/articles/home/en.pdf"', self.page('/?lang=en'))

    def test_no_section_when_none_is_ticked(self):
        self.make_article('hidden', title_en='Hidden')
        self.assertNotIn('data-home-section="articles"', self.page('/'))


class ObservationCountWordingTests(TestCase):
    def test_one_observation_in_both_languages(self):
        self.assertIn('תצפית אחת – ישראל.', seo_text.species_description('X y', '', '', '', 1, 'ישראל', 'he'))
        self.assertIn('2 תצפיות – ישראל.', seo_text.species_description('X y', '', '', '', 2, 'ישראל', 'he'))
        self.assertIn('1 observation in Israel.', seo_text.species_description('X y', '', '', '', 1, 'Israel', 'en'))
        self.assertIn('2 observations in Israel.', seo_text.species_description('X y', '', '', '', 2, 'Israel', 'en'))


class MoveOldPdfsIntoTheLibraryMigrationTests(MediaMixin, TransactionTestCase):
    """Migration 0077: each old article_pdf becomes one library article picked by the rows that used it."""

    def setUp(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        self.use_temp_media()
        self.executor = MigrationExecutor(connection)
        self.latest = self.executor.loader.graph.leaf_nodes('observations')
        self.executor.migrate([('observations', '0076_articles_library')])
        self.addCleanup(self.forward_to_latest)

    def forward_to_latest(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        MigrationExecutor(connection).migrate(self.latest)

    def test_old_pdfs_become_shared_articles_and_the_notes_are_filled(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        old = self.executor.loader.project_state([('observations', '0076_articles_library')]).apps
        Family, Genus = old.get_model('observations', 'TaxonFamily'), old.get_model('observations', 'TaxonGenus')
        Species_, Country_, Sea_, Area = (old.get_model('observations', m) for m in ('Species', 'Country', 'Sea', 'SpeciesArea'))
        Family.objects.create(name='Phyllidiidae', article_pdf='articles/families/zookeys-1006-001.pdf')
        Family.objects.create(name='Dorididae', article_pdf='articles/families/zookeys-1006-001.pdf')
        Genus.objects.create(name='Coryphellina', article_pdf='articles/genera/Coryphellina.pdf')
        Genus.objects.create(name='Hypselodoris')
        country, sea = Country_.objects.create(name='ישראל'), Sea_.objects.create(name='ים סוף')
        species = Species_.objects.create(scientific_name='Phyllidia ocellata')
        Area.objects.create(species=species, country=country, sea=sea, slug='phyllidia-ocellata-israel-red-sea-gulf-of-aqaba')
        Area.objects.create(species=Species_.objects.create(scientific_name='Phyllidia undula'), country=country, sea=sea,
                            slug='phyllidia-undula-israel-red-sea-gulf-of-aqaba', note_he='קיימת', note_en='Kept')
        MigrationExecutor(connection).migrate([('observations', '0077_article_pdfs_into_library')])
        self.forward_to_latest()
        self.assertEqual(sorted(Article.objects.values_list('slug', 'pdf_en')),
                         [('coryphellina', 'articles/genera/Coryphellina.pdf'), ('zookeys-1006-001', 'articles/families/zookeys-1006-001.pdf')])
        shared = Article.objects.get(slug='zookeys-1006-001')
        self.assertEqual(sorted(f.name for f in shared.families.all()), ['Dorididae', 'Phyllidiidae'])
        self.assertEqual(list(TaxonGenus.objects.get(name='Coryphellina').articles.values_list('slug', flat=True)), ['coryphellina'])
        self.assertFalse(TaxonGenus.objects.get(name='Hypselodoris').articles.exists())
        ocellata = SpeciesArea.objects.get(slug='phyllidia-ocellata-israel-red-sea-gulf-of-aqaba')
        self.assertTrue(ocellata.note_he.startswith('הזיהוי אינו ודאי: ייתכן שזהו מופע של Phyllidia undula'))
        self.assertTrue(ocellata.note_en.startswith('Identification uncertain'))
        undula = SpeciesArea.objects.get(slug='phyllidia-undula-israel-red-sea-gulf-of-aqaba')
        self.assertEqual((undula.note_he, undula.note_en), ('קיימת', 'Kept'))      # a note already written is left alone


class ObservationNoteTests(ArticleFixture):
    """A note on one observation (not the species, not the area), written by a manager and shown with it."""

    def setUp(self):
        super().setUp()
        self.eilat_sample = Sample.objects.get(species=self.ocellata, trip=self.eilat_trip)

    def test_the_note_is_shown_with_its_observation_with_names_in_italics(self):
        self.eilat_sample.note_he = 'זוהה כ־P. cf. ocellata; ייתכן שזו Phyllidia undula.'
        self.eilat_sample.note_en = 'Identified as P. cf. ocellata; possibly Phyllidia undula.'
        self.eilat_sample.save()
        html = self.page(f'/species/{self.ocellata_eilat.slug}/')
        self.assertIn('<p class="observation-note" role="note">זוהה כ־<i>P.</i> cf. <i>ocellata</i>; ייתכן שזו <i>Phyllidia undula</i>.</p>', html)
        english = self.page(f'/species/{self.ocellata_eilat.slug}/?lang=en')
        self.assertIn('Identified as <i>P.</i> cf. <i>ocellata</i>; possibly <i>Phyllidia undula</i>.', english)
        self.assertNotIn('זוהה כ', english)
        self.assertNotIn('class="observation-note"', self.page(f'/species/{self.ocellata_solomons.slug}/'))

    def test_a_note_in_one_language_is_shown_in_both(self):
        self.eilat_sample.note_he = 'הערה בעברית בלבד'
        self.eilat_sample.save()
        self.assertIn('הערה בעברית בלבד', self.page(f'/species/{self.ocellata_eilat.slug}/?lang=en'))

    def test_the_note_of_a_further_observation_is_shown_on_its_card(self):
        second = Sample(owner=self.owner, trip=DiveTrip.objects.create(title='אילת 2', year=2018, country=self.eilat_trip.country,
                                                                    region=self.eilat_trip.region),
                        species=self.ocellata, video_url='https://youtu.be/ddddddddddd', note_he='הערה לתצפית השנייה')
        second.save_reviewed()
        html = self.page(f'/species/{self.ocellata_eilat.slug}/')
        card = html.split(f'id="obs-{second.pk}"')[1].split('</article>')[0]
        self.assertIn('<p class="observation-note" role="note">הערה לתצפית השנייה</p>', card)

    def test_managers_write_the_note_on_the_observation_form_and_members_do_not_see_it(self):
        self.client.force_login(self.owner)
        html = self.page(f'/observations/{self.eilat_sample.pk}/edit/')
        self.assertIn('name="note_he"', html)
        self.assertIn('name="note_en"', html)
        member = User.objects.create_user('member', password='x')
        self.eilat_sample.owner = member
        self.eilat_sample.save()
        self.client.force_login(member)
        self.assertNotIn('name="note_he"', self.page(f'/observations/{self.eilat_sample.pk}/edit/'))

    def test_the_note_is_in_the_admin_observation_form(self):
        self.client.force_login(self.owner)
        self.assertIn('name="note_he"', self.page(f'/admin/observations/sample/{self.eilat_sample.pk}/change/'))


class UnneededArticleFilesTests(MediaMixin, TestCase):
    """Like the image manager's redundant images: what is no longer needed is deleted from the article-files page."""

    def setUp(self):
        import os
        from django.conf import settings
        self.use_temp_media()
        self.client.force_login(User.objects.create_superuser('boss', password='x'))
        self.used = self.make_article('used', title_en='Used', show_on_home=True)
        self.root = settings.MEDIA_ROOT
        os.makedirs(os.path.join(self.root, 'articles'), exist_ok=True)
        self.orphans = ['articles/draft.pdf', 'articles/draft_he.html', 'articles/old.pdf']
        for name in self.orphans:
            with open(os.path.join(self.root, name), 'wb') as f:
                f.write(b'<script>alert(1)</script>' if name.endswith('.html') else PDF)

    def exists(self, name):
        import os
        return os.path.exists(os.path.join(self.root, name))

    def test_leftover_html_drafts_are_listed_and_opened_as_plain_text(self):
        page = self.client.get('/admin/article-files/').content.decode()
        self.assertIn('articles/draft_he.html', page)
        self.assertIn('3 מהם יתומים', page)
        opened = self.client.get('/admin/article-files/open/', {'name': 'articles/draft_he.html'})
        self.assertEqual(opened['Content-Type'], 'text/plain; charset=utf-8')

    def test_all_selected_orphans_are_deleted_at_once_and_a_file_in_use_never(self):
        page = self.client.get('/admin/article-files/').content.decode()
        self.assertIn('בחירת כל הקבצים המיותרים', page)
        self.assertEqual(page.count('class="orphan-box"'), 3)
        response = self.client.post('/admin/article-files/delete/', {'names': self.orphans + [self.used.pdf_en.name]}, follow=True)
        for name in self.orphans:
            self.assertFalse(self.exists(name), name)
        self.assertTrue(self.exists(self.used.pdf_en.name))
        self.assertContains(response, 'נמחקו 3 קבצים')
        self.assertContains(response, 'לא נמחק')

    def test_the_row_button_deletes_only_its_own_file(self):
        self.client.post('/admin/article-files/delete/', {'name': 'articles/old.pdf', 'names': ['articles/draft.pdf']})
        self.assertFalse(self.exists('articles/old.pdf'))
        self.assertTrue(self.exists('articles/draft.pdf'))

    def test_articles_no_page_shows_are_listed_and_deleted_with_their_files(self):
        unused = self.make_article('unused', title_en='Unused paper')
        picked = self.make_article('picked', title_en='Picked paper')
        TaxonFamily.objects.create(name='Phyllidiidae').articles.add(picked)
        page = self.client.get('/admin/article-files/').content.decode()
        section = page.split('מאמרים שאינם מוצגים באף עמוד')[1]
        self.assertIn('Unused paper', section)
        self.assertNotIn('Picked paper', section)
        self.assertNotIn('>Used<', section)                 # on the home page: in use
        pdf = unused.pdf_en.name
        response = self.client.post('/admin/article-files/delete-articles/', {'articles': [unused.pk, picked.pk, self.used.pk]}, follow=True)
        self.assertContains(response, 'נמחקו 1 מאמרים')
        self.assertEqual(sorted(Article.objects.values_list('slug', flat=True)), ['picked', 'used'])
        self.assertFalse(self.exists(pdf))

    def test_deleting_an_article_in_the_admin_deletes_its_files(self):
        article = self.make_article('gone', title_en='Gone')
        pdf = article.pdf_en.name
        self.client.post(f'/admin/observations/article/{article.pk}/delete/', {'post': 'yes'})
        self.assertFalse(Article.objects.filter(pk=article.pk).exists())
        self.assertFalse(self.exists(pdf))


class ObservationNoteLinksAndMoveTests(ArticleFixture):
    NOTE_HE = 'הזיהוי אינו ודאי: ייתכן שזהו מופע של Phyllidia undula, שתועד באותו אתר — ראו מאמר.'
    NOTE_EN = 'Identification uncertain: this may be a form of Phyllidia undula, recorded at the same site — see article.'

    def move(self):
        import importlib
        from django.apps import apps as live_apps
        importlib.import_module('observations.migrations.0081_move_eilat_ocellata_note_to_observation').forwards(live_apps, None)

    def eilat(self):
        area = SpeciesArea.objects.get(pk=self.ocellata_eilat.pk)
        return area, Sample.objects.get(pk=area.defining_sample_id)

    def prepare(self, slug='phyllidia-ocellata-israel-red-sea-gulf-of-aqaba'):
        SpeciesArea.objects.filter(pk=self.ocellata_eilat.pk).update(slug=slug, note_he=self.NOTE_HE, note_en=self.NOTE_EN)

    def test_the_eilat_note_moves_from_the_page_to_its_observation(self):
        self.prepare()
        self.move()
        area, sample = self.eilat()
        self.assertEqual((area.note_he, area.note_en), ('', ''))
        self.assertEqual((sample.note_he, sample.note_en), (self.NOTE_HE, self.NOTE_EN))
        self.ocellata.articles.add(self.make_article('complex', title_he='מאמר', he=True, en=False))
        html = self.page(f'/species/{area.slug}/?lang=he')
        self.assertIn('<p class="observation-note" role="note">הזיהוי אינו ודאי: ייתכן שזהו מופע של <i>Phyllidia undula</i>, '
                      'שתועד באותו אתר — <a href="/articles/complex/he.pdf">ראו מאמר</a>.</p>', html)
        self.assertNotIn('class="species-note"', html)

    def test_an_edited_note_or_an_observation_with_its_own_note_is_left_alone(self):
        self.prepare()
        Sample.objects.filter(pk=self.ocellata_eilat.defining_sample_id).update(note_he='קיימת')
        self.move()
        area, sample = self.eilat()
        self.assertEqual((area.note_he, sample.note_he), (self.NOTE_HE, 'קיימת'))
        Sample.objects.filter(pk=sample.pk).update(note_he='')
        SpeciesArea.objects.filter(pk=area.pk).update(note_he='נוסח שנערך')
        self.move()
        area, sample = self.eilat()
        self.assertEqual((area.note_he, sample.note_he), ('נוסח שנערך', ''))


class NotesTravelWithTableTransferTests(ArticleFixture):
    def setUp(self):
        super().setUp()
        patcher = __import__('unittest.mock', fromlist=['patch']).patch(
            'observations.table_transfer.create_backup', return_value=__import__('pathlib').Path('test.sqlite3'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sample = Sample.objects.get(species=self.ocellata, trip=self.eilat_trip)

    def transfer(self, doc):
        from .table_transfer import apply, fingerprint
        apply(doc, fingerprint())

    def test_the_observation_note_is_exported_and_imported(self):
        from .table_transfer import export_table, plan
        self.sample.note_he, self.sample.note_en = 'הערה', 'Note'
        self.sample.save()
        doc = export_table('samples')
        row = next(r for r in doc['rows'] if r['transfer_id'] == str(self.sample.transfer_id))
        self.assertEqual((row['note_he'], row['note_en']), ('הערה', 'Note'))
        row['note_he'] = 'הערה מעודכנת'
        item = next(i for i in plan(doc) if i['object'] and i['object'].pk == self.sample.pk)
        self.assertEqual(item['action'], 'update')
        self.assertIn('הערה לתצפית (עברית)', [c['field'] for c in item['changes']])
        self.transfer(doc)
        self.sample.refresh_from_db()
        self.assertEqual((self.sample.note_he, self.sample.note_en), ('הערה מעודכנת', 'Note'))

    def test_an_older_samples_file_without_notes_keeps_the_target_notes(self):
        from .table_transfer import export_table, plan
        doc = export_table('samples')
        for row in doc['rows']:
            del row['note_he'], row['note_en']
        self.sample.note_he = 'הערה ביעד'
        self.sample.save()
        self.assertTrue(all(i['action'] == 'same' for i in plan(doc)))
        self.transfer(doc)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.note_he, 'הערה ביעד')

    def test_the_page_note_travels_with_the_species_areas_and_an_older_file_keeps_it(self):
        from .table_transfer import export_table, plan
        self.undula_eilat.note_he = 'הערה לעמוד'
        self.undula_eilat.save()
        doc = export_table('speciesareas')
        row = next(r for r in doc['rows'] if r['species'] == 'Phyllidia undula')
        self.assertEqual(row['note_he'], 'הערה לעמוד')
        row['note_en'] = 'Page note'
        self.transfer(doc)
        self.undula_eilat.refresh_from_db()
        self.assertEqual((self.undula_eilat.note_he, self.undula_eilat.note_en), ('הערה לעמוד', 'Page note'))
        old = export_table('speciesareas')
        for r in old['rows']:
            del r['note_he'], r['note_en']
        self.assertTrue(all(i['action'] == 'same' for i in plan(old)))
        self.transfer(old)
        self.undula_eilat.refresh_from_db()
        self.assertEqual((self.undula_eilat.note_he, self.undula_eilat.note_en), ('הערה לעמוד', 'Page note'))


class ArticleFilesLinkTests(TestCase):
    def test_superusers_reach_the_article_files_page_from_the_site_and_others_do_not_see_it(self):
        boss = User.objects.create_superuser('boss', password='x')
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(boss)
        html = self.client.get('/observations/trips/').content.decode()
        self.assertIn('href="/admin/article-files/"', html)
        self.assertIn('ניהול קבצי מאמרים', html)
        self.assertIn('Article files', self.client.get('/observations/trips/?lang=en').content.decode())
        self.assertIn('מחיקת קבצים ומאמרים מיותרים', self.client.get('/admin/').content.decode())
        self.client.force_login(staff)
        self.assertNotIn('href="/admin/article-files/"', self.client.get('/observations/trips/').content.decode())


class ArticleTransferTests(ArticleFixture):
    """Moving articles between the environments like images: export a list, compare it on the other side,
    download the chosen articles as ordinary files and upload them there."""

    def setUp(self):
        super().setUp()
        from unittest.mock import patch
        from pathlib import Path as _Path
        patcher = patch('observations.table_transfer.create_backup', return_value=_Path('test.sqlite3'))
        self.backup = patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.owner)
        self.article = self.make_article('complex', 'מאמר', 'Paper', he=True, en=True, source='Liebes 2026')
        self.ocellata.articles.add(self.article)
        self.undula.articles.add(self.article)
        self.genus.articles.add(self.article)
        self.eilat_trip.code = 'J17'; self.eilat_trip.save()
        self.eilat_trip.articles.add(self.article)

    def manifest(self):
        import json
        response = self.client.post('/admin/article-files/', {'action': 'export_manifest'})
        self.assertIn('seaslugs-articles-local.json', response['Content-Disposition'])
        return json.loads(response.content)

    def compare(self, manifest):
        import io, json
        upload = io.BytesIO(json.dumps(manifest).encode()); upload.name = 'other.json'
        return self.client.post('/admin/article-files/', {'action': 'compare_manifest', 'manifest': upload})

    def download(self, part):
        response = self.client.get('/admin/article-files/transfer-file/', {'article': 'complex', 'part': part})
        self.assertEqual(response.status_code, 200)
        return response

    def as_upload(self, response):
        from django.core.files.uploadedfile import SimpleUploadedFile
        name = response['Content-Disposition'].split('filename="')[1].rstrip('"')
        body = b''.join(response.streaming_content) if response.streaming else response.content
        return SimpleUploadedFile(name, body)

    def test_the_list_holds_details_fingerprints_and_pages_by_name_not_ids(self):
        manifest = self.manifest()
        self.assertEqual(manifest['format'], 'seaslugs-article-manifest-v1')
        entry = manifest['articles'][0]
        self.assertEqual((entry['slug'], entry['title_he'], entry['source']), ('complex', 'מאמר', 'Liebes 2026'))
        self.assertEqual(len(entry['files']['he'][0]), 64)
        self.assertEqual(entry['pages']['species'], ['Phyllidia ocellata', 'Phyllidia undula'])
        self.assertEqual(entry['pages']['genera'], ['Phyllidia'])
        self.assertEqual(entry['pages']['trips'], ['J17'])

    def test_the_comparison_lists_missing_extra_and_different_articles(self):
        manifest = self.manifest()
        other = self.make_article('only-here', title_en='Only here')
        theirs = manifest['articles'][0]
        theirs['title_en'] = 'Paper, revised'
        theirs['files']['en'] = ['0' * 64, 1, 10]
        theirs['pages']['species'] = ['Phyllidia ocellata']
        manifest['articles'].append(dict(theirs, slug='only-there', title_he='רק שם'))
        page = self.compare(manifest).content.decode()
        missing = page.split('חסרים כאן, קיימים בסביבה השנייה')[1].split('<h3>')[0]
        self.assertIn('רק שם', missing)
        self.assertIn('Only here', page.split('קיימים רק כאן, חסרים בסביבה השנייה')[1].split('<h3>')[0])
        different = page.split('קיימים בשתי הסביבות עם הבדלים')[1].split('<h3>')[0]
        self.assertIn('כותרת (אנגלית)', different)
        self.assertIn('PDF באנגלית: תוכן שונה — החדש יותר כאן', different)
        self.assertIn('מינים: רק כאן — <span dir="ltr">Phyllidia undula</span>', different)
        self.assertNotIn('PDF בעברית', different)
        self.assertIn('"only-here"', page)            # for the "select these for download" button
        other.delete()

    def test_an_identical_environment_has_nothing_to_move(self):
        page = self.compare(self.manifest()).content.decode()
        self.assertIn('אין מאמרים חסרים כאן', page)
        self.assertIn('אין מאמרים שקיימים רק כאן', page)
        self.assertIn('לכל המאמרים המשותפים אותם פרטים, קבצים ועמודים בשתי הסביבות', page)

    def test_a_bad_list_is_refused(self):
        self.assertIn('קובץ השוואת מאמרים לא תקין', self.compare({'format': 'other'}).content.decode())

    def test_downloaded_files_recreate_the_article_on_the_other_side(self):
        files = [self.as_upload(self.download(part)) for part in ('details', 'he', 'en')]
        self.assertEqual([f.name for f in files], ['complex.article.json', 'complex-he.pdf', 'complex-en.pdf'])
        self.article.delete()                               # the other environment does not have it yet
        response = self.client.post('/admin/article-files/', {'action': 'upload_articles', 'files': files}, follow=True)
        self.assertContains(response, 'הועברו 1 מאמרים')
        article = Article.objects.get(slug='complex')
        self.assertEqual((article.title_he, article.title_en, article.source), ('מאמר', 'Paper', 'Liebes 2026'))
        self.assertEqual(article.pdf_he.read(), PDF)
        self.assertEqual(sorted(s.scientific_name for s in article.species.all()), ['Phyllidia ocellata', 'Phyllidia undula'])
        self.assertEqual(list(article.genera.all()), [self.genus])
        self.assertEqual(list(article.trips.all()), [self.eilat_trip])
        self.backup.assert_called_once()

    def test_an_update_keeps_existing_pdfs_unless_replacing_is_confirmed_and_reports_unknown_pages(self):
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        document = json.loads(self.download('details').content)
        document['article']['title_en'] = 'Paper, revised'
        document['article']['pages']['species'].append('Nosuch species')
        document['article']['pages']['genera'] = []
        details = lambda: SimpleUploadedFile('complex.article.json', json.dumps(document).encode())
        new_pdf = lambda: SimpleUploadedFile('complex-en.pdf', b'%PDF-1.4 new version')
        response = self.client.post('/admin/article-files/', {'action': 'upload_articles', 'files': [details(), new_pdf()]}, follow=True)
        self.assertContains(response, 'לא הוחלף')
        self.assertContains(response, 'מין: Nosuch species')
        article = Article.objects.get(slug='complex')
        self.assertEqual(article.title_en, 'Paper, revised')
        self.assertEqual(article.pdf_en.read(), PDF)
        self.assertFalse(article.genera.exists())        # the pages are set to those listed
        self.client.post('/admin/article-files/', {'action': 'upload_articles', 'files': [details(), new_pdf()], 'replace': 'yes'})
        self.assertEqual(Article.objects.get(slug='complex').pdf_en.read(), b'%PDF-1.4 new version')

    def test_the_same_pdf_again_needs_no_confirmation(self):
        response = self.client.post('/admin/article-files/', {'action': 'upload_articles',
                                    'files': [self.as_upload(self.download('details')), self.as_upload(self.download('he'))]}, follow=True)
        self.assertNotContains(response, 'לא הוחלף')

    def test_wrong_files_are_refused(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        for files, message in (([SimpleUploadedFile('complex-he.pdf', PDF)], 'חסר קובץ פרטי המאמר'),
                               ([SimpleUploadedFile('notes.txt', b'x')], 'יש להעלות רק קבצים שהורדו מכאן'),
                               ([self.as_upload(self.download('details')), SimpleUploadedFile('complex-he.pdf', b'not a pdf')], 'אינו קובץ PDF'),
                               ([SimpleUploadedFile('x.article.json', b'{"format": "other"}')], 'קובץ פרטי מאמר לא תקין')):
            response = self.client.post('/admin/article-files/', {'action': 'upload_articles', 'files': files})
            self.assertContains(response, message)

    def test_the_page_offers_the_transfer_and_only_to_superusers(self):
        page = self.client.get('/admin/article-files/').content.decode()
        self.assertIn('העברת מאמרים בין הסביבות', page)
        self.assertIn('ייצוא רשימת מאמרים להשוואה', page)
        self.assertIn('class="article-box" value="complex"', page)
        self.assertIn('part=details', page)
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/admin/article-files/transfer-file/', {'article': 'complex', 'part': 'he'}).status_code, 403)
        self.assertEqual(self.client.post('/admin/article-files/', {'action': 'export_manifest'}).status_code, 403)


class DeleteAnyArticleTests(ArticleFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)
        self.article = self.make_article('complex', 'מאמר', 'Paper', he=True, en=True)
        self.ocellata.articles.add(self.article)
        self.genus.articles.add(self.article)
        self.files = [self.article.pdf_he.path, self.article.pdf_en.path]

    def assert_gone(self):
        import os
        self.assertFalse(Article.objects.filter(slug='complex').exists())
        for path in self.files:
            self.assertFalse(os.path.exists(path), path)
        self.assertFalse(self.ocellata.articles.exists())
        self.assertFalse(self.genus.articles.exists())
        self.assertNotIn('id="articles"', self.page(f'/species/{self.ocellata_eilat.slug}/'))

    def test_a_picked_article_is_deleted_from_the_article_files_page_with_its_files(self):
        page = self.page('/admin/article-files/')
        self.assertIn('name="slugs" class="article-box" value="complex"', page)
        response = self.client.post('/admin/article-files/delete-chosen-articles/', {'slugs': ['complex']}, follow=True)
        self.assertContains(response, 'נמחקו 1 מאמרים')
        self.assert_gone()

    def test_deleting_in_the_admin_does_the_same(self):
        page = self.page(f'/admin/observations/article/{self.article.pk}/delete/')
        self.assertIn('יוסר מכל העמודים', page)
        self.client.post(f'/admin/observations/article/{self.article.pk}/delete/', {'post': 'yes'})
        self.assert_gone()

    def test_the_admin_bulk_delete_action_also_deletes_the_files(self):
        self.client.post('/admin/observations/article/', {'action': 'delete_selected', '_selected_action': [self.article.pk], 'post': 'yes'})
        self.assert_gone()

    def test_only_superusers_delete(self):
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.post('/admin/article-files/delete-chosen-articles/', {'slugs': ['complex']}).status_code, 403)
        self.assertTrue(Article.objects.filter(slug='complex').exists())


HE_PAGE = '''<!DOCTYPE html><html lang="he"><head><style>body{}</style></head><body>
<article class="article-body" lang="he" dir="rtl">
<h1><i>Phyllidia ocellata</i> — מין אחד או קומפלקס של מינים?</h1>
<p class="subtitle">שונות מורפולוגית בין תצפיות</p>
<p class="byline">תצלומים ותצפיות: בעז ליבס | אוקטובר 2026</p>
<figure><img src="/observations/408/photo/" alt="x"><figcaption>איור 1. הפרט מאילת. זיהוי: <i>Phyllidia</i> cf. <i>ocellata</i>.</figcaption></figure>
<h2>מבוא</h2>
<p><i>Phyllidia ocellata</i> Cuvier, 1804 היא חשופית.</p>
<p>פסקה שנייה עם <a href="https://doi.org/10.1/x">קישור</a>.</p>
<div class="table-wrap"><table><thead><tr><th>מאפיין</th><th>אילת</th></tr></thead><tbody><tr><td>רקע</td><td>שחור ולבן</td></tr></tbody></table></div>
<div class="notice"><p><strong>הערה על רומבלון.</strong> הפרט דומה.</p></div>
<h3>שתי פרשנויות</h3>
<ul><li><strong>מופעים של מין אחד.</strong> לפי Brunckhorst.</li><li>שני מינים.</li></ul>
<h2>התצפיות באתר</h2>
<ul><li><a href="https://seaslugs.org.il/species/phyllidia-ocellata-israel-red-sea/?lang=he"><i>Phyllidia</i> cf. <i>ocellata</i> ממפרץ אילת (איור 1)</a></li></ul>
<h2>מקורות וקישורים</h2>
<ol class="refs"><li>Yonow, N. (1986). Red Sea Phyllidiidae. <em>J. Nat. Hist.</em> <a href="https://doi.org/10.1080/1">doi:10.1080/1</a></li></ol>
<p class="editorial">הערת עריכה.</p>
</article></body></html>'''
EN_PAGE = (HE_PAGE.replace('התצפיות באתר', 'Observations on the site').replace('ממפרץ אילת (איור 1)', 'from the Gulf of Aqaba (Figure 1)').replace('מקורות וקישורים', 'References and links')
           .replace('lang="he" dir="rtl"', 'lang="en" dir="ltr"')
           .replace('מין אחד או קומפלקס של מינים?', 'One Species or a Species Complex?')
           .replace('שונות מורפולוגית בין תצפיות', 'Morphological variation').replace('תצלומים ותצפיות: בעז ליבס | אוקטובר 2026', 'Photos: Boaz Liebes')
           .replace('איור 1. הפרט מאילת. זיהוי:', 'Figure 1. The Eilat animal. Identification:').replace('מבוא', 'Introduction')
           .replace('היא חשופית.', 'is a nudibranch.').replace('פסקה שנייה עם', 'A second paragraph with').replace('קישור', 'a link')
           .replace('מאפיין', 'Character').replace('אילת', 'Eilat').replace('רקע', 'Ground').replace('שחור ולבן', 'Black and white')
           .replace('הערה על רומבלון.', 'A note on Romblon.').replace('הפרט דומה.', 'The animal is similar.')
           .replace('שתי פרשנויות', 'Two interpretations').replace('מופעים של מין אחד.', 'Forms of one species.')
           .replace('לפי Brunckhorst.', 'After Brunckhorst.').replace('שני מינים.', 'Two species.')
           .replace('הערת עריכה.', 'Editorial note.'))


class WrittenArticleTests(ArticleFixture):
    """An article written on the site: sections in both languages, its own page, printing instead of a PDF."""

    def setUp(self):
        super().setUp()
        from .article_import import import_article
        self.sample = Sample.objects.get(species=self.ocellata, trip=self.eilat_trip)
        self.sample.image.save('eilat.jpg', ContentFile(b'\xff\xd8\xff jpeg'), save=False)
        Sample.objects.filter(pk=self.sample.pk).update(image=self.sample.image.name)
        self.sample.refresh_from_db()
        self.article = import_article(Article(slug='complex'), HE_PAGE, EN_PAGE, [self.sample])
        self.ocellata.articles.add(self.article)

    def test_the_two_pages_become_one_bilingual_article(self):
        a = Article.objects.get(slug='complex')
        self.assertEqual(a.title_he, 'Phyllidia ocellata — מין אחד או קומפלקס של מינים?')
        self.assertEqual((a.subtitle_en, a.byline_he), ('Morphological variation', 'תצלומים ותצפיות: בעז ליבס | אוקטובר 2026'))
        self.assertEqual([b.kind for b in a.blocks.all()],
                         ['figure', 'heading', 'paragraph', 'table', 'notice', 'subheading', 'list', 'heading', 'list'])
        figure, heading, paragraph, table, notice, sub, lst, own_heading, own_list = a.blocks.all()
        # the article's own "observations on the site" list, kept as written; links to this site made relative
        self.assertEqual(own_heading.text_he, 'התצפיות באתר')
        self.assertEqual(own_list.text_en, '[*Phyllidia* cf. *ocellata* from the Gulf of Aqaba (Figure 1)](/species/phyllidia-ocellata-israel-red-sea/)')
        self.assertEqual(figure.sample, self.sample)
        self.assertEqual(figure.text_he, 'הפרט מאילת. זיהוי: *Phyllidia* cf. *ocellata*.')       # the number is the page's own
        self.assertEqual(paragraph.text_en, '*Phyllidia ocellata* Cuvier, 1804 is a nudibranch.\n\nA second paragraph with [a link](https://doi.org/10.1/x).')
        self.assertEqual(table.text_he, 'מאפיין | אילת\nרקע | שחור ולבן')
        self.assertEqual((notice.title_en, notice.text_en), ('A note on Romblon.', 'The animal is similar.'))
        self.assertEqual(lst.text_en, '**Forms of one species.** After Brunckhorst.\nTwo species.')
        self.assertEqual([r.text for r in a.references.all()],
                         ['Yonow, N. (1986). Red Sea Phyllidiidae. *J. Nat. Hist.* [doi:10.1080/1](https://doi.org/10.1080/1)'])
        self.assertEqual(a.editorial_he, 'הערת עריכה.')
        self.assertTrue(a.is_written)

    def test_the_page_shows_one_language_with_numbered_figures_and_the_observations_list(self):
        html = self.page('/articles/complex/?lang=he')
        self.assertIn('<h1><i>Phyllidia ocellata</i> — מין אחד או קומפלקס של מינים?</h1>', html)
        self.assertIn(f'<img src="/observations/{self.sample.pk}/photo/"', html)
        self.assertIn('<span class="figure-number">איור 1.</span> הפרט מאילת. זיהוי: <i>Phyllidia</i> cf. <i>ocellata</i>.', html)
        self.assertIn('<p><i>Phyllidia ocellata</i> Cuvier, 1804 היא חשופית.</p><p>פסקה שנייה עם <a href="https://doi.org/10.1/x" target="_blank" rel="noopener">קישור</a>.</p>', html)
        self.assertIn('<th>מאפיין</th><th>אילת</th>', html)
        self.assertIn('<div class="notice"><p><strong>הערה על רומבלון.</strong> הפרט דומה.</p></div>', html)
        self.assertIn('<li><strong>מופעים של מין אחד.</strong> לפי Brunckhorst.</li>', html)
        self.assertIn('<h2>התצפיות באתר</h2>', html)
        self.assertIn('<a href="/species/phyllidia-ocellata-israel-red-sea/"><i>Phyllidia</i> cf. <i>ocellata</i> ממפרץ אילת (איור 1)</a>', html)
        self.assertNotIn('<h2>תצפיות באתר</h2>', html)          # no automatic list besides the article's own
        self.assertIn('<ol class="refs" dir="ltr" lang="en">', html)
        self.assertIn('<h2>מקורות וקישורים</h2>', html)
        self.assertIn('הדפסה / שמירה כ־PDF', html)
        self.assertIn('@media print', html)
        self.assertNotIn('One Species', html)
        english = self.page('/articles/complex/?lang=en')
        self.assertIn('<span class="figure-number">Figure 1.</span> The Eilat animal.', english)
        self.assertIn('Print / save as PDF', english)
        self.assertIn('<a href="/species/phyllidia-ocellata-israel-red-sea/?lang=en">', english)
        self.assertNotIn('מבוא', english)

    def test_an_untranslated_section_says_so_in_the_page_language(self):
        block = self.article.blocks.get(kind='subheading')
        block.text_en = ''
        block.save()
        english = self.page('/articles/complex/?lang=en')
        self.assertIn('This section has not been translated into English yet.', english)
        self.assertIn('Some sections have not been translated yet.', english)
        self.assertNotIn('שתי פרשנויות', english)

    def test_links_to_the_article_lead_to_its_page_with_the_first_figure_as_preview(self):
        species_page = self.page(f'/species/{self.ocellata_eilat.slug}/?lang=he')
        self.assertIn('<a class="article-thumb" href="/articles/complex/"', species_page)
        self.assertIn(f'<img src="/observations/{self.sample.pk}/photo/" alt="" width="64"', species_page)
        self.assertIn('href="/articles/complex/"', self.page('/articles/?lang=he'))
        self.assertIn('קריאת המאמר', self.page('/articles/?lang=he'))
        self.assertIn('href="/articles/complex/?lang=en"', self.page('/articles/?lang=en'))

    def test_a_pdf_article_page_leads_to_its_pdf(self):
        self.make_article('paper', title_en='Paper')
        self.assertRedirects(self.client.get('/articles/paper/'), '/articles/paper/en.pdf', fetch_redirect_response=False)

    def test_inline_markup(self):
        from .article_render import inline, plain
        html = inline('**Bold** and *J. Nat. Hist.* with Phyllidia undula and [a link](https://x.org/a) <b>', set([('Phyllidia', 'undula')]))
        self.assertEqual(html, '<strong>Bold</strong> and <i>J. Nat. Hist.</i> with <i>Phyllidia undula</i> and '
                               '<a href="https://x.org/a" target="_blank" rel="noopener">a link</a> &lt;b&gt;')
        self.assertEqual(plain('**a** *b* [c](/d)'), 'a b c')

    def test_the_admin_edits_the_sections_and_requires_content(self):
        self.client.force_login(self.owner)
        html = self.page(f'/admin/observations/article/{self.article.pk}/change/')
        self.assertIn('name="blocks-0-text_he"', html)
        self.assertIn('name="references-0-text"', html)
        self.assertIn('מאמר שנכתב באתר', html)
        response = self.client.post('/admin/observations/article/add/', {
            'title_he': 'ריק', 'slug': 'empty', 'published_on': '2026-10-23',
            'blocks-TOTAL_FORMS': '0', 'blocks-INITIAL_FORMS': '0', 'references-TOTAL_FORMS': '0', 'references-INITIAL_FORMS': '0'})
        self.assertContains(response, 'למאמר צריך תוכן')
        response = self.client.post('/admin/observations/article/add/', {
            'title_he': 'מאמר', 'slug': 'written', 'published_on': '2026-10-23',
            'blocks-TOTAL_FORMS': '1', 'blocks-INITIAL_FORMS': '0', 'blocks-0-position': '10', 'blocks-0-kind': 'paragraph',
            'blocks-0-text_he': 'שלום', 'references-TOTAL_FORMS': '0', 'references-INITIAL_FORMS': '0'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('<p>שלום</p>', self.page('/articles/written/'))

    def test_the_transfer_carries_the_sections_with_figures_by_observation(self):
        import json
        from unittest.mock import patch
        from pathlib import Path as _Path
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.owner)
        details = self.client.get('/admin/article-files/transfer-file/', {'article': 'complex', 'part': 'details'}).content
        content = json.loads(details)['article']['content']
        self.assertEqual(content['blocks'][0]['sample'], str(self.sample.transfer_id))
        self.article.delete()
        with patch('observations.table_transfer.create_backup', return_value=_Path('t.sqlite3')):
            response = self.client.post('/admin/article-files/', {'action': 'upload_articles',
                                        'files': [SimpleUploadedFile('complex.article.json', details)]}, follow=True)
        self.assertContains(response, 'הועברו 1 מאמרים')
        article = Article.objects.get(slug='complex')
        self.assertEqual(article.blocks.count(), 9)
        self.assertEqual(article.blocks.first().sample, self.sample)
        self.assertEqual(article.references.count(), 1)
        self.assertEqual(article.subtitle_he, 'שונות מורפולוגית בין תצפיות')

    def test_the_import_command(self):
        import tempfile, os
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder:
            he, en = os.path.join(folder, 'he.html'), os.path.join(folder, 'en.html')
            open(he, 'w', encoding='utf-8').write(HE_PAGE); open(en, 'w', encoding='utf-8').write(EN_PAGE)
            call_command('import_article_html', 'complex', he, en, figures=str(self.sample.pk))
            from django.core.management.base import CommandError
            with self.assertRaisesMessage(CommandError, 'איורים'):
                call_command('import_article_html', 'other', he, en, figures='')
        self.assertEqual(Article.objects.get(slug='complex').blocks.count(), 9)


class AutomaticObservationsListTests(ArticleFixture):
    def test_an_article_without_its_own_list_gets_one_built_from_its_figures(self):
        from .article_import import import_article
        sample = Sample.objects.get(species=self.ocellata, trip=self.eilat_trip)
        sample.image.save('e.jpg', ContentFile(b'\xff\xd8\xff jpeg'), save=False)
        Sample.objects.filter(pk=sample.pk).update(image=sample.image.name)
        he = HE_PAGE.split('<h2>התצפיות באתר</h2>')[0] + '</article></body></html>'
        en = EN_PAGE.split('<h2>Observations on the site</h2>')[0] + '</article></body></html>'
        import_article(Article(slug='plain'), he, en, [Sample.objects.get(pk=sample.pk)])
        html = self.page('/articles/plain/?lang=he')
        self.assertIn('<h2>תצפיות באתר</h2>', html)
        self.assertIn(f'href="/species/{self.ocellata_eilat.slug}/"', html)


class ArticleManagerButtonsTests(ArticleFixture):
    def setUp(self):
        super().setUp()
        from .article_import import import_article
        self.paper = self.make_article('paper', title_he='מאמר')
        self.written = import_article(Article(slug='written'), HE_PAGE, EN_PAGE, [Sample.objects.get(species=self.ocellata, trip=self.eilat_trip)])

    def test_managers_get_add_and_edit_buttons(self):
        self.client.force_login(self.owner)
        html = self.page('/articles/?lang=he')
        self.assertIn('href="/admin/observations/article/add/"', html)
        self.assertIn('הוספת מאמר', html)
        self.assertIn(f'href="/admin/observations/article/{self.paper.pk}/change/"', html)
        self.assertIn(f'href="/admin/observations/article/{self.written.pk}/change/"', html)
        self.assertIn('Edit article', self.page('/articles/?lang=en'))
        self.assertIn(f'href="/admin/observations/article/{self.written.pk}/change/"', self.page('/articles/written/'))

    def test_visitors_and_members_do_not(self):
        for user in (None, User.objects.create_user('member', password='x'), User.objects.create_user('staff', password='x', is_staff=True)):
            if user: self.client.force_login(user)
            html = self.page('/articles/?lang=he')
            self.assertNotIn('/admin/observations/article/', html)
            self.assertNotIn('עריכת מאמר', self.page('/articles/written/'))
