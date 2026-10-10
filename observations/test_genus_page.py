import tempfile
from django.core.exceptions import ValidationError
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

    def test_back_button_returns_to_the_family_page(self):
        response = self.client.get(f'/genus/{self.genus.name}/')
        self.assertContains(response, f'<a class="back-button" href="/family/{self.family.name}/">')
        self.assertContains(response, 'חזרה למשפחה')

    def test_back_button_is_in_english_and_keeps_the_language(self):
        response = self.client.get(f'/genus/{self.genus.name}/?lang=en')
        self.assertContains(response, f'<a class="back-button" href="/family/{self.family.name}/?lang=en">')
        self.assertContains(response, 'Back to family')

    def test_back_button_goes_to_the_gallery_when_the_genus_has_no_family(self):
        self.genus.family = None
        self.genus.save()
        response = self.client.get(f'/genus/{self.genus.name}/')
        self.assertContains(response, '<a class="back-button" href="/">')
        self.assertContains(response, 'חזרה לגלריה')

    def test_family_page_has_a_back_button_to_its_order(self):
        url = f'/family/{self.family.name}/'
        response = self.client.get(url)
        self.assertContains(response, f'<a class="back-button" href="/order/{self.order.pk}/">')
        self.assertContains(response, 'חזרה לסדרה Nudibranchia')
        response = self.client.get(url + '?lang=en')
        self.assertContains(response, f'<a class="back-button" href="/order/{self.order.pk}/?lang=en">')
        self.assertContains(response, 'Back to order Nudibranchia')

    def test_order_page_has_a_back_button_to_the_gallery(self):
        url = f'/order/{self.order.pk}/'
        response = self.client.get(url)
        self.assertContains(response, '<a class="back-button" href="/">חזרה לכל הסדרות</a>')
        self.assertNotContains(response, 'חזרה לסדרה')
        response = self.client.get(url + '?lang=en')
        self.assertContains(response, '<a class="back-button" href="/?lang=en">Back to all orders</a>')

    def _taxon_sample(self, kind, owner=None, **names):
        self._video = getattr(self, '_video', 60000000000) + 1
        sample = Sample(owner=owner or self.owner, kind=kind, trip=self.trip, video_url=f'https://youtu.be/{self._video}', **names)
        sample.save_reviewed(actor=self.owner, approve=True)
        return sample

    def test_edit_button_for_those_who_may_edit_the_taxon_observation(self):
        from django.urls import reverse
        family_sample = self._taxon_sample(Sample.Kind.FAMILY, family='Chromodorididae')
        order_sample = self._taxon_sample(Sample.Kind.ORDER, order='Nudibranchia')
        pages = [(f'/genus/{self.genus.name}/', self.genus_sample), (f'/family/{self.family.name}/', family_sample),
                 (f'/order/{self.order.pk}/', order_sample)]
        for url, sample in pages:                                   # a visitor sees no edit button
            self.assertNotContains(self.client.get(url), 'class="edit-button"')
        self.client.force_login(self.owner)                          # a manager sees it, next to the back button
        for url, sample in pages:
            response = self.client.get(url + '?lang=he')     # the language persists in a cookie
            edit = reverse('observation-edit', args=[sample.pk])
            self.assertContains(response, f'<a class="edit-button" href="{edit}?next=')
            self.assertContains(response, 'עריכה</a>')
            self.assertContains(self.client.get(url + '?lang=en'), '>Edit</a>')
        # ... and the edit page really opens, returning to the taxon page after saving
        edit_url = self.client.get(f'/genus/{self.genus.name}/').context['edit_url']
        self.assertEqual(self.client.get(edit_url).status_code, 200)
        self.assertIn('next=%2Fgenus%2FChromodoris%2F', edit_url)

    def test_edit_button_only_for_the_observations_own_owner_or_a_manager(self):
        owner = User.objects.create_user('photographer', password='x')
        stranger = User.objects.create_user('stranger', password='x')
        own = self._taxon_sample(Sample.Kind.FAMILY, owner=owner, family='Chromodorididae')
        self.family.defining_sample = own; self.family.save()
        url = f'/family/{self.family.name}/'
        self.client.force_login(owner)
        self.assertContains(self.client.get(url), 'class="edit-button"')
        self.client.force_login(stranger)
        self.assertNotContains(self.client.get(url), 'class="edit-button"')
        own.soft_delete(self.owner)                                  # a deleted observation can't be edited by its owner
        self.family.refresh_from_db()
        self.client.force_login(owner)
        self.assertNotContains(self.client.get(url), 'class="edit-button"')

    def test_without_an_observation_of_its_own_a_manager_gets_a_new_one_for_the_taxon(self):
        from urllib.parse import urlencode
        self.client.force_login(self.owner)                          # superuser = manager
        self.family.description_he = 'תיאור קיים'; self.family.save()
        url = f'/family/{self.family.name}/'
        edit_url = self.client.get(url + '?lang=he').context['edit_url']
        self.assertEqual(edit_url, '/observations/new/?' + urlencode({'kind': 'family', 'name': 'Chromodorididae', 'next': url + '?lang=he'}))
        form = self.client.get(edit_url).context['form']             # kind and name filled in, with the family's current texts
        self.assertEqual((form.initial['kind'], form.initial['family']), ('family', 'Chromodorididae'))
        self.assertEqual(form.initial['taxon_description_he'], 'תיאור קיים')
        # saving it WITHOUT any picture or video of its own works, edits the family's texts and returns to the page
        data = {'kind': 'family', 'family': 'Chromodorididae', 'trip': str(self.trip.pk), 'site': '', 'taxon_description_he': 'תיאור חדש', 'next': url}
        response = self.client.post(edit_url, data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        self.assertTrue(response.url.startswith(url + '#obs-'))
        self.family.refresh_from_db()
        self.assertEqual(self.family.description_he, 'תיאור חדש')
        sample = Sample.objects.get(kind=Sample.Kind.FAMILY, family='Chromodorididae')
        self.assertFalse(sample.image or sample.video_url)
        # from now on the button leads to that observation
        self.assertTrue(self.client.get(url + '?lang=he').context['edit_url'].startswith(f'/observations/{sample.pk}/edit/'))
        self.assertEqual(self.client.get(f'/observations/?kind=family').status_code, 200)

    def test_species_without_media_still_requires_it(self):
        self.client.force_login(self.owner)
        response = self.client.post('/observations/new/', {'kind': 'species', 'species': 'Chromodoris annae', 'trip': str(self.trip.pk), 'site': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn('video_url', response.context['form'].errors)

    def test_new_taxon_observation_link_ignores_other_kinds_and_non_managers(self):
        photographer = User.objects.create_user('photographer', password='x')
        self.client.force_login(photographer)
        initial = self.client.get('/observations/new/?kind=family&name=Chromodorididae').context['form'].initial
        self.assertEqual((initial['kind'], initial['family']), ('species', ''))
        self.client.force_login(self.owner)
        initial = self.client.get('/observations/new/?kind=collection&name=x').context['form'].initial
        self.assertEqual(initial['kind'], 'species')

    def test_no_edit_button_without_an_observation_for_a_non_admin(self):
        photographer = User.objects.create_user('photographer', password='x')
        staff = User.objects.create_user('staff', password='x', is_staff=True)     # staff, but no change permission
        for user in (photographer, staff):
            self.client.force_login(user)
            self.assertNotContains(self.client.get(f'/family/{self.family.name}/'), 'class="edit-button"')
            self.assertNotContains(self.client.get(f'/order/{self.order.pk}/'), 'class="edit-button"')

    def test_species_page_has_back_and_edit_buttons(self):
        from django.urls import reverse
        url = f'/species/{self.area.slug}/'
        species_sample = Sample.objects.get(species=self.species)
        response = self.client.get(url + '?lang=he')                 # a visitor: back button only
        self.assertContains(response, f'<a class="back-button" href="/genus/{self.genus.name}/">חזרה לסוג Chromodoris</a>')
        self.assertNotContains(response, 'class="edit-button"')
        self.assertContains(self.client.get(url + '?lang=en'), f'href="/genus/{self.genus.name}/?lang=en">Back to genus Chromodoris</a>')
        self.client.force_login(self.owner)                          # a manager: edit button to the observation
        response = self.client.get(url + '?lang=he')
        self.assertContains(response, f'<a class="edit-button" href="{reverse("observation-edit", args=[species_sample.pk])}?next=')
        self.assertEqual(self.client.get(response.context['edit_url']).status_code, 200)
        stranger = User.objects.create_user('stranger', password='x')
        self.client.force_login(stranger)
        self.assertNotContains(self.client.get(url + '?lang=he'), 'class="edit-button"')
        species_sample.owner = stranger; species_sample.save(update_fields=['owner'])   # ...but the observation's own owner does
        self.assertContains(self.client.get(url + '?lang=he'), 'class="edit-button"')

    def test_species_page_back_button_goes_to_the_gallery_when_the_species_has_no_taxonomy_row(self):
        url = f'/species/{self.area.slug}/'
        self.genus.delete()
        response = self.client.get(url + '?lang=he')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a class="back-button" href="/">חזרה לגלריה</a>')
        self.assertNotContains(response, 'חזרה לסוג')

    def test_observation_cards_link_to_their_place_in_the_gallery(self):
        species_sample = Sample.objects.get(species=self.species)
        family_sample = self._taxon_sample(Sample.Kind.FAMILY, family='Chromodorididae')
        order_sample = self._taxon_sample(Sample.Kind.ORDER, order='Nudibranchia')
        lonely_family = TaxonFamily.objects.create(name='Emptyidae', order=self.order)
        lonely = self._taxon_sample(Sample.Kind.FAMILY, family='Emptyidae')   # no gallery species under it: no page
        self.client.force_login(self.owner)
        html = self.client.get('/observations/?lang=he').content.decode()
        def card(sample):
            start = html.index(f'<article id="obs-{sample.pk}"')
            return html[start:html.index('</article>', start)]
        self.assertIn(f'<a class="gallery-link" href="/species/{self.area.slug}/#obs-{species_sample.pk}">הצגה בגלריה</a>', card(species_sample))
        self.assertIn(f'href="/genus/Chromodoris/">הצגה בגלריה', card(self.genus_sample))
        self.assertIn('href="/family/Chromodorididae/">הצגה בגלריה', card(family_sample))
        self.assertIn(f'href="/order/{self.order.pk}/">הצגה בגלריה', card(order_sample))
        self.assertNotIn('gallery-link', card(lonely))
        self.assertIn(f'?lang=en#obs-{species_sample.pk}">Show in gallery', self.client.get('/observations/?lang=en').content.decode())
        # the link really lands on the observation: the species page anchors it
        self.assertContains(self.client.get(f'/species/{self.area.slug}/'), f'id="obs-{species_sample.pk}"')
        species_sample.soft_delete(self.owner)                      # a deleted observation is not in the gallery any more
        html = self.client.get('/observations/?lang=he').content.decode()
        self.assertNotIn(f'/species/{self.area.slug}/#obs-{species_sample.pk}', html)

    def test_taxon_observation_needs_no_trip_and_the_field_is_disabled(self):
        self.client.force_login(self.owner)
        form = self.client.get('/observations/new/?kind=genus&name=Chromodoris').context['form']
        for name in ('trip', 'site', 'site_other', 'day'):
            self.assertTrue(form.fields[name].disabled, name)
        # saved without a trip -- an order/family/genus observation describes a taxon, not a dive
        response = self.client.post('/observations/new/', {'kind': 'order', 'order': 'Nudibranchia', 'trip': '', 'site': '',
                                                           'taxon_description_he': 'תיאור', 'next': '/'})
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        sample = Sample.objects.get(kind=Sample.Kind.ORDER, order='Nudibranchia')
        self.assertIsNone(sample.trip)
        sample.save_reviewed(actor=self.owner, approve=True)         # ... and can be approved and published like that
        self.assertEqual(sample.status, 'published')
        # a posted trip is ignored for taxon kinds (the field is disabled)
        other = self.client.post('/observations/new/', {'kind': 'family', 'family': 'Chromodorididae', 'trip': str(self.trip.pk), 'site': '', 'next': '/'})
        self.assertIsNone(Sample.objects.get(kind=Sample.Kind.FAMILY, family='Chromodorididae').trip)
        # the pages and lists that show observations cope with a trip-less one
        self.assertEqual(self.client.get('/observations/').status_code, 200)
        self.assertEqual(self.client.get(f'/order/{self.order.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/admin/observations/sample/{sample.pk}/change/').status_code, 200)
        self.assertEqual(self.client.get('/observations/trips/').status_code, 200)

    def test_editing_a_taxon_observation_keeps_the_trip_it_already_has(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.genus_sample.trip_id, self.trip.pk)
        response = self.client.post(f'/observations/{self.genus_sample.pk}/edit/', {
            'kind': 'genus', 'genus': 'Chromodoris', 'video_url': self.genus_sample.video_url, 'site': '', 'next': '/'})
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        self.genus_sample.refresh_from_db()
        self.assertEqual(self.genus_sample.trip_id, self.trip.pk)

    def test_species_and_collection_observations_still_need_a_trip(self):
        self.client.force_login(self.owner)
        response = self.client.post('/observations/new/', {'kind': 'species', 'species': 'Chromodoris annae', 'video_url': 'https://youtu.be/99999999999', 'trip': '', 'site': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn('trip', response.context['form'].errors)
        self.assertFalse(response.context['form'].fields['trip'].disabled)
        self.assertIn('required', response.context['form']['trip'].as_widget())
        response = self.client.post('/observations/new/', {'kind': 'collection', 'title': 'x', 'video_url': 'https://youtu.be/88888888888', 'trip': '', 'site': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn('trip', response.context['form'].errors)

    def test_the_save_message_shows_on_the_page_the_edit_returns_to_and_only_once(self):
        self.client.force_login(self.owner)
        for url in (f'/family/{self.family.name}/', f'/genus/{self.genus.name}/', f'/species/{self.area.slug}/'):
            sample = self.genus_sample if '/genus/' in url else Sample.objects.get(species=self.species)
            response = self.client.post(f'/observations/{sample.pk}/edit/', {
                'kind': sample.kind, 'genus': sample.genus, 'species': 'annae' if sample.species_id else '', 'trip': str(self.trip.pk), 'site': '',
                'video_url': sample.video_url, 'next': url}, follow=True)
            self.assertContains(response, 'class="notice', msg_prefix=url)
            self.assertNotContains(self.client.get(url), 'class="notice')       # shown once, then gone
        family_sample = self._taxon_sample(Sample.Kind.FAMILY, family='Chromodorididae')
        self.client.post(f'/observations/{family_sample.pk}/edit/', {'kind': 'family', 'family': 'Chromodorididae', 'next': f'/family/{self.family.name}/'})
        self.assertContains(self.client.get(f'/family/{self.family.name}/'), 'התצפית נשמרה')

    def test_card_shows_the_observation_count_when_the_species_has_several(self):
        url = f'/genus/{self.genus.name}/'
        self.assertNotContains(self.client.get(url), 'count-badge" aria-hidden')      # one observation: no badge
        second = Sample(owner=self.owner, trip=self.trip, species=self.species, video_url='https://youtu.be/22222222222')
        second.save_reviewed()
        gone = Sample(owner=self.owner, trip=self.trip, species=self.species, video_url='https://youtu.be/33333333333')
        gone.save_reviewed(); gone.soft_delete(self.owner)                            # a deleted one is not counted
        response = self.client.get(url)
        self.assertContains(response, '<span class="count-badge" aria-hidden="true">2</span>')
        self.assertContains(response, '<span>2 תצפיות</span>')

    def test_species_page_shows_the_full_name_on_each_observation_that_differs(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        cf = Sample(owner=self.owner, trip=self.trip, species=self.species, identification_qualifier='cf.',
                    video_url='https://youtu.be/44444444444')
        cf.save_reviewed()
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertEqual(html.count('class="sample-name"'), 1)           # the plain observation would only repeat the h1
        self.assertIn('<i>Chromodoris</i> cf. <i>annae</i>', html)       # the qualifier is visible on that observation only
        self.assertEqual(html.count('cf. <i>annae</i>'), 1)

    def test_species_page_heading_is_italic_with_the_author_in_roman_and_no_name_in_the_breadcrumb(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn('<h1 dir="ltr"><i>Chromodoris annae</i> <span class="species-author">Bergh, 1877</span></h1>', html)
        start = html.index('class="breadcrumb"'); crumb = html[start:html.index('</nav>', start)]
        self.assertIn('Chromodoris</a>', crumb)               # the genus link stays
        self.assertNotIn('aria-current', crumb)               # the species name is not repeated there
        self.assertNotIn('annae', crumb)

    def test_observation_names_above_the_photos_are_italic_except_the_qualifier(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        Sample(owner=self.owner, trip=self.trip, species=self.species, identification_qualifier='cf.',
               video_url='https://youtu.be/55555555555').save_reviewed()
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn('<i>Chromodoris</i> cf. <i>annae</i> <span class="sample-author">Bergh, 1877</span>', html)
        self.assertEqual(html.count('class="sample-name"'), 1)
        self.assertNotIn('<i>Chromodoris annae</i> Bergh, 1877', html)   # a plain name is not repeated above its photo

    def test_species_page_heading_is_one_colour_and_small(self):
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn('.species-summary h1 .species-author{font-style:normal;color:inherit}', html)   # base.css paints every h1 span teal
        self.assertIn('font-size:24px', html.split('.species-summary h1{')[1].split('}')[0])
        # `.card h3{font-size:24px}` in styles.css would win over a bare `.sample-name`, so the rule carries the card
        self.assertIn('font-size:16px', html.split('.card h3.sample-name{')[1].split('}')[0])
        self.assertIn('display:block;margin-top:2px;font-size:11px', html.split('.card h3.sample-name .sample-author{')[1].split('}')[0])

    def test_observation_name_sits_below_the_photo_with_a_small_author(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        Sample(owner=self.owner, trip=self.trip, species=self.species, identification_qualifier='cf.', life_stage='juv.',
               video_url='https://youtu.be/66666666666').save_reviewed()
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertLess(html.index('<img src', html.index('class="grid"')), html.index('class="sample-name"'))
        self.assertIn('<h3 class="sample-name" dir="ltr"><i>Chromodoris</i> cf. <i>annae</i> '
                      '<span class="sample-author">Bergh, 1877</span> juv.</h3>', html)

    def test_genus_page_cards_show_the_species_name_in_italics(self):
        self.species.species = 'annae'; self.species.save()
        self.assertContains(self.client.get(f'/genus/{self.genus.name}/'), '<i>Chromodoris annae</i>')

    def test_genus_page_cards_put_the_author_in_a_small_span_after_the_name(self):
        self.species.species = 'annae'; self.species.author = 'Bergh, 1877'; self.species.save()
        html = self.client.get(f'/genus/{self.genus.name}/').content.decode()
        self.assertIn('<i>Chromodoris annae</i> <span class="card-author">Bergh, 1877</span></h3>', html)   # styled block by styles.css
        self.species.author = ''; self.species.save()
        html = self.client.get(f'/genus/{self.genus.name}/').content.decode()
        self.assertNotIn('card-author', html)

    def test_genus_page_without_a_defining_sample_falls_back_to_a_species_photo(self):
        # Breadcrumbs and gallery panels always link to the genus page, so a genus with no
        # media of its own still gets a page, using one of its species' photo/video.
        self.genus_sample.soft_delete(self.owner)  # only genus-kind sample -- see Sample.save
        self.genus.refresh_from_db()
        self.assertIsNone(self.genus.defining_sample_id)
        response = self.client.get(f'/genus/{self.genus.name}/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['image_url'] or response.context['video_id'])

    def test_family_kind_sample_becomes_the_family_page_media(self):
        sample = Sample(owner=self.owner, kind=Sample.Kind.FAMILY, family='Chromodorididae', order='Nudibranchia',
                        trip=self.trip, video_url='https://youtu.be/44444444444')
        sample.save_reviewed(actor=self.owner, approve=True)
        self.family.refresh_from_db()
        self.assertEqual(self.family.defining_sample_id, sample.pk)
        self.assertEqual(self.client.get('/family/Chromodorididae/').context['video_id'], '44444444444')
        sample.soft_delete(self.owner)   # a stale family-kind pick is cleared; the page falls back to a species
        self.family.refresh_from_db()
        self.assertIsNone(self.family.defining_sample_id)
        self.assertEqual(self.client.get('/family/Chromodorididae/').status_code, 200)

    def test_observation_filter_offers_every_record_type(self):
        self.client.force_login(self.owner)
        html = self.client.get('/observations/').content.decode()
        for value in ('species', 'collection', 'genus', 'family', 'order'):
            self.assertIn(f'<option value="{value}"', html)

    def test_order_and_family_pages_list_the_species(self):
        from observations.gallery_data import TaxonResolver
        order, family, _ = TaxonResolver().resolve(self.species)
        if order:
            response = self.client.get(f'/order/{order.pk}/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'/species/{self.area.slug}/')
        if family:
            response = self.client.get(f'/family/{family.name}/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'/genus/{self.genus.name}/')
        self.assertEqual(self.client.get('/family/Nonexistentidae/').status_code, 404)

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


class GenusPageEnglishTests(TestCase):
    def setUp(self):
        GenusPageTests.setUp(self)

    def test_english_page_has_no_hebrew_section_title_or_meta_fallback(self):
        html = self.client.get(f'/genus/{self.genus.name}/?lang=en').content.decode()
        self.assertIn('Species in this genus', html)
        self.assertNotIn('מינים בסוג זה', html)
        self.assertIn('the sea slugs website', html)       # the meta description fallback
        self.assertIn('מינים בסוג זה', self.client.get(f'/genus/{self.genus.name}/?lang=he').content.decode())


class GenusIdentificationFileTests(TestCase):
    """A genus can carry ONE identification file -- a PDF or an image (a diagram, plate of
    photos or key for telling its species apart) -- with a caption and a source."""
    PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 20

    def setUp(self):
        GenusPageTests.setUp(self)

    def attach(self, filename, data, **extra):
        self.genus.identification_file.save(filename, ContentFile(data), save=False)
        for key, value in extra.items():
            setattr(self.genus, key, value)
        self.genus.save()

    def test_page_without_a_file_has_no_identification_section(self):
        self.assertNotContains(self.client.get(f'/genus/{self.genus.name}/'), 'id="identification"')

    def test_image_file_is_shown_inline_with_caption_and_source(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.attach('key.png', self.PNG, identification_caption='Species of Hypselodoris', identification_source='Gosliner 2015')
            response = self.client.get(f'/genus/{self.genus.name}/')
            self.assertContains(response, 'id="identification"')
            self.assertContains(response, f'<img src="/genus/{self.genus.name}/identification/"')
            self.assertContains(response, 'Species of Hypselodoris')
            self.assertContains(response, 'Gosliner 2015')

    def test_caption_follows_the_page_language_with_a_fallback_to_the_other(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.attach('key.png', self.PNG, identification_caption='כיתוב בעברית', identification_caption_en='English caption')
            self.assertContains(self.client.get(f'/genus/{self.genus.name}/'), 'כיתוב בעברית')
            self.assertNotContains(self.client.get(f'/genus/{self.genus.name}/'), 'English caption')
            self.assertContains(self.client.get(f'/genus/{self.genus.name}/?lang=en'), 'English caption')
            self.assertNotContains(self.client.get(f'/genus/{self.genus.name}/?lang=en'), 'כיתוב בעברית')
            self.genus.identification_caption_en = ''; self.genus.save()
            self.assertContains(self.client.get(f'/genus/{self.genus.name}/?lang=en'), 'כיתוב בעברית')

    def test_pdf_file_is_shown_as_a_link_not_an_image(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.attach('key.pdf', b'%PDF-1.4 test')
            response = self.client.get(f'/genus/{self.genus.name}/')
            self.assertContains(response, 'class="identification-pdf"')
            self.assertNotContains(response, 'class="identification-image"')

    def test_file_alone_still_shows_the_identification_section_in_english(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.attach('key.pdf', b'%PDF-1.4 test')
            response = self.client.get(f'/genus/{self.genus.name}/?lang=en')
            self.assertContains(response, 'Identification key (PDF)')

    def test_identification_view_serves_each_type_with_its_content_type(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.attach('key.png', self.PNG)
            response = self.client.get(f'/genus/{self.genus.name}/identification/')
            self.assertEqual((response.status_code, response['Content-Type']), (200, 'image/png'))
            self.assertIn('inline', response['Content-Disposition'])
            self.genus.identification_file.delete(save=False)
            self.attach('key.pdf', b'%PDF-1.4 test')
            response = self.client.get(f'/genus/{self.genus.name}/identification/')
            self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_identification_view_404s_without_a_file(self):
        self.assertEqual(self.client.get(f'/genus/{self.genus.name}/identification/').status_code, 404)

    def test_only_pdf_and_image_files_are_accepted(self):
        for good in ('a.pdf', 'a.jpg', 'a.JPEG', 'a.png', 'a.webp', 'a.gif'):
            self.genus.identification_file.name = good
            self.genus.full_clean(exclude=['family', 'defining_sample'])
        for bad in ('a.docx', 'a.txt', 'a.svg', 'a.exe'):
            self.genus.identification_file.name = bad
            with self.assertRaises(ValidationError, msg=bad):
                self.genus.full_clean(exclude=['family', 'defining_sample'])

    def test_oversized_file_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import validate_identification_file_size
        validate_identification_file_size(SimpleUploadedFile('a.pdf', b'x' * 1024))
        with self.assertRaises(ValidationError):
            validate_identification_file_size(SimpleUploadedFile('a.pdf', b'x' * (20 * 1024 * 1024 + 1)))

    def test_a_stored_file_missing_from_disk_does_not_break_saving_the_genus(self):
        # e.g. right after a database replace brought the row but not the media file
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.genus.identification_file.name = 'identification/genera/gone.png'
            self.genus.full_clean(exclude=['family', 'defining_sample'])

    def test_sources_are_listed_on_the_genus_page(self):
        self.genus.sources = 'https://www.marinespecies.org/aphia.php?p=taxdetails&id=1\nGosliner et al. 2015'
        self.genus.save()
        response = self.client.get(f'/genus/{self.genus.name}/')
        self.assertContains(response, 'class="species-sources"')
        self.assertContains(response, 'marinespecies.org ↗')
        self.assertContains(response, 'Gosliner et al. 2015')

    def test_admin_form_offers_the_description_identification_and_file_fields(self):
        self.client.force_login(self.owner)
        response = self.client.get(f'/admin/observations/taxongenus/{self.genus.pk}/change/')
        for name in ('description_he', 'description_en', 'identification_he', 'identification_en',
                     'identification_file', 'identification_caption', 'identification_source'):
            self.assertContains(response, f'name="{name}"')


class PhotoBeforeVideoTests(TestCase):
    """On a genus, family or order page that has both a photo and a video, the photo is the hero."""
    setUp = GenusPageTests.setUp                        # the same fixtures, without re-running that class's tests
    _taxon_sample = GenusPageTests._taxon_sample

    def _both(self, sample):
        Sample.objects.filter(pk=sample.pk).update(image='observations/hero.jpg')
        sample.refresh_from_db()
        self.assertTrue(sample.image and sample.video_url)

    def assert_photo_hero(self, url, sample):
        html = self.client.get(url).content.decode()
        hero = html[html.index('class="species-media"'):html.index('class="species-summary"')]
        self.assertIn(f'<img src="/observations/{sample.pk}/photo/"', hero)
        self.assertNotIn('<iframe', hero)

    def test_genus_page(self):
        html = self.client.get(f'/genus/{self.genus.name}/').content.decode()
        self.assertIn('<iframe', html[html.index('class="species-media"'):html.index('class="species-summary"')])   # video only: the video
        self._both(self.genus_sample)
        self.assert_photo_hero(f'/genus/{self.genus.name}/', self.genus_sample)

    def test_family_and_order_pages(self):
        family = self._taxon_sample(Sample.Kind.FAMILY, family='Chromodorididae')
        order = self._taxon_sample(Sample.Kind.ORDER, order='Nudibranchia')
        for url, sample in ((f'/family/{self.family.name}/', family), (f'/order/{self.order.pk}/', order)):
            html = self.client.get(url).content.decode()
            self.assertIn('<iframe', html[html.index('class="species-media"'):html.index('class="species-summary"')])
            self._both(sample)
            self.assert_photo_hero(url, sample)
