from django.contrib.auth.models import User
from django.test import TestCase
from .models import Country, Sea, Region, Species, Sample, DiveTrip, SpeciesArea


class SitemapTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name='Test species')
        sample = Sample(owner=self.owner, trip=self.trip, species=species, video_url='https://youtu.be/abcdefghijk')
        sample.save_reviewed()  # kind=species auto-publishes -- see Sample.save_reviewed
        self.area = SpeciesArea.objects.get(species=species)

    def test_sitemap_returns_200_with_xml_content(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertIn('xml', response['Content-Type'])

    def test_sitemap_includes_the_homepage_over_https_on_the_real_domain(self):
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('<loc>https://seaslugs.org.il/</loc>', content)

    def test_sitemap_includes_a_live_species_page_over_https_on_the_real_domain(self):
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(f'<loc>https://seaslugs.org.il/species/{self.area.slug}/</loc>', content)

    def test_sitemap_excludes_an_area_whose_defining_sample_is_not_published(self):
        # A SpeciesArea can exist (e.g. mid-curation) before its defining sample is actually
        # published -- species_page() 404s on that, so the sitemap must not link to it either.
        other_species = Species.objects.create(scientific_name='Unpublished species')
        pending = Sample(owner=self.owner, trip=self.trip, species=other_species,
                          video_url='https://youtu.be/22222222222')
        pending.save()  # plain .save(), not save_reviewed() -- stays pending, no auto-publish
        area = SpeciesArea.objects.create(species=other_species, country=self.trip.country,
                                           sea=self.trip.resolved_sea, defining_sample=pending)
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn(area.slug, content)

    def test_sitemap_excludes_an_area_with_no_sample_actually_matching_its_own_country_and_sea(self):
        # Regression for the real Romblon/Anilao bug this app just hit: a SpeciesArea's own
        # country+sea can drift out of sync with where its defining sample's trip actually is
        # (e.g. after a trip's region gets repointed) -- species_page() 404s when no sample
        # matches the area's own country+sea, so the sitemap must exclude that case too, even
        # though the defining sample itself is perfectly published.
        other_country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        other_species = Species.objects.create(scientific_name='Drifted species')
        area = SpeciesArea.objects.create(species=other_species, country=other_country,
                                           sea=self.trip.resolved_sea, defining_sample=None)
        # Give it a defining_sample that's published but belongs to a DIFFERENT country's trip
        # than the area itself claims -- exactly the mismatch that made species_page() 404.
        sample = Sample(owner=self.owner, trip=self.trip, species=other_species,
                         video_url='https://youtu.be/33333333333')
        sample.save_reviewed()
        area.defining_sample = sample
        area.save(update_fields=['defining_sample'])
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn(area.slug, content)

    def test_sitemap_never_links_admin_login_or_profile_pages(self):
        content = self.client.get('/sitemap.xml').content.decode()
        for path in ('/admin/', '/observations/login/', '/observations/'):
            self.assertNotIn(f'<loc>https://seaslugs.org.il{path}</loc>', content)
