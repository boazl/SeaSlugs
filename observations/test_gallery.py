import json
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Country, Sea, Region, Species, Sample, DiveTrip


class GalleryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name='Test species')
        self.item = Sample(owner=self.owner, trip=self.trip, species=species, video_url='https://youtu.be/abcdefghijk')
        self.item.save_reviewed()

    def catalog(self):
        response = self.client.get('/catalog.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        return json.loads(response.content.decode().split('=', 1)[1].strip().removesuffix(';'))

    def test_database_updates_and_soft_delete_reach_gallery(self):
        self.assertEqual(self.catalog()['species'][0]['title'], 'Test species')
        self.item.video_url = 'https://youtu.be/zyxwvutsrqp'
        self.item.save()
        self.assertEqual(self.catalog()['species'][0]['video_id'], 'zyxwvutsrqp')
        self.item.soft_delete(self.owner)
        self.assertEqual(self.catalog()['species'], [])

    def test_catalog_exposes_genus_and_epithet_for_alphabetical_sorting(self):
        # The gallery's alphabetical sort (genus, then specific epithet) is done client
        # side in app.js, so both fields must actually reach catalog.js.
        self.item.species.genus = 'Testus'
        self.item.species.species = 'exemplaris'
        self.item.species.save()
        entry = self.catalog()['species'][0]
        self.assertEqual(entry['genus'], 'Testus')
        self.assertEqual(entry['epithet'], 'exemplaris')

    def test_catalog_exposes_defining_samples_region_and_year_for_the_card_caption(self):
        # The species card shows "<region>, <year>" (e.g. "Eilat, 2026") for the defining
        # sample's own trip, rather than the coarser country+sea area label -- both fields
        # must reach catalog.js for app.js to render that.
        entry = self.catalog()['species'][0]
        self.assertEqual(entry['region'], str(self.trip.region_id))
        self.assertEqual(entry['year'], 2026)
        self.assertEqual(self.catalog()['regions'][str(self.trip.region_id)]['label'], 'אילת')

    def test_species_hidden_when_area_has_no_defining_sample(self):
        from .models import SpeciesArea
        area = SpeciesArea.objects.get(species=self.item.species)
        area.defining_sample = None
        area.save(update_fields=['defining_sample'])
        self.assertEqual(self.catalog()['species'], [])

    def test_soft_deleting_the_defining_sample_falls_back_to_another_published_one(self):
        second = Sample(owner=self.owner, trip=self.trip, species=self.item.species, video_url='https://youtu.be/12345678901')
        second.save_reviewed()
        self.item.soft_delete(self.owner)
        catalog = self.catalog()
        self.assertEqual(len(catalog['species']), 1)
        self.assertEqual(catalog['species'][0]['video_id'], '12345678901')

    def test_pending_and_incomplete_records_are_not_public(self):
        self.item.status = 'pending'
        self.item.save()
        self.assertEqual(self.catalog()['species'], [])
        self.trip.year = None
        self.trip.save()
        with self.assertRaises(ValidationError):
            self.item.save_reviewed(actor=self.owner, approve=True)
        self.item.status = 'published'
        self.item.save()
        self.assertEqual(self.catalog()['species'], [])

    def test_manager_links_and_admin_form(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/observations/'), f'/admin/observations/sample/{self.item.pk}/change/')
        self.assertEqual(self.client.get(f'/admin/observations/sample/{self.item.pk}/change/').status_code, 200)

    def test_account_navigation_and_private_observation_list(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'href="/observations/"')
        self.assertContains(response, 'href="/observations/login/"')
        self.assertEqual(self.client.get('/observations/').status_code, 302)
        member = User.objects.create_user('ordinary-member', first_name='Dana', password='test-password')
        self.client.force_login(member)
        response = self.client.get('/')
        self.assertContains(response, '<bdi>Dana</bdi>');self.assertNotContains(response, 'ordinary-member')
        self.assertContains(response, 'href="/observations/"')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        for suffix in ('', '?mine=0', '?owner=1'):
            self.assertNotContains(self.client.get('/observations/' + suffix), 'Test species')
        self.item.owner = member
        self.item.status = 'pending'
        self.item.save()
        self.assertContains(self.client.get('/observations/'), 'Test species')
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/observations/'), 'Test species')
        self.client.logout()
        self.assertNotContains(self.client.get('/'), 'ordinary-member')


class ObservationsFilterTests(TestCase):
    """Covers the /observations/ list page's filter/sort GET params added alongside
    the gallery sort feature: narrowing filters, manager-only scope of the owner
    filter, sort ordering, and the filter-dropdown option lists themselves."""

    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        self.client.force_login(self.owner)

    def make(self, species, owner=None):
        sample = Sample(owner=owner or self.owner, trip=self.trip, species=species,
                         video_url='https://youtu.be/abcdefghijk')
        sample.save_reviewed(actor=self.owner, approve=True)
        return sample

    def test_kind_filter_narrows_observations_list(self):
        self.make(Species.objects.create(scientific_name='Aeolid species'))
        collection = Sample(owner=self.owner, kind='collection', trip=self.trip, title='Trip collection',
                             video_url='https://youtu.be/abcdefghijk')
        collection.save_reviewed(actor=self.owner, approve=True)
        response = self.client.get('/observations/?kind=collection')
        self.assertContains(response, 'Trip collection')
        self.assertNotContains(response, 'Aeolid species')
        response = self.client.get('/observations/?kind=species')
        self.assertContains(response, 'Aeolid species')
        self.assertNotContains(response, 'Trip collection')

    def test_owner_filter_is_manager_only(self):
        self.make(Species.objects.create(scientific_name='Manager species'))
        member = User.objects.create_user('member', password='test-password')
        self.make(Species.objects.create(scientific_name='Member species'), owner=member)
        response = self.client.get(f'/observations/?owner={member.username}')
        self.assertContains(response, 'Member species')
        self.assertNotContains(response, 'Manager species')
        self.client.force_login(member)
        response = self.client.get(f'/observations/?owner={self.owner.username}')
        # Non-managers can't use the owner param to see someone else's records --
        # they only ever see their own, whatever the query string says.
        self.assertNotContains(response, 'Manager species')
        self.assertContains(response, 'Member species')

    def test_sort_by_species_name(self):
        self.make(Species.objects.create(scientific_name='Zzz species'))
        self.make(Species.objects.create(scientific_name='Aaa species'))
        content = self.client.get('/observations/?sort=species').content.decode()
        self.assertLess(content.index('Aaa species'), content.index('Zzz species'))

    def test_filter_dropdown_options_have_no_duplicates(self):
        # Regression: Sample's default Meta.ordering (-created_at) must not leak into the
        # values_list().distinct() calls that build the filter dropdowns, or the same
        # option value appears twice whenever two matching samples have different
        # created_at timestamps -- the same class of bug once fixed in SpeciesArea.rebuild().
        # A second, differently-ordered species is included so the "order" filter has more
        # than one value and is actually rendered (see test_single_value_filters_are_hidden).
        species = Species.objects.create(scientific_name='Duplicate species', order='Nudibranchia')
        other = Species.objects.create(scientific_name='Other species', order='Sacoglossa')
        first = self.make(species)
        second = self.make(species)
        self.make(other)
        Sample.objects.filter(pk=second.pk).update(created_at=first.created_at - timedelta(days=1))
        response = self.client.get('/observations/')
        self.assertEqual(response.context['orders'], ['Nudibranchia', 'Sacoglossa'])
        self.assertEqual(response.content.decode().count('value="Nudibranchia"'), 1)

    def test_single_value_filters_are_hidden_from_the_form(self):
        # A filter whose only visible data holds one distinct value (or none) can never
        # narrow the result set, so it shouldn't clutter the form -- kind, status, country,
        # order etc. are all published with the exact same values in setUp/make().
        self.make(Species.objects.create(scientific_name='Only species', order='Nudibranchia'))
        content = self.client.get('/observations/').content.decode()
        for hidden_field in ('name="kind"', 'name="status"', 'name="country"', 'name="region"',
                              'name="order"', 'name="genus"', 'name="photographer"'):
            self.assertNotIn(hidden_field, content)

    def test_genus_filter_is_a_searchable_autocomplete_field(self):
        berghia = Species.objects.create(scientific_name='Berghia coerulescens', genus='Berghia')
        hypselodoris = Species.objects.create(scientific_name='Hypselodoris picta', genus='Hypselodoris')
        self.make(berghia)
        self.make(hypselodoris)
        response = self.client.get('/observations/')
        self.assertContains(response, 'name="genus" list="genus-options"')
        self.assertContains(response, '<option value="Berghia">')
        self.assertContains(response, '<option value="Hypselodoris">')
        # A partial, not-quite-exact typed value still narrows the results (icontains).
        response = self.client.get('/observations/?genus=Berg')
        self.assertContains(response, 'Berghia coerulescens')
        self.assertNotContains(response, 'Hypselodoris picta')


class TaxonomicSortAndPanelTests(TestCase):
    """Covers the gallery's taxonomic sort (order -> family -> genus, by each level's own
    curated taxonomic_order) and the data app.js needs to render the group-heading panels:
    per-species taxon ids (to detect where a group changes) and per-taxon labels/thumbnails
    (catalog.taxa), including the sub_order value used for the suborder filter."""

    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)

    def catalog(self):
        response = self.client.get('/catalog.js')
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content.decode().split('=', 1)[1].strip().removesuffix(';'))

    def publish(self, species):
        item = Sample(owner=self.owner, trip=self.trip, species=species, video_url='https://youtu.be/abcdefghijk')
        item.save_reviewed()
        return item

    def test_species_sorted_by_taxon_taxonomic_order_not_just_phylogenetic_order(self):
        from .models import TaxonOrder
        # Two species whose raw phylogenetic_order would sort them the other way round, but
        # whose curated TaxonOrder.taxonomic_order disagrees -- the curated rank wins.
        TaxonOrder.objects.create(name='Sacoglossa', taxonomic_order='001')
        TaxonOrder.objects.create(name='Nudibranchia', taxonomic_order='002')
        sp_a = Species.objects.create(scientific_name='A species', order='Nudibranchia', phylogenetic_order='100')
        sp_b = Species.objects.create(scientific_name='B species', order='Sacoglossa', phylogenetic_order='999')
        self.publish(sp_a)
        self.publish(sp_b)
        titles = [e['title'] for e in self.catalog()['species']]
        self.assertEqual(titles, ['B species', 'A species'])

    def test_species_expose_taxon_ids_and_sub_order_for_the_gallery_panel(self):
        from .models import TaxonOrder, TaxonFamily, TaxonGenus
        order = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia')
        family = TaxonFamily.objects.create(name='Facelinidae', order=order)
        genus = TaxonGenus.objects.create(name='Facelina', family=family)
        species = Species.objects.create(scientific_name='Facelina test', order='Nudibranchia', family='Facelinidae', genus='Facelina')
        self.publish(species)
        entry = self.catalog()['species'][0]
        self.assertEqual(entry['taxon_order_id'], str(order.pk))
        self.assertEqual(entry['taxon_family_id'], str(family.pk))
        self.assertEqual(entry['taxon_genus_id'], str(genus.pk))
        self.assertEqual(entry['sub_order'], 'Cladobranchia')

    def test_taxa_payload_carries_labels_and_defining_sample_thumbnail(self):
        from .models import TaxonOrder, TaxonFamily, TaxonGenus
        order = TaxonOrder.objects.create(name='Nudibranchia', name_he='עירומי זימים', sub_order='Cladobranchia')
        family = TaxonFamily.objects.create(name='Facelinidae', order=order)
        genus = TaxonGenus.objects.create(name='Facelina', family=family)
        species = Species.objects.create(scientific_name='Facelina test', order='Nudibranchia', family='Facelinidae', genus='Facelina')
        item = self.publish(species)
        order.defining_sample = item
        order.save(update_fields=['defining_sample'])
        taxa = self.catalog()['taxa']
        order_entry = taxa['orders'][str(order.pk)]
        # The scientific (Latin) name leads; the Hebrew name (when set) follows in parens.
        self.assertEqual(order_entry['label'], 'Nudibranchia (Cladobranchia) (עירומי זימים)')
        self.assertEqual(order_entry['label_en'], 'Nudibranchia (Cladobranchia)')
        self.assertTrue(order_entry['thumbnail'])
        self.assertIn(str(genus.pk), taxa['genera'])

    def test_species_without_a_genus_match_falls_back_to_the_family_base_row(self):
        from .models import TaxonFamily
        # A species identified only to family level (no genus text) still resolves through
        # the auto-built base family row, rather than being left with no taxon ids at all.
        family = TaxonFamily.objects.create(name='Some family')
        species = Species.objects.create(scientific_name='Family-only species', family='Some family')
        self.publish(species)
        entry = self.catalog()['species'][0]
        self.assertEqual(entry['taxon_family_id'], str(family.pk))
        self.assertIsNone(entry['taxon_genus_id'])

    def test_species_with_no_matching_taxon_rows_gets_null_taxon_ids(self):
        species = Species.objects.create(scientific_name='Unmatched species', order='Nowhereida')
        self.publish(species)
        entry = self.catalog()['species'][0]
        self.assertIsNone(entry['taxon_order_id'])
        self.assertEqual(entry['sub_order'], '')

    def test_species_with_blank_genus_resolves_via_scientific_name_leading_word(self):
        from .models import TaxonFamily, TaxonGenus
        # A handful of real species have a blank genus column even though their scientific
        # name clearly starts with one -- resolve_taxon_chain falls back to that leading word
        # for resolution only (Species.genus itself is never touched).
        family = TaxonFamily.objects.create(name='Facelinidae')
        genus = TaxonGenus.objects.create(name='Coryphellina', family=family)
        species = Species.objects.create(scientific_name='Coryphellina iurmanovi', genus='', family='Facelinidae')
        self.publish(species)
        entry = self.catalog()['species'][0]
        self.assertEqual(entry['taxon_genus_id'], str(genus.pk))
        self.assertEqual(entry['taxon_family_id'], str(family.pk))
