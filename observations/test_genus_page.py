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
