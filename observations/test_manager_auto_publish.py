"""An observation a manager saves is approved by the save itself -- a collection too -- when it is
complete; a member's collection still waits for a manager's approval."""
from django.contrib.auth.models import Permission, User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea


class ManagerSavePublishesTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Israel')
        region = Region.objects.create(name='Eilat', country=country, sea=Sea.objects.create(name='Red Sea'))
        self.trip = DiveTrip.objects.create(title='Eilat', code='E26', year=2026, month=3, country=country, region=region)
        self.manager = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927')
        self.member = User.objects.create_user('member', password='a-valid-password-927')

    def post(self, user, **extra):
        self.client.force_login(user)
        data = {'kind': 'collection', 'title': 'Night dive', 'trip': str(self.trip.pk), 'site': '',
                'video_url': 'https://youtu.be/12345678901', 'next': '/'}
        data.update(extra)
        return self.client.post('/observations/new/', data)

    def test_a_managers_collection_is_published_at_once(self):
        response = self.post(self.manager)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        sample = Sample.objects.get(title='Night dive')
        self.assertEqual((sample.status, sample.approved_by), ('published', self.manager))

    def test_a_managers_incomplete_collection_still_waits(self):
        # a free-text "other" dive site still has to be replaced by a site from the table
        response = self.post(self.manager, site='other', site_other='Somewhere new')
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        self.assertEqual(Sample.objects.get(title='Night dive').status, 'pending')

    def test_a_members_collection_waits_for_approval(self):
        self.post(self.member)
        self.assertEqual(Sample.objects.get(title='Night dive').status, 'pending')
