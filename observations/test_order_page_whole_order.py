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
        self.superfamily = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Doridina', superfamily='Chromodoridoidea', name_he='חשופיות נדן')
        for i, (order, family, genus, sp) in enumerate([
                (self.base, 'Hexabranchidae', 'Hexabranchus', 'sanguineus'),
                (self.group, 'Chromodorididae', 'Chromodoris', 'annae'),
                (self.single, 'Plakobranchidae', 'Plakobranchus', 'ocellatus')]):
            fam = TaxonFamily.objects.create(name=family, order=order, superfamily='Chromodoridoidea' if family == 'Chromodorididae' else '')
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

    def test_only_the_whole_order_page_has_the_edit_observation_button(self):
        """An order observation is the whole order's, so a sub-order page does not offer to edit it."""
        self.client.login(username='manager', password='test-password')
        whole = self.client.get(reverse('order-page', args=[self.base.pk])).content.decode()
        sub = self.client.get(reverse('order-page', args=[self.group.pk])).content.decode()
        self.assertIn('עריכת תצפית', whole)
        self.assertNotIn('עריכת תצפית', sub)
        self.assertIn('עריכת התת-סדרה', sub)

    def test_a_sub_order_page_says_sub_order_and_links_back_to_the_whole_order(self):
        sub = self.client.get(reverse('order-page', args=[self.group.pk])).content.decode()
        whole = self.client.get(reverse('order-page', args=[self.base.pk])).content.decode()
        self.assertIn('>תת-סדרה</span>', sub)
        self.assertIn(f'<a class="back-button" href="/order/{self.base.pk}/">חזרה לסדרה חשופיות</a>', sub)
        self.assertIn('>סדרה</span>', whole)
        self.assertNotIn('חזרה לסדרה', whole)
        english = self.client.get(reverse('order-page', args=[self.group.pk]) + '?lang=en').content.decode()
        self.assertIn('>Sub-order</span>', english)

    def test_a_family_page_links_back_to_its_sub_order_and_its_order(self):
        family = self.client.get('/family/Chromodorididae/').content.decode()
        row = family[family.index('class="back-row"'):]
        row = row[:row.index('</p>')]
        self.assertIn(f'href="/order/{self.group.pk}/">חזרה לתת-סדרה Doridina</a>', row)
        self.assertIn(f'href="/order/{self.base.pk}/">חזרה לסדרה חשופיות</a>', row)
        self.assertLess(row.index('חזרה לתת-סדרה'), row.index('חזרה לסדרה'))
        hexa = self.client.get('/family/Hexabranchidae/').content.decode()    # in the order's own row: just the order
        self.assertIn('חזרה לסדרה חשופיות', hexa)
        self.assertNotIn('חזרה לתת-סדרה', hexa)
        self.assertIn(f'href="/order/{self.group.pk}/?lang=en"', self.client.get('/family/Chromodorididae/?lang=en').content.decode())

    def test_rank_follows_the_sub_order_and_superfamily_columns(self):
        self.assertEqual([o.rank for o in (self.base, self.group, self.superfamily)], ['order', 'suborder', 'superfamily'])
        row = TaxonOrder(name='Runcinida', superfamily='Runcinoidea')
        row.save()
        self.assertEqual(TaxonOrder.objects.get(pk=row.pk).rank, 'superfamily')
        row.superfamily = ''
        row.save(update_fields=['superfamily'])
        self.assertEqual(TaxonOrder.objects.get(pk=row.pk).rank, 'order')
        self.assertEqual(str(self.superfamily), 'Nudibranchia / Doridina / Chromodoridoidea')

    def test_a_superfamily_page_holds_its_families_species_and_says_superfamily(self):
        response = self.client.get(reverse('order-page', args=[self.superfamily.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.names(response), ['Chromodoris'])
        html = response.content.decode()
        self.assertIn('>על-משפחה</span>', html)
        self.assertIn('frame-superfamily', html)
        self.assertIn('<h2>משפחות</h2>', html)
        back = html[html.index('class="back-row"'):]
        back = back[:back.index('</p>')]
        self.assertLess(back.index('חזרה לתת-סדרה Doridina'), back.index('חזרה לסדרה חשופיות'))   # nearest level first
        self.assertNotIn('עריכת תצפית', back)

    def test_pages_list_the_next_level_down(self):
        whole = self.client.get(reverse('order-page', args=[self.base.pk])).content.decode()
        self.assertIn('<h2>קבוצות טקסונומיות</h2>', whole)            # a sub-order (Doridina) and a family (Hexabranchidae)
        sub = self.client.get(reverse('order-page', args=[self.group.pk])).content.decode()
        self.assertIn('<h2>על-משפחות</h2>', sub)
        self.assertIn(f'href="/order/{self.superfamily.pk}/"', sub)

    def test_a_family_page_links_back_to_its_superfamily_first(self):
        html = self.client.get('/family/Chromodorididae/').content.decode()
        row = html[html.index('class="back-row"'):]
        row = row[:row.index('</p>')]
        self.assertLess(row.index('חזרה לעל-משפחה חשופיות נדן'), row.index('חזרה לתת-סדרה'))
        self.assertIn(f'href="/order/{self.superfamily.pk}/">חזרה לעל-משפחה', row)
        crumbs = html[html.index('class="breadcrumb"'):]
        self.assertIn('חשופיות נדן', crumbs[:crumbs.index('</nav>')])

    def test_only_an_order_row_can_be_a_familys_order(self):
        self.assertEqual(TaxonFamily._meta.get_field('order').remote_field.limit_choices_to, {'superfamily': ''})

    def test_admin_has_a_view_the_page_button_for_each_level(self):
        """As the species admin has: next to Save, a link to the public page of the order / sub-order / superfamily /
        family / genus -- only when that page exists."""
        self.client.login(username='manager', password='test-password')
        empty = TaxonOrder.objects.create(name='Pteropoda', sub_order='Gymnosomata')      # no gallery species: no page
        for row, label in ((self.base, 'צפייה בדף הסדרה'), (self.group, 'צפייה בדף התת-סדרה'), (self.superfamily, 'צפייה בדף העל-משפחה')):
            html = self.client.get(reverse('admin:observations_taxonorder_change', args=[row.pk])).content.decode()
            self.assertIn('name="_save_and_view" value="0" class="button site-page-link"', html)
            self.assertIn('שמירה ו' + label, html)
        self.assertNotIn('site-page-link', self.client.get(reverse('admin:observations_taxonorder_change', args=[empty.pk])).content.decode())
        family = TaxonFamily.objects.get(name='Chromodorididae')
        html = self.client.get(reverse('admin:observations_taxonfamily_change', args=[family.pk])).content.decode()
        self.assertIn('שמירה וצפייה בדף המשפחה', html)
        genus = TaxonGenus.objects.get(name='Chromodoris')
        html = self.client.get(reverse('admin:observations_taxongenus_change', args=[genus.pk])).content.decode()
        self.assertIn('שמירה וצפייה בדף הסוג', html)
        # the button saves the row and then opens its page (not the table)
        url = reverse('admin:observations_taxonfamily_change', args=[family.pk])
        form = self.client.get(url).context['adminform'].form
        from django import forms as dj_forms
        data = {name: ('' if value is None else value) for name, value in form.initial.items()
                if name in form.fields and not isinstance(form.fields[name], dj_forms.FileField)}
        data.update({'name_he': 'משפחה בדוקה', '_save_and_view': '0'})
        response = self.client.post(url, data)
        self.assertRedirects(response, '/family/Chromodorididae/', fetch_redirect_response=False)
        family.refresh_from_db(); self.assertEqual(family.name_he, 'משפחה בדוקה')

    def test_every_level_page_has_a_back_to_the_gallery_button_that_restores_the_view(self):
        """"/?restore=1": the gallery comes back to the view the visitor left (same rank, taxon, filters, place)."""
        pages = [reverse('order-page', args=[row.pk]) for row in (self.base, self.group, self.superfamily)] + [
            '/family/Chromodorididae/', '/genus/Chromodoris/', '/species/' + Species.objects.get(scientific_name='Chromodoris annae').areas.first().slug + '/']
        for url in pages:
            self.assertIn('href="/?restore=1">חזרה לגלריה</a>', self.client.get(url).content.decode(), url)
        self.assertIn('href="/?restore=1&amp;lang=en">Back to the gallery</a>', self.client.get('/genus/Chromodoris/?lang=en').content.decode())


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


