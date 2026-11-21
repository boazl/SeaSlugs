from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea


class SpeciesExtraObservationLinkTests(TestCase):
    """On a species page, an extra observation's card ("תצפיות נוספות") opens that observation's edit page for a
    visitor who may edit it (a manager: any; an owner: their own) -- with "View the photo" / "Watch the video" links
    opening the media in the lightbox; for everyone else the card keeps opening the photo or video on the page."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        self.manager = User.objects.create_superuser('boss', password='x')
        self.other = User.objects.create_user('other', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        region = Region.objects.create(name='Anilao', country=ph, sea=sea)
        species = Species.objects.create(scientific_name='Longibranchus putnami', genus='Longibranchus', species='putnami',
                                         author='(Fernández-Simón & Moles, 2023)')
        samples = []
        for n, code in enumerate(('C', 'V'), 1):
            trip = DiveTrip.objects.create(code=code, title=code, year=2020 + n, month=1, country=ph, region=region)
            sample = Sample(owner=self.owner, species=species, trip=trip, video_url=f'https://youtu.be/3000000000{n}')
            sample.save_reviewed()
            samples.append(sample)
        self.area = SpeciesArea.objects.get(species=species)
        self.extra = next(s for s in samples if s.pk != self.area.defining_sample_id)

    def card(self, user=None):
        if user: self.client.force_login(user)
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        return html[html.index(f'id="obs-{self.extra.pk}"'):html.index('</article>', html.index(f'id="obs-{self.extra.pk}"'))]

    def test_editors_open_the_edit_page(self):
        for user in (self.manager, self.owner):
            card = self.card(user)
            self.assertIn(f'class="video-button observation-edit-link" href="/observations/{self.extra.pk}/edit/?next=', card)
            self.assertIn('class="lightbox-link"', card)
            self.assertIn('צפייה בסרטון', card)

    def test_visitors_keep_the_lightbox(self):
        for user in (None, self.other):
            card = self.card(user)
            self.assertNotIn('observation-edit-link', card)
            self.assertIn('class="video-button lightbox-link"', card)
