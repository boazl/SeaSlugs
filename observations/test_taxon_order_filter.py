from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, TaxonFamily, TaxonGenus, TaxonOrder


class TaxonFiltersTests(TestCase):
    """The two taxonomy filters on the genus/family changelists: the order by name (one option
    per order, not per TaxonOrder row), then sub-orders and superfamilies, indented under their
    sub-order. Beside each option: rows with species in the gallery, and (small) rows in the table."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_superuser('manager', password='x')
        self.client.force_login(self.owner)
        self.sac = TaxonOrder.objects.create(name='Sacoglossa', taxonomic_order='1')
        self.bare = TaxonOrder.objects.create(name='Nudibranchia', sub_order='', taxonomic_order='3')
        self.dor = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Doridina', taxonomic_order='4')
        self.cla1 = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='7')
        self.cla2 = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='8')
        self.other = TaxonOrder.objects.create(name='Nudibranchia', sub_order='', taxonomic_order='9')     # no sub-order at all
        self.f_sac = TaxonFamily.objects.create(name='Plakobranchidae', order=self.sac, superfamily='Plakobranchoidea')
        self.f_bare = TaxonFamily.objects.create(name='Polyceridae', order=self.bare, superfamily='Polyceroidea')
        self.f_dor = TaxonFamily.objects.create(name='Chromodorididae', order=self.dor, superfamily='Chromodoridoidea')
        self.f_cla1 = TaxonFamily.objects.create(name='Tethydidae', order=self.cla1, superfamily='Dendronotoidea')
        self.f_cla2 = TaxonFamily.objects.create(name='Flabellinidae', order=self.cla2, superfamily='Fionoidea')
        self.f_other = TaxonFamily.objects.create(name='Zzzidae', order=self.other, superfamily='Zzzoidea')
        TaxonFamily.objects.create(name='Heroidae', order=self.cla1, superfamily='\\N')   # import artifact
        TaxonGenus.objects.create(name='Elysia', family=self.f_sac)
        TaxonGenus.objects.create(name='Zzzus', family=self.f_other)
        TaxonGenus.objects.create(name='Polycera', family=self.f_bare)
        TaxonGenus.objects.create(name='Hypselodoris', family=self.f_dor)
        TaxonGenus.objects.create(name='Felimare', family=self.f_dor)
        self.flab = TaxonGenus.objects.create(name='Flabellina', family=self.f_cla2)
        TaxonGenus.objects.create(name='Tethys', family=self.f_cla1)

    def page(self, query=''):
        return self.client.get('/admin/observations/taxongenus/' + query).content.decode()

    def put_in_gallery(self, genus, family):
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name=f'{genus} test', genus=genus, family=family)
        Sample(owner=self.owner, trip=trip, species=species, video_url='https://youtu.be/00000000001').save_reviewed()

    def test_order_filter_has_one_option_per_order_name(self):
        html = self.page()
        self.assertEqual(html.count('<span class="depth0">Nudibranchia</span>'), 1)
        self.assertIn('<span class="depth0">Sacoglossa</span>', html)
        self.assertIn('לפי סדרה (בגלריה, ובקטן: במאגר)', html)
        # all the Nudibranchia genera, across its four rows
        self.assertIn('<span class="depth0">Nudibranchia</span> <span class="gal-count">0</span> <span class="db-count">(6)</span>', html)

    def test_group_filter_indents_superfamilies_under_their_sub_order(self):
        html = self.page()
        self.assertIn('לפי תת־סדרה / על־משפחה', html)
        for text in ('<span class="depth0">Doridina</span>', '<span class="depth0">Cladobranchia</span>', '<span class="depth0">Others</span>',
                     '<span class="depth1">Zzzoidea</span>',
                     '<span class="depth1">Chromodoridoidea</span>', '<span class="depth1">Dendronotoidea</span>',
                     '<span class="depth1">Fionoidea</span>', '<span class="depth1">Polyceroidea</span>'):
            self.assertIn(text, html)
        self.assertIn('<span class="depth0">Plakobranchoidea</span>', html)    # an order with no sub-orders: not indented
        self.assertEqual(html.count('>Cladobranchia<'), 1)                     # two rows, one option
        self.assertNotIn('\\N</span>', html)                                    # the import artifact never becomes an option

    def test_phanerobranch_row_is_shown_under_doridina_not_others(self):
        # Nudibranchia #3 has no sub-order in the table, but its species are Doridina (as in the gallery).
        html = self.page()
        doridina = html.index('<span class="depth0">Doridina</span>')
        self.assertLess(doridina, html.index('<span class="depth1">Polyceroidea</span>'))
        self.assertLess(html.index('<span class="depth1">Polyceroidea</span>'), html.index('<span class="depth0">Cladobranchia</span>'))
        self.assertLess(html.index('<span class="depth0">Cladobranchia</span>'), html.index('<span class="depth0">Others</span>'))
        self.assertLess(html.index('<span class="depth0">Others</span>'), html.index('<span class="depth1">Zzzoidea</span>'))
        self.assertIn('<span class="depth0">Doridina</span> <span class="gal-count">0</span> <span class="db-count">(3)</span>', html)
        self.assertIn('<span class="depth0">Others</span> <span class="gal-count">0</span> <span class="db-count">(1)</span>', html)

    def test_counts_are_gallery_first_then_small_table_total(self):
        self.put_in_gallery('Hypselodoris', 'Chromodorididae')
        html = self.page()
        self.assertIn('<span class="depth0">Doridina</span> <span class="gal-count">1</span> <span class="db-count">(3)</span>', html)
        self.assertIn('<span class="depth1">Chromodoridoidea</span> <span class="gal-count">1</span> <span class="db-count">(2)</span>', html)
        self.assertIn('<span class="depth0">Cladobranchia</span> <span class="gal-count">0</span> <span class="db-count">(2)</span>', html)

    def test_order_choice_narrows_the_group_filter(self):
        html = self.page('?order_name=Sacoglossa')
        self.assertIn('<span class="depth0">Plakobranchoidea</span>', html)
        self.assertNotIn('Chromodoridoidea</span>', html)

    def test_filters_filter_the_list(self):
        def rows(query):
            html = self.page(query)
            return sorted(n for n in ('Elysia', 'Zzzus', 'Polycera', 'Hypselodoris', 'Felimare', 'Flabellina', 'Tethys') if f'<td class="field-name">{n}</td>' in html)
        self.assertEqual(rows('?order_name=Nudibranchia'), ['Felimare', 'Flabellina', 'Hypselodoris', 'Polycera', 'Tethys', 'Zzzus'])
        self.assertEqual(rows('?group=sub:Cladobranchia'), ['Flabellina', 'Tethys'])
        self.assertEqual(rows('?group=sf:Chromodoridoidea'), ['Felimare', 'Hypselodoris'])
        self.assertEqual(rows('?group=none:Nudibranchia'), ['Zzzus'])
        self.assertEqual(rows('?order_name=Nudibranchia&group=sub:Doridina'), ['Felimare', 'Hypselodoris', 'Polycera'])

    def test_family_changelist_has_the_same_filters_counting_families(self):
        self.put_in_gallery('Hypselodoris', 'Chromodorididae')
        html = self.client.get('/admin/observations/taxonfamily/').content.decode()
        self.assertIn('<span class="depth1">Chromodoridoidea</span> <span class="gal-count">1</span> <span class="db-count">(1)</span>', html)
        rows = self.client.get('/admin/observations/taxonfamily/?group=sf:Fionoidea').content.decode()
        self.assertIn('Flabellinidae', rows)
        self.assertNotIn('>Polyceridae<', rows)

    def test_panel_keeps_stock_width_and_font_but_is_left_aligned(self):
        html = self.page()
        self.assertNotIn('flex: 0 0', html)                                      # the stock width and font size
        self.assertNotIn('font-size: 11.5px', html)
        self.assertIn('direction: ltr; text-align: left;', html)
