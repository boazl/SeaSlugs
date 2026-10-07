from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, TaxonFamily, TaxonGenus, TaxonOrder


class TaxonOrderFilterTests(TestCase):
    """The order filter on the genus/family changelists: several TaxonOrder rows share a name
    (Nudibranchia/Cladobranchia x3), so each option also shows its Hebrew name and superfamilies;
    beside it, how many genera/families have species in the gallery, and (small) how many the
    reference table holds."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_superuser('manager', password='x')
        self.client.force_login(self.owner)
        self.aeolid = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='8', name_he='חשופיות אונות')
        self.dendro = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='7', name_he='חשופיות אילן')
        self.flab = TaxonFamily.objects.create(name='Flabellinidae', order=self.aeolid, superfamily='Fionoidea')
        TaxonFamily.objects.create(name='Facelinidae', order=self.aeolid, superfamily='Aeolidioidea')
        TaxonFamily.objects.create(name='Tethydidae', order=self.dendro, superfamily='Dendronotoidea')
        TaxonFamily.objects.create(name='Heroidae', order=self.dendro, superfamily='\\N')   # import artifact
        self.flabellina = TaxonGenus.objects.create(name='Flabellina', family=self.flab)
        TaxonGenus.objects.create(name='Edmundsella', family=self.flab)         # in the table, not in the gallery
        TaxonGenus.objects.create(name='Tethys', family=TaxonFamily.objects.get(name='Tethydidae'))

    def page(self, url):
        return self.client.get(url).content.decode()

    def put_in_gallery(self, genus, family):
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name=f'{genus} test', genus=genus, family=family)
        Sample(owner=self.owner, trip=trip, species=species, video_url='https://youtu.be/00000000001').save_reviewed()

    def test_genus_filter_tells_same_named_rows_apart(self):
        html = self.page('/admin/observations/taxongenus/')
        self.assertIn('Nudibranchia (Cladobranchia) · חשופיות אונות · Aeolidioidea, Fionoidea', html)
        self.assertIn('Nudibranchia (Cladobranchia) · חשופיות אילן · Dendronotoidea', html)
        self.assertNotIn('Dendronotoidea, \\N', html)

    def test_counts_show_gallery_genera_and_small_table_total(self):
        self.put_in_gallery('Flabellina', 'Flabellinidae')
        html = self.page('/admin/observations/taxongenus/')
        # 2 genera in the table under the aeolid group, 1 of them with a species in the gallery
        self.assertIn('Aeolidioidea, Fionoidea <span class="gal-count">1</span> <span class="db-count">(2)</span>', html)
        self.assertIn('Dendronotoidea <span class="gal-count">0</span> <span class="db-count">(1)</span>', html)

    def test_family_filter_counts_families(self):
        self.put_in_gallery('Flabellina', 'Flabellinidae')
        html = self.page('/admin/observations/taxonfamily/')
        self.assertIn('Aeolidioidea, Fionoidea <span class="gal-count">1</span> <span class="db-count">(2)</span>', html)
        self.assertIn('מספר המשפחות בגלריה', html)

    def test_title_says_what_the_counts_count(self):
        self.assertIn('לפי סדרה (מספר הסוגים בגלריה, ובקטן: במאגר)', self.page('/admin/observations/taxongenus/'))

    def test_filtering_still_works(self):
        html = self.page(f'/admin/observations/taxongenus/?family__order__id__exact={self.aeolid.pk}')
        self.assertIn('Flabellina', html)
        html = self.page(f'/admin/observations/taxongenus/?family__order__id__exact={self.dendro.pk}')
        self.assertNotIn('>Flabellina<', html)

    def test_panel_is_wider_left_aligned_and_smaller(self):
        html = self.page('/admin/observations/taxongenus/')
        self.assertIn('#changelist-filter { flex: 0 0 360px; }', html)          # 240px + 50%
        self.assertIn('direction: ltr; text-align: left; font-size: 11.5px;', html)
