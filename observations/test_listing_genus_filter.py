from django.test import TestCase
from django.contrib.auth.models import User
from .models import Sample, Species, Country, Sea, Region, DiveTrip


class ListingGenusFilterTests(TestCase):
    """The observations listing's own genus filter (observations/views.py's listing())
    queries Species.genus directly -- separate from, and previously inconsistent with,
    config.views' resolve_taxon_chain, which already works around a handful of species
    having a blank genus column even though their scientific name clearly starts with one
    (real data: "Cyerce basi" with genus='')."""
    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='testing')
        country = Country.objects.create(name='Israel'); sea = Sea.objects.create(name='Red Sea')
        region = Region.objects.create(name='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Eilat trip', year=2026, country=country, region=region)
        self.client.force_login(self.user)

    def _published_sample(self, species, video_id):
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=species,
                         video_url=f'https://youtu.be/{video_id}')
        sample.save_reviewed(actor=self.user, approve=True)
        return sample

    def test_genus_search_finds_a_species_with_a_blank_genus_column(self):
        # Regression: without the fallback, this species' own sample never showed up in a
        # genus search for it at all -- exactly what happened with the real "Cyerce basi"
        # record (genus='', scientific_name='Cyerce basi').
        species = Species.objects.create(scientific_name='Cyerce basi', genus='', species='')
        self._published_sample(species, '11111111111')
        response = self.client.get('/observations/', {'genus': 'Cyerce'})
        self.assertContains(response, 'Cyerce basi')

    def test_genus_search_still_matches_a_properly_filled_genus_column(self):
        species = Species.objects.create(scientific_name='Cyerce nigra', genus='Cyerce', species='nigra')
        self._published_sample(species, '22222222222')
        response = self.client.get('/observations/', {'genus': 'Cyerce'})
        self.assertContains(response, 'Cyerce nigra')

    def test_blank_genus_fallback_only_matches_the_scientific_names_leading_word(self):
        # The fallback must act like a genus (the first word of a binomial name), not match
        # a search term appearing anywhere else in the scientific name.
        species = Species.objects.create(scientific_name='Something elseus', genus='', species='')
        self._published_sample(species, '33333333333')
        response = self.client.get('/observations/', {'genus': 'elseus'})
        self.assertNotContains(response, 'Something elseus')
