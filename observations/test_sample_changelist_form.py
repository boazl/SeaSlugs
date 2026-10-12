"""The Samples admin list is editable: a row whose data fails the model's validation on a field the list
does not show (media, trip...) must give a row error, never a server error; and a deleted row never blocks."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .forms import SampleChangelistForm
from .models import Country, DiveTrip, Region, Sample, Sea, Species


class SampleChangelistFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('boss', password='test-password-x1')
        country = Country.objects.create(name='ישראל'); sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        self.species = Species.objects.create(scientific_name='Cyerce basi', genus='Cyerce', species='basi')
        self.live = Sample.objects.create(owner=self.user, trip=self.trip, species=self.species, video_url='https://youtu.be/abcdefghijk')
        self.duplicate = Sample.objects.create(owner=self.user, trip=self.trip, species=self.species)   # no media, same species and trip

    def form(self, sample):
        data = {'order': 'Sacoglossa', 'family': 'Caliphyllidae', 'genus': 'Cyerce', 'species': 'basi',
                'identification_qualifier': '', 'life_stage': ''}
        return SampleChangelistForm(data, instance=sample)

    def test_errors_on_fields_the_list_does_not_have_become_row_errors(self):
        form = self.form(self.duplicate)
        self.assertFalse(form.is_valid())                         # used to raise ValueError (HTTP 500)
        text = ' '.join(form.non_field_errors())
        self.assertIn('YouTube', text)

    def test_a_deleted_row_does_not_block_saving_the_list(self):
        self.duplicate.deleted_at = timezone.now(); self.duplicate.save(update_fields=['deleted_at'])
        form = self.form(Sample.objects.get(pk=self.duplicate.pk))
        self.assertTrue(form.is_valid(), form.errors)

    def test_a_valid_live_row_still_saves(self):
        self.duplicate.delete()
        form = self.form(self.live)
        self.assertTrue(form.is_valid(), form.errors)
