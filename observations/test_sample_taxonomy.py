"""Sample taxonomy: order / family / genus / species fields that depend on the sample's kind,
the open-nomenclature qualifier and life stage, the full name, the image file name, the form,
the transfer format (old rows still accepted) and migration 0041."""
import json
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from .forms import SampleForm
from .models import Country, Sea, Region, DiveTrip, Species, Sample, TaxonOrder, TaxonFamily, TaxonGenus
from .table_transfer import TABLES, export_table, plan


class TaxonomyBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner', password='a-valid-password-927')
        self.country = Country.objects.create(name='Israel'); self.sea = Sea.objects.create(name='Med')
        self.region = Region.objects.create(name='Akhziv', country=self.country, sea=self.sea)
        self.trip = DiveTrip.objects.create(title='t', code='ak24', year=2024, country=self.country, region=self.region)
        self.order = TaxonOrder.objects.create(name='Nudibranchia')
        self.other_order = TaxonOrder.objects.create(name='Cephalaspidea')
        self.family = TaxonFamily.objects.create(name='Chromodorididae', order=self.order)
        self.other_family = TaxonFamily.objects.create(name='Aglajidae', order=self.other_order)
        self.genus = TaxonGenus.objects.create(name='Chromodoris', family=self.family)
        self.other_genus = TaxonGenus.objects.create(name='Chelidonura', family=self.other_family)
        self.species = Species.objects.create(genus='Chromodoris', species='strigata', author='Rudman, 1982')
        self._n = 0
    def sample(self, **kw):
        self._n += 1
        kw.setdefault('video_url', f'https://youtu.be/{str(self._n).zfill(11)}')
        return Sample(owner=self.user, trip=self.trip, **kw)


class KindFieldsTests(TaxonomyBase):
    def test_order_kind_keeps_only_the_order(self):
        s = self.sample(kind=Sample.Kind.ORDER, order='Nudibranchia', family='Chromodorididae', genus='Chromodoris',
                        species=self.species, species_other='x', identification_qualifier='cf.')
        s.full_clean(); s.save()
        s.refresh_from_db()
        self.assertEqual((s.order, s.family, s.genus, s.species_id, s.species_other, s.identification_qualifier), ('Nudibranchia', '', '', None, '', ''))

    def test_family_kind_fills_its_order_and_clears_genus_and_species(self):
        s = self.sample(kind=Sample.Kind.FAMILY, family='Chromodorididae', genus='Chromodoris', species=self.species)
        s.full_clean(); s.save(); s.refresh_from_db()
        self.assertEqual((s.order, s.family, s.genus, s.species_id), ('Nudibranchia', 'Chromodorididae', '', None))

    def test_genus_kind_fills_family_and_order_from_the_tables(self):
        s = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris')
        s.full_clean(); s.save(); s.refresh_from_db()
        self.assertEqual((s.order, s.family, s.genus, s.species_id), ('Nudibranchia', 'Chromodorididae', 'Chromodoris', None))

    def test_species_kind_takes_genus_family_and_order_from_the_species_and_tables(self):
        s = self.sample(species=self.species, order='Wrong', genus='Wrong')
        s.full_clean(); s.save(); s.refresh_from_db()
        self.assertEqual((s.order, s.family, s.genus), ('Nudibranchia', 'Chromodorididae', 'Chromodoris'))

    def test_species_outside_the_tables_falls_back_to_its_own_family_and_order(self):
        sp = Species.objects.create(genus='Newgenus', species='novus', family='Newfamily', order='Neworder')
        s = self.sample(species=sp); s.full_clean()
        self.assertEqual((s.order, s.family, s.genus), ('Neworder', 'Newfamily', 'Newgenus'))

    def test_plain_save_without_clean_also_normalises(self):
        # transfers and scripts save without full_clean(): the stored row must still be consistent
        s = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris', species_other='stale', species=self.species)
        s.save(); s.refresh_from_db()
        self.assertEqual((s.order, s.family, s.genus, s.species_id, s.species_other), ('Nudibranchia', 'Chromodorididae', 'Chromodoris', None, ''))
        sp = self.sample(species=self.species); sp.save(); sp.refresh_from_db()
        self.assertEqual((sp.order, sp.family, sp.genus), ('Nudibranchia', 'Chromodorididae', 'Chromodoris'))

    def test_collection_kind_clears_the_taxonomy_fields(self):
        s = self.sample(kind=Sample.Kind.COLLECTION, title='Night dive', order='Nudibranchia', family='x', genus='y',
                        life_stage='juv.')
        s.full_clean()
        self.assertEqual((s.order, s.family, s.genus, s.life_stage), ('', '', '', ''))

    def test_each_kind_requires_its_own_field(self):
        for kind, field in ((Sample.Kind.ORDER, 'order'), (Sample.Kind.FAMILY, 'family'), (Sample.Kind.GENUS, 'genus'), (Sample.Kind.SPECIES, 'species')):
            with self.assertRaises(ValidationError) as ctx:
                self.sample(kind=kind).full_clean()
            self.assertIn(field, ctx.exception.message_dict, kind)
        # a genus name in the wrong field does not satisfy a FAMILY sample
        with self.assertRaises(ValidationError) as ctx:
            self.sample(kind=Sample.Kind.FAMILY, genus='Chromodoris').full_clean()
        self.assertIn('family', ctx.exception.message_dict)

    def test_conflicting_levels_are_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris', family='Aglajidae').full_clean()
        self.assertIn('family', ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:
            self.sample(kind=Sample.Kind.FAMILY, family='Chromodorididae', order='Cephalaspidea').full_clean()
        self.assertIn('order', ctx.exception.message_dict)

    def test_unknown_names_are_accepted_as_typed(self):
        s = self.sample(kind=Sample.Kind.GENUS, genus='Brandnewgenus'); s.full_clean()
        self.assertEqual((s.genus, s.family, s.order), ('Brandnewgenus', '', ''))

    def test_species_other_is_only_for_species_kind_and_not_with_a_species(self):
        with self.assertRaises(ValidationError) as ctx:
            self.sample(species=self.species, species_other='x').full_clean()
        self.assertIn('species_other', ctx.exception.message_dict)
        s = self.sample(species=None, species_other='Chromodoris sp. new'); s.full_clean()
        self.assertEqual(s.species_other, 'Chromodoris sp. new')
        self.assertTrue(s.publication_reasons())

    def test_genus_kind_samples_publish_without_an_other_warning(self):
        s = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris')
        s.save_reviewed(actor=self.user, approve=True)
        self.assertEqual(s.status, 'published')
        self.assertFalse(any('להחליף את ערך המין' in r for r in s.publication_reasons()))

    def test_saving_a_genus_sample_points_the_genus_at_it(self):
        s = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris')
        s.save_reviewed(actor=self.user, approve=True)
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.defining_sample_id, s.pk)


class NameTests(TaxonomyBase):
    def test_name_comes_from_the_field_that_matches_the_kind(self):
        self.assertEqual(self.sample(kind=Sample.Kind.ORDER, order='Nudibranchia').taxon_name, 'Nudibranchia')
        self.assertEqual(self.sample(kind=Sample.Kind.FAMILY, family='Chromodorididae').taxon_name, 'Chromodorididae')
        self.assertEqual(self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris').taxon_name, 'Chromodoris')
        self.assertEqual(self.sample(species=self.species).taxon_name, 'Chromodoris strigata')
        self.assertEqual(self.sample(kind=Sample.Kind.COLLECTION, title='Trip').taxon_name, 'Trip')

    def test_full_name_has_qualifier_author_and_life_stage(self):
        s = self.sample(species=self.species)
        self.assertEqual(s.taxon_full_name, 'Chromodoris strigata Rudman, 1982')
        s.identification_qualifier = 'cf.'; s.life_stage = 'juv.'
        self.assertEqual(s.taxon_full_name, 'Chromodoris cf. strigata Rudman, 1982 juv.')
        self.assertEqual(s.taxon_label, 'Chromodoris cf. strigata juv.')
        s.identification_qualifier = 'aff.'
        self.assertEqual(s.taxon_label, 'Chromodoris aff. strigata juv.')

    def test_image_name_ignores_the_qualifier_and_uses_the_kind_field(self):
        s = self.sample(species=self.species, identification_qualifier='cf.')
        self.assertEqual(s.canonical_image_name(), 'observations/ak24-chromodoris-strigata.jpg')
        g = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris', family='Chromodorididae')
        self.assertEqual(g.canonical_image_name(), 'observations/ak24-chromodoris.jpg')
        f = self.sample(kind=Sample.Kind.FAMILY, family='Chromodorididae', genus='Chromodoris')
        f.sync_taxonomy()
        self.assertEqual(f.canonical_image_name(), 'observations/ak24-chromodorididae.jpg')


class FormTests(TaxonomyBase):
    def data(self, **kw):
        d = dict(kind='species', title='', order='', family='', genus='', species='', identification_qualifier='', life_stage='',
                 species_other='', trip=str(self.trip.pk), site='', site_other='', day='', depth='', video_url='https://youtu.be/abcdefghijk')
        d.update(kw); return d
    def test_genus_sample_is_saved_from_the_genus_field(self):
        form = SampleForm(self.data(kind='genus', genus='Chromodoris', species='stale text'))
        self.assertTrue(form.is_valid(), form.errors)
        s = form.save(commit=False); s.owner = self.user; s.save()
        self.assertEqual((s.kind, s.genus, s.family, s.order, s.species_id, s.species_other),
                         ('genus', 'Chromodoris', 'Chromodorididae', 'Nudibranchia', None, ''))
    def test_species_sample_with_qualifier_and_life_stage(self):
        form = SampleForm(self.data(species='Chromodoris strigata', identification_qualifier='cf.', life_stage='juv.'))
        self.assertTrue(form.is_valid(), form.errors)
        s = form.save(commit=False); s.owner = self.user; s.save()
        self.assertEqual((s.species_id, s.identification_qualifier, s.life_stage, s.genus), (self.species.pk, 'cf.', 'juv.', 'Chromodoris'))
    def test_missing_taxon_for_the_kind_is_a_form_error(self):
        form = SampleForm(self.data(kind='family'))
        self.assertFalse(form.is_valid()); self.assertIn('family', form.errors)
    def test_invalid_qualifier_is_rejected(self):
        form = SampleForm(self.data(species='Chromodoris strigata', identification_qualifier='sp.'))
        self.assertFalse(form.is_valid()); self.assertIn('identification_qualifier', form.errors)
    def test_full_name_is_read_only_and_shown_on_edit(self):
        s = self.sample(species=self.species, identification_qualifier='cf.'); s.save()
        form = SampleForm(instance=s)
        self.assertTrue(form.fields['full_name'].disabled)
        self.assertEqual(form.initial['full_name'], 'Chromodoris cf. strigata Rudman, 1982')
        # a posted value for it is ignored
        form = SampleForm(self.data(species='Chromodoris strigata', full_name='tampered'))
        self.assertTrue(form.is_valid(), form.errors); self.assertNotIn('tampered', str(form.cleaned_data.values()))
    def test_page_ships_the_cascade_data(self):
        self.client.force_login(self.user)
        response = self.client.get('/observations/new/')
        self.assertContains(response, 'name="order"'); self.assertContains(response, 'name="family"'); self.assertContains(response, 'name="genus"')
        self.assertContains(response, 'name="identification_qualifier"'); self.assertContains(response, 'name="life_stage"')
        self.assertContains(response, 'id="order-options"')
        taxonomy = response.context['taxonomy']
        self.assertIn('Nudibranchia', taxonomy['orders'])
        self.assertIn(('Chromodoris', 'Chromodorididae', 'Nudibranchia'), taxonomy['genera'])
        self.assertIn(('Chromodorididae', 'Nudibranchia'), taxonomy['families'])
        self.assertEqual(taxonomy['authors']['Chromodoris strigata'], 'Rudman, 1982')


class ListingTests(TaxonomyBase):
    def test_listing_heading_shows_the_qualifier(self):
        self.client.force_login(self.user)
        s = self.sample(species=self.species, identification_qualifier='cf.'); s.save_reviewed(actor=self.user, approve=True)
        response = self.client.get('/observations/')
        self.assertContains(response, 'Chromodoris cf. strigata')
    def test_order_family_genus_filters_use_the_sample_fields(self):
        self.client.force_login(self.user)
        sp = self.sample(species=self.species); sp.save_reviewed(actor=self.user, approve=True)
        fam = self.sample(kind=Sample.Kind.FAMILY, family='Aglajidae'); fam.save_reviewed(actor=self.user, approve=True)
        response = self.client.get('/observations/?order=Cephalaspidea')
        self.assertEqual([i.pk for i in response.context['observations']], [fam.pk])
        response = self.client.get('/observations/?genus=Chromodoris')
        self.assertEqual([i.pk for i in response.context['observations']], [sp.pk])
        self.assertIn('Aglajidae', response.context['families'])


class TransferTests(TaxonomyBase):
    def export(self):
        s = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris'); s.save_reviewed(actor=self.user, approve=True)
        return s, export_table('samples')
    def test_new_fields_are_exported_and_roundtrip(self):
        s, doc = self.export()
        row = doc['rows'][0]
        self.assertEqual((row['order'], row['family'], row['genus'], row['identification_qualifier'], row['life_stage']),
                         ('Nudibranchia', 'Chromodorididae', 'Chromodoris', '', ''))
        self.assertEqual(plan(json.loads(json.dumps(doc)))[0]['action'], 'same')
    def test_rows_from_before_the_taxonomy_fields_are_still_accepted(self):
        s, doc = self.export()
        old = {k: v for k, v in doc['rows'][0].items() if k not in ('order', 'family', 'genus', 'identification_qualifier', 'life_stage')}
        old['species_other'] = 'Chromodoris'     # how a genus-kind sample used to carry its name
        doc['rows'] = [old]
        result = plan(doc)[0]
        self.assertEqual(result['action'], 'same')
        self.assertEqual((result['object'].genus, result['object'].species_other), ('Chromodoris', ''))
    def test_oldest_rows_without_transfer_id_and_image_are_still_accepted(self):
        s, doc = self.export()
        skip = ('order', 'family', 'genus', 'identification_qualifier', 'life_stage', 'transfer_id', 'image')
        old = {k: v for k, v in doc['rows'][0].items() if k not in skip}
        old['species_other'] = 'Chromodoris'
        doc['rows'] = [old]
        self.assertEqual(plan(doc)[0]['object'].genus, 'Chromodoris')
    def test_a_row_with_unknown_extra_fields_is_still_rejected(self):
        s, doc = self.export()
        doc['rows'][0]['bogus'] = 'x'
        with self.assertRaises(ValidationError): plan(doc)


class Migration0041Tests(TransactionTestCase):
    before = [('observations', '0040_sample_taxonomy_fields')]
    after = [('observations', '0041_sample_taxonomy_data')]
    prior = [('observations', '0039_species_scientific_name_not_editable')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_taxon_names_move_out_of_species_other_and_back(self):
        old = self.migrate(self.before)
        g = lambda n: old.get_model('observations', n)
        owner = old.get_model('auth', 'User').objects.create(username='o')
        trip = g('DiveTrip').objects.create(title='t')
        order = g('TaxonOrder').objects.create(name='Nudibranchia')
        family = g('TaxonFamily').objects.create(name='Chromodorididae', order=order)
        g('TaxonGenus').objects.create(name='Chromodoris', family=family)
        sp = g('Species').objects.create(scientific_name='Chromodoris annae', genus='Chromodoris', species='annae', order='Doridida')
        mk = lambda **kw: g('Sample').objects.create(owner=owner, trip=trip, video_url='https://youtu.be/x', **kw)
        genus = mk(kind='genus', species_other='Chromodoris')
        fam = mk(kind='family', species_other='Chromodorididae')
        order_s = mk(kind='order', species_other='Nudibranchia')
        species = mk(kind='species', species=sp)
        other = mk(kind='species', species_other='Undescribed')
        coll = mk(kind='collection', title='c')

        new = self.migrate(self.after)
        S = new.get_model('observations', 'Sample')
        f = lambda s: S.objects.values_list('order', 'family', 'genus', 'species_other', 'species_id').get(pk=s.pk)
        self.assertEqual(f(genus), ('Nudibranchia', 'Chromodorididae', 'Chromodoris', '', None))
        self.assertEqual(f(fam), ('Nudibranchia', 'Chromodorididae', '', '', None))
        self.assertEqual(f(order_s), ('Nudibranchia', '', '', '', None))
        self.assertEqual(f(species), ('Nudibranchia', 'Chromodorididae', 'Chromodoris', '', sp.pk))   # via the genus, not species.order
        self.assertEqual(f(other), ('', '', '', 'Undescribed', None))
        self.assertEqual(f(coll), ('', '', '', '', None))

        back = self.migrate(self.before)
        Sb = back.get_model('observations', 'Sample')
        self.assertEqual(Sb.objects.get(pk=genus.pk).species_other, 'Chromodoris')
        self.assertEqual(Sb.objects.get(pk=fam.pk).species_other, 'Chromodorididae')
        self.assertEqual(Sb.objects.get(pk=order_s.pk).species_other, 'Nudibranchia')
        self.assertEqual(Sb.objects.get(pk=other.pk).species_other, 'Undescribed')


class EpithetFieldTests(TaxonomyBase):
    """The species field of a sample holds the epithet only; the genus has its own field."""
    def data(self, **kw):
        d = dict(kind='species', title='', order='', family='', genus='', species='', identification_qualifier='', life_stage='',
                 species_other='', trip=str(self.trip.pk), site='', site_other='', day='', depth='', video_url='https://youtu.be/abcdefghijk')
        d.update(kw); return d
    def test_genus_plus_epithet_finds_the_species(self):
        form = SampleForm(self.data(genus='Chromodoris', species='strigata'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['species'], self.species)
    def test_epithet_is_looked_up_within_the_genus(self):
        other = Species.objects.create(genus='Hypselodoris', species='strigata')
        form = SampleForm(self.data(genus='Hypselodoris', species='strigata'))
        self.assertTrue(form.is_valid(), form.errors); self.assertEqual(form.cleaned_data['species'], other)
    def test_epithet_that_does_not_exist_in_the_genus_is_an_error(self):
        form = SampleForm(self.data(genus='Chelidonura', species='strigata'))
        self.assertFalse(form.is_valid()); self.assertIn('species', form.errors)
    def test_open_nomenclature_epithets_and_variant_letter(self):
        sp = Species.objects.create(genus='Coryphellina', species='sp.')
        form = SampleForm(self.data(genus='Coryphellina', species='sp. A'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['species'], sp); self.assertEqual(form.instance.undetermined_variant, 'A')
        s = form.save(commit=False); s.owner = self.user; s.save()
        self.assertEqual(SampleForm(instance=s).initial['species'], 'sp. A')
    def test_a_full_name_in_the_species_field_is_still_accepted(self):
        for genus in ('', 'Chromodoris'):
            form = SampleForm(self.data(genus=genus, species='Chromodoris strigata'))
            self.assertTrue(form.is_valid(), form.errors); self.assertEqual(form.cleaned_data['species'], self.species)


class SampleAdminListTests(TaxonomyBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('boss', password='pw-for-tests-1')
        self.client.force_login(self.admin)
        self.s = self.sample(species=self.species); self.s.save_reviewed(actor=self.admin)
        self.g = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris'); self.g.save_reviewed(actor=self.admin, approve=True)
    def post(self, **overrides):
        rows = [self.s, self.g]
        data = {'form-TOTAL_FORMS': '2', 'form-INITIAL_FORMS': '2', 'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000', '_save': 'Save'}
        for i, row in enumerate(rows):
            row.refresh_from_db()
            epithet = row.species.species if row.species_id else ''
            data.update({f'form-{i}-id': str(row.pk), f'form-{i}-order': row.order, f'form-{i}-family': row.family, f'form-{i}-genus': row.genus,
                         f'form-{i}-species': epithet, f'form-{i}-identification_qualifier': row.identification_qualifier, f'form-{i}-life_stage': row.life_stage})
        data.update(overrides)
        return self.client.post('/admin/observations/sample/', data, follow=True)
    def test_list_has_editable_taxonomy_columns_and_compact_filters(self):
        response = self.client.get('/admin/observations/sample/')
        self.assertEqual(response.status_code, 200)
        for name in ('order', 'family', 'genus', 'species', 'identification_qualifier', 'life_stage'):
            self.assertContains(response, f'name="form-0-{name}"')
        # order/family/genus/species suggest the known names through one shared list each
        for column in ('order', 'family', 'genus', 'species'):
            self.assertContains(response, f'<datalist id="sample-{column}-options">')
            self.assertContains(response, f'list="sample-{column}-options"')
        self.assertContains(response, '<option value="Chromodorididae">')
        # the species column holds the epithet only
        self.assertContains(response, 'value="strigata"')
        # long filters are dropdowns, and the panel is kept narrow
        self.assertContains(response, 'dropdown-filter'); self.assertContains(response, 'max-width: 210px')
    def test_unchanged_save_keeps_every_row(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.s.refresh_from_db(); self.g.refresh_from_db()
        self.assertEqual((self.s.species_id, self.s.genus, self.g.genus, self.g.species_id), (self.species.pk, 'Chromodoris', 'Chromodoris', None))
    def test_editing_the_species_and_qualifier_from_the_list(self):
        other = Species.objects.create(genus='Chromodoris', species='annae')
        response = self.post(**{'form-0-species': 'annae', 'form-0-identification_qualifier': 'cf.', 'form-0-life_stage': 'juv.'})
        self.assertEqual(response.status_code, 200)
        self.s.refresh_from_db()
        self.assertEqual((self.s.species_id, self.s.identification_qualifier, self.s.life_stage), (other.pk, 'cf.', 'juv.'))
    def test_an_unknown_species_in_the_list_is_rejected(self):
        response = self.post(**{'form-0-species': 'nonexistent'})
        self.assertContains(response, 'לא נמצא מין תואם')
        self.s.refresh_from_db(); self.assertEqual(self.s.species_id, self.species.pk)
    def test_a_genus_sample_row_can_change_its_genus(self):
        response = self.post(**{'form-1-genus': 'Chelidonura', 'form-1-family': '', 'form-1-order': ''})
        self.assertEqual(response.status_code, 200)
        self.g.refresh_from_db()
        self.assertEqual((self.g.genus, self.g.family, self.g.order), ('Chelidonura', 'Aglajidae', 'Cephalaspidea'))
    def test_long_filter_values_are_truncated_in_the_dropdown(self):
        trip = DiveTrip.objects.create(title='T' * 120, code='x' * 40, year=2024, country=self.country, region=self.region)
        Sample(owner=self.user, trip=trip, species=self.species, video_url='https://youtu.be/zzzzzzzzzzz').save()
        response = self.client.get('/admin/observations/sample/')
        self.assertNotContains(response, '>' + 'T' * 120)            # the visible option text is cut...
        self.assertContains(response, 'title="' + 'T' * 120)         # ...and the full text stays in the tooltip
    def test_change_form_has_working_dropdown_fields(self):
        response = self.client.get(f'/admin/observations/sample/{self.s.pk}/change/')
        self.assertEqual(response.status_code, 200)
        # regression: the inputs were escaped and shown as literal HTML text
        self.assertNotContains(response, '&lt;input'); self.assertNotContains(response, '&lt;datalist')
        for name in ('order', 'family', 'genus', 'species'):
            self.assertContains(response, f'<input type="text" name="{name}"')
        # suggestion lists for every level, filled by the shared cascade script
        for listing in ('order-options', 'family-options', 'genus-options', 'species-options'):
            self.assertContains(response, f'<datalist id="{listing}">')
        self.assertContains(response, 'list="genus-options"'); self.assertContains(response, 'list="species-options"')
        self.assertContains(response, '<option value="Chromodoris strigata">')
        self.assertContains(response, 'id="taxonomy"')
        self.assertContains(response, 'Taxonomic cascade')

    def test_datalist_widget_output_is_marked_safe(self):
        from django.utils.safestring import SafeString
        from .admin import DatalistTextInput
        self.assertIsInstance(DatalistTextInput(['a']).render('x', 'v'), SafeString)


class ReferenceTableTests(TaxonomyBase):
    """cf./aff. and juv. come from admin-editable reference tables, which also transfer."""
    def test_tables_are_seeded_and_new_values_can_be_added(self):
        from .models import IdentificationQualifier, LifeStage
        self.assertEqual(set(IdentificationQualifier.objects.values_list('code', flat=True)), {'cf.', 'aff.'})
        self.assertEqual(set(LifeStage.objects.values_list('code', flat=True)), {'juv.'})
        LifeStage.objects.create(code='ad.', name='בוגר', name_en='adult')
        form = SampleForm()
        self.assertIn(('ad.', 'ad. — בוגר'), list(form.fields['life_stage'].choices))
        s = self.sample(species=self.species, life_stage='ad.'); s.full_clean()
        self.assertEqual(s.taxon_label, 'Chromodoris strigata ad.')
    def test_a_value_missing_from_the_table_is_rejected(self):
        for field in ('identification_qualifier', 'life_stage'):
            with self.assertRaises(ValidationError) as ctx:
                self.sample(species=self.species, **{field: 'zz.'}).full_clean()
            self.assertIn(field, ctx.exception.message_dict)
    def test_selects_offer_the_table_values_and_managers_get_an_add_link(self):
        form = SampleForm()
        self.assertEqual([c[0] for c in form.fields['identification_qualifier'].choices], ['', 'aff.', 'cf.'])
        self.assertNotIn('/admin/', form['life_stage'].as_widget())
        form.enable_add_links()
        self.assertIn('/admin/observations/lifestage/add/', form['life_stage'].as_widget())
        self.assertIn('/admin/observations/identificationqualifier/add/', form['identification_qualifier'].as_widget())
    def test_public_edit_page_shows_add_links_only_to_staff(self):
        s = self.sample(species=self.species); s.save()
        staff = User.objects.create_user('staffer', password='pw-for-tests-4', is_staff=True)
        s.owner = staff; s.save()
        self.client.force_login(staff)
        url = f'/observations/{s.pk}/edit/'
        self.assertContains(self.client.get(url), '/admin/observations/lifestage/add/')
        plain = User.objects.create_user('plainuser', password='pw-for-tests-5')
        s.owner = plain; s.save()
        self.client.force_login(plain)
        self.assertNotContains(self.client.get(url), '/admin/observations/lifestage/add/')
    def test_admin_pages_for_the_tables_and_add_links_on_the_change_form(self):
        admin = User.objects.create_superuser('boss2', password='pw-for-tests-2'); self.client.force_login(admin)
        for name in ('identificationqualifier', 'lifestage'):
            self.assertEqual(self.client.get(f'/admin/observations/{name}/').status_code, 200)
            self.assertEqual(self.client.get(f'/admin/observations/{name}/add/').status_code, 200)
        s = self.sample(species=self.species); s.save()
        response = self.client.get(f'/admin/observations/sample/{s.pk}/change/')
        self.assertContains(response, '/admin/observations/identificationqualifier/add/')
    def test_full_name_field_sits_right_after_the_species_field(self):
        names = list(SampleForm().fields)
        self.assertEqual(names[names.index('species') + 1], 'full_name')
        self.assertEqual(SampleForm().fields['full_name'].label, 'השם המדעי המלא (כולל מחבר ותוספות)')
    def test_reference_tables_are_in_the_table_transfer_list_before_samples(self):
        keys = list(TABLES)
        self.assertIn('qualifiers', keys); self.assertIn('lifestages', keys)
        self.assertLess(keys.index('qualifiers'), keys.index('samples')); self.assertLess(keys.index('lifestages'), keys.index('samples'))
        admin = User.objects.create_superuser('boss3', password='pw-for-tests-3'); self.client.force_login(admin)
        response = self.client.get('/admin/table-transfer/')
        self.assertContains(response, 'qualifiers'); self.assertContains(response, 'lifestages')
    def test_reference_tables_roundtrip_through_table_transfer(self):
        from .models import IdentificationQualifier, LifeStage
        LifeStage.objects.create(code='ad.', name='בוגר', name_en='adult')
        for table, model in (('qualifiers', IdentificationQualifier), ('lifestages', LifeStage)):
            doc = json.loads(json.dumps(export_table(table)))
            self.assertEqual(set(doc['rows'][0]), {'code', 'name', 'name_en'})
            self.assertEqual({r['action'] for r in plan(doc)}, {'same'})
            # a new value is created, an edited one updated -- matched by its abbreviation
            doc['rows'].append({'code': 'sp.', 'name': 'מין לא מזוהה', 'name_en': 'unidentified'})
            doc['rows'][0]['name_en'] = 'changed'
            actions = {r['label']: r['action'] for r in plan(doc)}
            self.assertEqual(list(actions.values()).count('new'), 1); self.assertIn('update', actions.values())
    def test_samples_carry_the_new_fields_and_need_the_table_values_at_the_target(self):
        from .models import IdentificationQualifier
        s = self.sample(species=self.species, identification_qualifier='cf.', life_stage='juv.'); s.save_reviewed(actor=self.user)
        doc = json.loads(json.dumps(export_table('samples')))
        self.assertEqual((doc['rows'][0]['identification_qualifier'], doc['rows'][0]['life_stage']), ('cf.', 'juv.'))
        self.assertEqual(plan(doc)[0]['action'], 'same')
        IdentificationQualifier.objects.filter(code='cf.').delete()      # target environment without the table row
        with self.assertRaises(ValidationError): plan(doc)
