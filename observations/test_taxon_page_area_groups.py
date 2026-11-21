import re

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, TaxonGenus


class TaxonPageAreaGroupsTests(TestCase):
    """On a genus page (and the family / order pages) a species observed in several areas is one card, like in the
    gallery (app.js groupSpeciesByArea; gallery_data.group_area_cards): its Mediterranean card when it has one, else the
    one with the most observations, with an "N areas" button and no count of its own; its other area cards follow it,
    hidden until the button opens them. A species in one area, and an unmarked "sp.", stay ordinary cards."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        israel = Country.objects.create(name='ישראל', name_en='Israel')
        australia = Country.objects.create(name='אוסטרליה', name_en='Australia')
        med = Sea.objects.create(name='הים התיכון', name_en='Mediterranean', url_code='med')
        coral = Sea.objects.create(name='ים האלמוגים', name_en='Coral Sea', url_code='coral')
        self.med_trip = DiveTrip.objects.create(code='I', title='i', year=2026, month=1, country=israel,
                                                region=Region.objects.create(name='מכמורת', country=israel, sea=med))
        self.aus_trip = DiveTrip.objects.create(code='Z', title='z', year=1998, month=1, country=australia,
                                                region=Region.objects.create(name='Lady Elliot', country=australia, sea=coral))
        TaxonGenus.objects.create(name='Aplysia')
        self.n = 0

    def observe(self, name, trip):
        genus, epithet = name.split(' ', 1)
        species = Species.objects.filter(scientific_name=name).first() or Species.objects.create(
            scientific_name=name, genus=genus, species=epithet)
        self.n += 1
        Sample(owner=self.owner, species=species, trip=trip, video_url=f'https://youtu.be/3000000000{self.n}').save_reviewed()

    def cards(self):
        html = self.client.get('/genus/Aplysia/?lang=he').content.decode()
        return re.findall(r'<article class="(card[^"]*)"[^>]*?(hidden)?>', html), html

    def test_one_card_per_species_with_an_areas_button(self):
        self.observe('Aplysia dactylomela', self.aus_trip)
        self.observe('Aplysia dactylomela', self.med_trip)
        self.observe('Aplysia argus', self.aus_trip)
        cards, html = self.cards()
        self.assertEqual(cards, [('card', ''), ('card area-group', ''), ('card area-member', 'hidden')])
        self.assertIn('2 אזורים ▾', html)
        group = html.index('card area-group')
        self.assertIn('ישראל', html[group:html.index('card area-member')])      # the Mediterranean card is the one shown
        self.assertIn('area-group-toggle', html)
        self.assertIn("closest('.area-group-toggle[data-group]')", html)

    def test_single_area_species_and_bare_sp_are_ordinary_cards(self):
        self.observe('Aplysia argus', self.aus_trip)
        self.observe('Aplysia sp.', self.aus_trip)
        self.observe('Aplysia sp.', self.med_trip)
        cards, html = self.cards()
        self.assertEqual([c for c, _ in cards], ['card', 'card', 'card'])
        self.assertNotIn('area-group-toggle" data-group', html)
