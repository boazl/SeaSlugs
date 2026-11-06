"""The admin import tools (folder import of photos, video import) pick the dive trip exactly like the observation
form: country / region / site / year filters (initTripPicker, _trip_picker_script.html) above a full-width trip
list labelled "title (region · country · month/year)", the "add a trip" link that comes back with the new trip
selected (?trip=), and no taxon library trips."""
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sea, taxon_library_trip


class TripPickerToolsTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('manager', password='pw'))
        country = Country.objects.create(name='ישראל'); sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(code='J7', title='אילת 2026', year=2026, month=6, country=country, region=region,
                                            local_video_folder='/Users/x/Video Output')
        taxon_library_trip('genus')

    def check(self, url):
        html = self.client.get(url).content.decode()
        self.assertIn('initTripPicker(document.getElementById(\'id_trip\')', html)
        self.assertIn('function initTripPicker', html)
        self.assertIn('<select name="trip" id="id_trip" required style="width:100%">', html)
        self.assertIn(f'<option value="{self.trip.pk}" data-folder="/Users/x/Video Output" selected>אילת 2026 (אילת · ישראל · 6/2026)</option>', html)
        self.assertIn('trip-add-link', html)
        self.assertNotIn('ספריית זיהוי לפי סוג', html)
        self.assertIn('"filters"', html)

    def test_folder_import(self):
        self.check(f'/admin/images/folder/?trip={self.trip.pk}')

    def test_video_import(self):
        self.check(f'/admin/local-videos/import/?trip={self.trip.pk}')

    def test_observation_form_still_uses_it(self):
        html = self.client.get('/observations/new/').content.decode()
        self.assertIn('function initTripPicker', html); self.assertIn('initTripPicker(tripEl,locations);', html)
