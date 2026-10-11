"""An order's page holds every species of the order, whichever sub-order row (TaxonOrder) it sits in."""
import io
import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .models import Country, DiveTrip, Region, Sample, Sea, Species, TaxonFamily, TaxonGenus, TaxonOrder


def png(color):
    buffer = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(buffer, 'PNG')
    return SimpleUploadedFile('p.png', buffer.getvalue(), content_type='image/png')


class WholeOrderPageTests(TestCase):
    def setUp(self):
        owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        self.base = TaxonOrder.objects.create(name='Nudibranchia', name_he='חשופיות')
        self.group = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Doridina')
        self.single = TaxonOrder.objects.create(name='Sacoglossa', name_he='עלעליות')
        for i, (order, family, genus, sp) in enumerate([
                (self.base, 'Hexabranchidae', 'Hexabranchus', 'sanguineus'),
                (self.group, 'Chromodorididae', 'Chromodoris', 'annae'),
                (self.single, 'Plakobranchidae', 'Plakobranchus', 'ocellatus')]):
            fam = TaxonFamily.objects.create(name=family, order=order)
            TaxonGenus.objects.create(name=genus, family=fam)
            species = Species.objects.create(scientific_name=f'{genus} {sp}', genus=genus, species=sp)
            Sample(owner=owner, trip=trip, species=species, image=png((i * 70, 40, 90))).save_reviewed()

    def names(self, response):
        html = response.content.decode()
        return [n for n in ('Hexabranchus', 'Chromodoris', 'Plakobranchus') if n in html]

    def test_the_base_row_page_holds_every_species_of_the_order(self):
        response = self.client.get(reverse('order-page', args=[self.base.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.names(response), ['Hexabranchus', 'Chromodoris'])
        html = response.content.decode()
        self.assertIn('חשופיות', html)                    # the common name of the whole order

    def test_a_sub_order_page_keeps_just_its_own_species(self):
        response = self.client.get(reverse('order-page', args=[self.group.pk]))
        self.assertEqual(self.names(response), ['Chromodoris'])

    def test_an_order_with_one_row_is_unchanged(self):
        response = self.client.get(reverse('order-page', args=[self.single.pk]))
        self.assertEqual(self.names(response), ['Plakobranchus'])
        self.assertIn('עלעליות', response.content.decode())

    def test_the_catalog_tells_the_gallery_which_page_holds_each_order(self):
        response = self.client.get('/catalog.js')
        data = json.loads(response.content.decode().split('=', 1)[1].strip().removesuffix(';'))
        self.assertEqual(data['taxa']['order_pages'], {'Nudibranchia': self.base.pk, 'Sacoglossa': self.single.pk})

    def test_the_gallery_links_an_order_card_to_that_page(self):
        from pathlib import Path
        from django.conf import settings
        js = (Path(settings.BASE_DIR) / 'dist' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("(taxaData.order_pages || {})[key]", js)


class RetiredNudibranchiaGroupRedirectTests(TestCase):
    def test_old_group_pages_redirect_to_the_whole_order_page(self):
        base = TaxonOrder.objects.create(name='Nudibranchia', sub_order='', taxonomic_order='3')
        for pk in (14, 16, 17):
            response = self.client.get(f'/order/{pk}/')
            self.assertEqual(response.status_code, 301, pk)
            self.assertEqual(response['Location'], f'/order/{base.pk}/')

    def test_other_missing_orders_still_404(self):
        TaxonOrder.objects.create(name='Nudibranchia', sub_order='', taxonomic_order='3')
        self.assertEqual(self.client.get('/order/999/').status_code, 404)
