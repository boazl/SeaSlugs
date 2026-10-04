import tempfile
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea, TaxonGenus, TaxonFamily, TaxonOrder


class GenusPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        self.country = Country.objects.create(name='ישראל', name_en='Israel')
        self.sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        self.region = Region.objects.create(name='אילת', name_en='Eilat', country=self.country, sea=self.sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=self.country, region=self.region)
        self.order = TaxonOrder.objects.create(name='Nudibranchia')
        self.family = TaxonFamily.objects.create(name='Chromodorididae', order=self.order)
        self.genus = TaxonGenus.objects.create(name='Chromodoris', family=self.family)
        self.species = Species.objects.create(scientific_name='Chromodoris annae', genus='Chromodoris')
        species_sample = Sample(owner=self.owner, trip=self.trip, species=self.species, video_url='https://youtu.be/abcdefghijk')
        species_sample.save_reviewed()  # kind=species auto-publishes -- see Sample.save_reviewed
        self.area = SpeciesArea.objects.get(species=self.species)
        self.genus_sample = Sample(owner=self.owner, kind=Sample.Kind.GENUS, genus='Chromodoris',
                                    trip=self.trip, video_url='https://youtu.be/11111111111')
        self.genus_sample.save_reviewed(actor=self.owner, approve=True)

    def test_genus_page_returns_200_and_lists_its_species(self):
        response = self.client.get(f'/genus/{self.genus.name}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chromodoris annae')
        self.assertContains(response, f'/species/{self.area.slug}/')

    def test_card_shows_the_observation_count_when_the_species_has_several(self):
        url = f'/genus/{self.genus.name}/'
        self.assertNotContains(self.client.get(url), 'count-badge" aria-hidden')      # one observation: no badge
        second = Sample(owner=self.owner, trip=self.trip, species=self.species, video_url='https://youtu.be/22222222222')
        second.save_reviewed()
        gone = Sample(owner=self.owner, trip=self.trip, species=self.species, video_url='https://youtu.be/33333333333')
        gone.save_reviewed(); gone.soft_delete(self.owner)                            # a deleted one is not counted
        response = self.client.get(url)
        self.assertContains(response, '<span class="count-badge" aria-hidden="true">2</span>')
        self.assertContains(response, '<span>2 תצפיות</span>')

    def test_species_page_shows_the_full_name_on_each_observation_that_differs(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        cf = Sample(owner=self.owner, trip=self.trip, species=self.species, identification_qualifier='cf.',
                    video_url='https://youtu.be/44444444444')
        cf.save_reviewed()
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertEqual(html.count('class="sample-name"'), 1)           # the plain observation would only repeat the h1
        self.assertIn('<i>Chromodoris</i> cf. <i>annae</i>', html)       # the qualifier is visible on that observation only
        self.assertEqual(html.count('cf. <i>annae</i>'), 1)

    def test_species_page_heading_is_italic_with_the_author_in_roman_and_no_name_in_the_breadcrumb(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn('<h1 dir="ltr"><i>Chromodoris annae</i> <span class="species-author">Bergh, 1877</span></h1>', html)
        start = html.index('class="breadcrumb"'); crumb = html[start:html.index('</nav>', start)]
        self.assertIn('Chromodoris</a>', crumb)               # the genus link stays
        self.assertNotIn('aria-current', crumb)               # the species name is not repeated there
        self.assertNotIn('annae', crumb)

    def test_observation_names_above_the_photos_are_italic_except_the_qualifier(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        Sample(owner=self.owner, trip=self.trip, species=self.species, identification_qualifier='cf.',
               video_url='https://youtu.be/55555555555').save_reviewed()
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn('<i>Chromodoris</i> cf. <i>annae</i> <span class="sample-author">Bergh, 1877</span>', html)
        self.assertEqual(html.count('class="sample-name"'), 1)
        self.assertNotIn('<i>Chromodoris annae</i> Bergh, 1877', html)   # a plain name is not repeated above its photo

    def test_species_page_heading_is_one_colour_and_small(self):
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn('.species-summary h1 .species-author{font-style:normal;color:inherit}', html)   # base.css paints every h1 span teal
        self.assertIn('font-size:24px', html.split('.species-summary h1{')[1].split('}')[0])
        # `.card h3{font-size:24px}` in styles.css would win over a bare `.sample-name`, so the rule carries the card
        self.assertIn('font-size:16px', html.split('.card h3.sample-name{')[1].split('}')[0])
        self.assertIn('display:inline-block;font-size:11px', html.split('.card h3.sample-name .sample-author{')[1].split('}')[0])

    def test_observation_name_sits_below_the_photo_with_a_small_author(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        Sample(owner=self.owner, trip=self.trip, species=self.species, identification_qualifier='cf.', life_stage='juv.',
               video_url='https://youtu.be/66666666666').save_reviewed()
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertLess(html.index('<img src', html.index('class="grid"')), html.index('class="sample-name"'))
        self.assertIn('<h3 class="sample-name" dir="ltr"><i>Chromodoris</i> cf. <i>annae</i> '
                      '<span class="sample-author">Bergh, 1877</span> juv.</h3>', html)

    def test_genus_page_cards_show_the_species_name_in_italics(self):
        self.species.species = 'annae'; self.species.save()
        self.assertContains(self.client.get(f'/genus/{self.genus.name}/'), '<i>Chromodoris annae</i>')

    def test_genus_page_404s_without_a_defining_sample(self):
        self.genus_sample.soft_delete(self.owner)  # only genus-kind sample -- see Sample.save
        self.genus.refresh_from_db()
        self.assertIsNone(self.genus.defining_sample_id)
        response = self.client.get(f'/genus/{self.genus.name}/')
        self.assertEqual(response.status_code, 404)

    def test_genus_page_404s_when_no_species_resolve_to_it(self):
        empty_genus = TaxonGenus.objects.create(name='Hypselodoris')
        sample = Sample(owner=self.owner, kind=Sample.Kind.GENUS, genus='Hypselodoris',
                         trip=self.trip, video_url='https://youtu.be/22222222222')
        sample.save_reviewed(actor=self.owner, approve=True)
        response = self.client.get(f'/genus/{empty_genus.name}/')
        self.assertEqual(response.status_code, 404)

    def test_genus_page_404s_for_an_unknown_genus_name(self):
        response = self.client.get('/genus/NoSuchGenus/')
        self.assertEqual(response.status_code, 404)

    def test_species_page_breadcrumb_links_to_the_genus_page(self):
        response = self.client.get(f'/species/{self.area.slug}/')
        self.assertContains(response, f'href="/genus/{self.genus.name}/"')

    def test_genus_article_streams_the_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=tmp):
                self.genus.article_pdf.save('article.pdf', ContentFile(b'%PDF-1.4 test'), save=True)
                response = self.client.get(f'/genus/{self.genus.name}/article.pdf')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_genus_article_404s_without_a_pdf(self):
        response = self.client.get(f'/genus/{self.genus.name}/article.pdf')
        self.assertEqual(response.status_code, 404)

    def test_sitemap_includes_a_live_genus_page(self):
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(f'<loc>https://seaslugs.org.il/genus/{self.genus.name}/</loc>', content)

    def test_sitemap_excludes_a_genus_with_no_defining_sample(self):
        empty_genus = TaxonGenus.objects.create(name='Hypselodoris')
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn(f'/genus/{empty_genus.name}/', content)

    def test_catalog_exposes_the_genus_name_for_the_gallery_panel_link(self):
        import json
        response = self.client.get('/catalog.js')
        data = json.loads(response.content.decode().split('=', 1)[1].strip().removesuffix(';'))
        entry = data['taxa']['genera'][str(self.genus.pk)]
        self.assertEqual(entry['name'], 'Chromodoris')
