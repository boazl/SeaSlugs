from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species


class PhotoMissingFileTests(TestCase):
    """/observations/<pk>/photo/: an observation whose photo file is not in this environment's storage (recorded, but
    not transferred yet -- /admin/images/) answers 404, not a server error."""

    def test_missing_file_is_not_found(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        trip = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph,
                                       region=Region.objects.create(name='Romblon', country=ph, sea=sea))
        species = Species.objects.create(scientific_name='Aegires sp. 12', genus='Aegires', species='sp. 12')
        sample = Sample(owner=owner, species=species, trip=trip, image='observations/not-here-at-all.jpg', status='published')
        Sample.objects.bulk_create([sample])
        sample = Sample.objects.get(species=species)
        self.assertEqual(self.client.get(f'/observations/{sample.pk}/photo/').status_code, 404)
