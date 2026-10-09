from django.contrib.auth.models import User
from django.test import TestCase

from .models import Species, TaxonOrder, TaxonFamily, TaxonGenus


class SpeciesAddTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_superuser('root', 'r@example.com', 'pw')
        self.member = User.objects.create_user('member', password='pw')
        self.order = TaxonOrder.objects.create(name='Nudibranchia')
        self.family = TaxonFamily.objects.create(name='Chromodorididae', order=self.order, superfamily='Doridoidea')
        self.genus = TaxonGenus.objects.create(name='Chromodoris', family=self.family)
        self.url = '/observations/species/new/'

    def post(self, **data):
        base = {'genus': 'Chromodoris', 'species': 'testa', 'author': 'Rudman, 1982', 'next': '/observations/new/'}
        base.update(data)
        return self.client.post(self.url, base)

    def test_only_a_manager_can_add_a_species(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)           # login
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post().status_code, 404)
        self.assertFalse(Species.objects.filter(species='testa').exists())

    def test_known_genus_fills_family_order_and_superfamily_and_returns_with_the_species_chosen(self):
        self.client.force_login(self.manager)
        response = self.post()
        species = Species.objects.get(scientific_name='Chromodoris testa')
        self.assertEqual((species.family, species.order, species.superfamily), ('Chromodorididae', 'Nudibranchia', 'Doridoidea'))
        self.assertEqual(response.url, f'/observations/new/?new_species={species.pk}')
        page = self.client.get(response.url)
        form = page.context['form']
        self.assertEqual((form.initial['genus'], form.initial['species']), ('Chromodoris', 'testa'))

    def test_a_new_genus_needs_a_family_and_gets_its_taxonomy_row(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.post(genus='Newgenus').status_code, 200)
        self.assertFalse(Species.objects.filter(genus='Newgenus').exists())
        self.post(genus='Newgenus', family='Chromodorididae')
        species = Species.objects.get(genus='Newgenus')
        self.assertEqual(species.order, 'Nudibranchia')
        self.assertEqual(TaxonGenus.objects.get(name='Newgenus').family, self.family)

    def test_duplicates_are_refused_in_any_case(self):
        self.client.force_login(self.manager)
        self.post()
        before = Species.objects.count()
        self.assertEqual(self.post(species='TESTA').status_code, 200)
        self.assertEqual(Species.objects.count(), before)

    def test_an_author_is_required_except_for_an_undescribed_sp(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.post(species='described', author='').status_code, 200)
        self.assertFalse(Species.objects.filter(species='described').exists())
        self.assertEqual(self.post(species='sp. 7', author='').status_code, 302)
        self.assertEqual(self.post(species='spinosa', author='').status_code, 200)   # not "sp."

    def test_next_is_not_an_open_redirect(self):
        self.client.force_login(self.manager)
        self.assertTrue(self.post(next='https://evil.example/').url.startswith('/observations/new/'))

    def test_the_free_text_other_species_field_is_for_members_not_managers(self):
        self.client.force_login(self.manager)
        page = self.client.get('/observations/new/')
        self.assertContains(page, 'href="/observations/species/new/?next=')
        self.assertContains(page, 'type="hidden" name="species_other"')
        self.client.force_login(self.member)
        page = self.client.get('/observations/new/')
        self.assertNotContains(page, 'species-add-link')
        self.assertNotContains(page, 'type="hidden" name="species_other"')
