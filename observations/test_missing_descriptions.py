from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .missing_descriptions import missing_description_rows
from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea


class MissingDescriptionsTests(TestCase):
    """/admin/missing-descriptions/ lists the species shown in the gallery (a SpeciesArea with a live published
    defining observation) whose description (description_he / description_en) is still empty -- in either
    language by default, or only Hebrew / only English / both. Species not in the gallery are left out; the
    newest species come first. Superusers only."""

    def setUp(self):
        self.user = User.objects.create_superuser('boss', password='x')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='הים התיכון', name_en='Mediterranean')
        region = Region.objects.create(name='אכזיב', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='T', year=2026, month=1, country=country, region=region)
        self.n = 0

    def gallery_species(self, name, he='', en='', published=True):
        species = Species.objects.create(scientific_name=name, description_he=he, description_en=en)
        self.n += 1
        sample = Sample(kind='species', species=species, trip=self.trip, owner=self.user,
                        video_url=f'https://youtu.be/abcdefghi{self.n:02d}')
        sample.save_reviewed(actor=self.user)
        if not published:
            Sample.objects.filter(pk=sample.pk).update(deleted_at=timezone.now())
            SpeciesArea.objects.filter(species=species).update(defining_sample=None)
        return species, sample

    def names(self, **kwargs):
        return [row['species'].scientific_name for row in missing_description_rows(**kwargs)[0]]

    def test_lists_gallery_species_by_missing_language(self):
        self.gallery_species('Aplysia argus')
        self.gallery_species('Elysia ornata', he='תיאור')
        self.gallery_species('Doto sp.', en='Description')
        self.gallery_species('Bornella anguilla', he='תיאור', en='Description')
        self.assertEqual(sorted(self.names()), ['Aplysia argus', 'Doto sp.', 'Elysia ornata'])
        self.assertEqual(self.names(missing='both'), ['Aplysia argus'])
        self.assertEqual(sorted(self.names(missing='he')), ['Aplysia argus', 'Doto sp.'])
        self.assertEqual(sorted(self.names(missing='en')), ['Aplysia argus', 'Elysia ornata'])

    def test_whitespace_is_no_description(self):
        self.gallery_species('Aplysia argus', he='  \n', en='Description')
        self.assertEqual(self.names(missing='he'), ['Aplysia argus'])

    def test_species_outside_the_gallery_are_ignored(self):
        Species.objects.create(scientific_name='Never observed')
        self.gallery_species('Hidden one', published=False)
        self.assertEqual(self.names(), [])
        self.assertEqual(missing_description_rows()[1], 0)

    def test_newest_species_first_and_by_name(self):
        _, old = self.gallery_species('Zeta old')
        Sample.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))
        self.gallery_species('Alpha new')
        self.assertEqual(self.names(), ['Alpha new', 'Zeta old'])
        self.assertEqual(self.names(sort='name'), ['Alpha new', 'Zeta old'])
        _, older = self.gallery_species('Beta oldest')
        Sample.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=60))
        self.assertEqual(self.names(), ['Alpha new', 'Zeta old', 'Beta oldest'])
        self.assertEqual(self.names(sort='name'), ['Alpha new', 'Beta oldest', 'Zeta old'])

    def test_page_for_superusers_only(self):
        species, _ = self.gallery_species('Aplysia argus')
        self.client.force_login(self.user)
        response = self.client.get('/admin/missing-descriptions/?missing=both')
        self.assertContains(response, 'Aplysia argus')
        self.assertContains(response, f'/admin/observations/species/{species.pk}/change/')
        self.assertContains(response, '/species/')
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/admin/missing-descriptions/').status_code, 403)

    def test_linked_from_the_admin_index(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/admin/'), '/admin/missing-descriptions/')
