import tempfile
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea, TaxonGenus, TaxonFamily, TaxonOrder

BASE = 'https://seaslugs.org.il'


class SeoFixture(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        self.order = TaxonOrder.objects.create(name='Nudibranchia')
        self.family = TaxonFamily.objects.create(name='Chromodorididae', order=self.order)
        self.genus = TaxonGenus.objects.create(name='Chromodoris', family=self.family)
        self.species = Species.objects.create(scientific_name='Chromodoris annae', genus='Chromodoris',
                                              name_he='חינניית אנה', description_he='חינניה כחולה עם פסים שחורים.')
        Sample(owner=self.owner, trip=self.trip, species=self.species,
               video_url='https://youtu.be/abcdefghijk').save_reviewed()
        self.area = SpeciesArea.objects.get(species=self.species)

    def page(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class ShareMetaTests(SeoFixture):
    def test_species_page_has_open_graph_tags_with_an_absolute_image(self):
        html = self.page(f'/species/{self.area.slug}/')
        self.assertIn('<meta property="og:title" content="Chromodoris annae — חינניית אנה">', html)
        self.assertIn('<meta property="og:description" content="חינניה כחולה עם פסים שחורים.">', html)
        self.assertIn('<meta property="og:image" content="https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg">', html)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', html)
        self.assertIn(f'<meta property="og:url" content="{BASE}/species/{self.area.slug}/">', html)

    def test_species_page_photo_becomes_an_absolute_https_og_image(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            from django.core.files.uploadedfile import SimpleUploadedFile
            from io import BytesIO
            from PIL import Image
            buf = BytesIO(); Image.new('RGB', (40, 30), 'blue').save(buf, 'JPEG')
            other = Species.objects.create(scientific_name='Hypselodoris infucata', genus='Hypselodoris')
            sample = Sample(owner=self.owner, trip=self.trip, species=other,
                            image=SimpleUploadedFile('a.jpg', buf.getvalue(), content_type='image/jpeg'))
            sample.save_reviewed()
            area = SpeciesArea.objects.get(species=other)
            html = self.page(f'/species/{area.slug}/')
            self.assertIn(f'<meta property="og:image" content="{BASE}/observations/{sample.pk}/photo/">', html)

    def test_canonical_and_hreflang_follow_the_page_language(self):
        url = f'/species/{self.area.slug}/'
        html = self.page(url)
        self.assertIn(f'<link rel="canonical" href="{BASE}{url}">', html)
        self.assertIn(f'<link rel="alternate" hreflang="en" href="{BASE}{url}?lang=en">', html)
        self.assertIn(f'<link rel="alternate" hreflang="x-default" href="{BASE}{url}">', html)
        self.assertIn('<meta property="og:locale" content="he_IL">', html)
        html_en = self.page(url + '?lang=en')
        self.assertIn(f'<link rel="canonical" href="{BASE}{url}?lang=en">', html_en)
        self.assertIn('<meta property="og:locale" content="en_US">', html_en)

    def test_genus_family_and_order_pages_have_share_tags(self):
        for url in (f'/genus/{self.genus.name}/', f'/family/{self.family.name}/', f'/order/{self.order.pk}/'):
            html = self.page(url)
            self.assertIn(f'<link rel="canonical" href="{BASE}{url}">', html)
            self.assertIn('<meta property="og:image" content="https://', html)

    def test_page_without_a_description_falls_back_to_the_generic_line(self):
        html = self.page(f'/genus/{self.genus.name}/')
        self.assertIn('<meta property="og:description" content="Chromodoris — תצפיות, תמונות ומידע', html)

    def test_gallery_home_has_share_tags_and_its_own_canonical_and_hreflang_per_language(self):
        html = self.page('/')
        self.assertIn(f'<link rel="canonical" href="{BASE}/">', html)
        self.assertIn(f'<meta property="og:image" content="{BASE}/intro-photo.jpg">', html)
        self.assertIn(f'<link rel="alternate" hreflang="he" href="{BASE}/">', html)
        self.assertIn(f'<link rel="alternate" hreflang="en" href="{BASE}/?lang=en">', html)
        self.assertIn(f'<link rel="alternate" hreflang="x-default" href="{BASE}/">', html)
        english = self.page('/?lang=en')
        self.assertIn(f'<link rel="canonical" href="{BASE}/?lang=en">', english)
        self.assertNotIn(f'<link rel="canonical" href="{BASE}/">', english)

    def test_dive_trips_page_has_share_tags(self):
        html = self.page('/observations/trips/')
        self.assertIn(f'<link rel="canonical" href="{BASE}/observations/trips/">', html)
        self.assertIn('<meta property="og:title" content="מסעות צלילה — SeaSlugs">', html)

    def test_search_console_tag_only_when_configured(self):
        url = f'/species/{self.area.slug}/'
        self.assertNotIn('google-site-verification', self.page(url))
        with override_settings(GOOGLE_SITE_VERIFICATION='abc123'):
            self.assertIn('<meta name="google-site-verification" content="abc123">', self.page(url))
            self.assertIn('<meta name="google-site-verification" content="abc123">', self.page('/'))


class RobotsAndSitemapTests(SeoFixture):
    def test_robots_txt_points_at_the_sitemap_and_blocks_admin(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        body = response.content.decode()
        self.assertIn('User-agent: *', body)
        self.assertIn('Disallow: /admin/', body)
        self.assertIn(f'Sitemap: {BASE}/sitemap.xml', body)

    def test_robots_txt_keeps_public_pages_and_photos_crawlable(self):
        rules = [line.split(': ', 1)[1] for line in self.client.get('/robots.txt').content.decode().splitlines()
                 if line.startswith('Disallow: ')]
        for path in ('/', '/species/x/', '/genus/x/', '/family/x/', '/order/1/', '/observations/trips/', '/observations/5/photo/'):
            for rule in rules:
                blocked = path == rule[:-1] if rule.endswith('$') else path.startswith(rule)
                self.assertFalse(blocked, f'{rule} blocks {path}')

    def test_sitemap_lists_live_family_and_order_pages(self):
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(f'<loc>{BASE}/family/Chromodorididae/</loc>', content)
        self.assertIn(f'<loc>{BASE}/order/{self.order.pk}/</loc>', content)

    def test_sitemap_skips_a_family_with_no_gallery_species(self):
        TaxonFamily.objects.create(name='Polyceridae', order=self.order)
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn('/family/Polyceridae/', content)
