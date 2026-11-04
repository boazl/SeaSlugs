"""The species pictures under each trip on the public trips page open that observation on its species page."""
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea


class TripSpeciesLinkTests(TestCase):
    """A species picture in a trip's list links to /species/<slug>/#obs-<pk> (in the page's language), in the same
    window -- not to the bare photo or to YouTube."""

    def setUp(self):
        owner = User.objects.create_user('diver', password='pw-test-12345')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Eilat', year=2026, country=country, region=region, code='e1')
        species = Species.objects.create(scientific_name='Phyllidia ocellata', genus='Phyllidia', species='ocellata',
                                         author='Cuvier, 1804', family='Phyllidiidae', order='Nudibranchia')
        self.sample = Sample(owner=owner, trip=trip, species=species, video_url='https://youtu.be/aaaaaaaaaaa')
        self.sample.save_reviewed()
        self.slug = SpeciesArea.objects.get().slug

    def thumb(self, query=''):
        html = self.client.get('/observations/trips/' + query).content.decode()
        return html.split('class="trip-thumb"')[1].split('>')[0]

    def test_opens_the_observation(self):
        link = self.thumb()
        self.assertIn(f'href="/species/{self.slug}/#obs-{self.sample.pk}"', link)
        self.assertNotIn('youtu', link)
        self.assertNotIn('target="_blank"', link)

    def test_keeps_the_language(self):
        self.assertIn(f'href="/species/{self.slug}/?lang=en#obs-{self.sample.pk}"', self.thumb('?lang=en'))
