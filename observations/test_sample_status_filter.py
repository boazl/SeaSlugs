from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import Sample


class SampleStatusFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('boss', password='test-password-x1')
        self.client.force_login(self.user)
        self.live = Sample.objects.create(owner=self.user, kind=Sample.Kind.GENUS, genus='Chromodoris', video_url='https://youtu.be/aaaaaaaaaaa')
        self.deleted = Sample.objects.create(owner=self.user, kind=Sample.Kind.GENUS, genus='Felimare', video_url='https://youtu.be/bbbbbbbbbbb',
                                             deleted_at=timezone.now())

    def ids(self, query):
        response = self.client.get('/admin/observations/sample/' + query)
        self.assertEqual(response.status_code, 200)
        return {obj.pk for obj in response.context['cl'].result_list}

    def test_pending_lists_only_live_observations(self):
        self.assertEqual(self.ids('?status__exact=pending'), {self.live.pk})

    def test_a_deleted_observation_is_still_listed_without_the_pending_filter(self):
        self.assertEqual(self.ids(''), {self.live.pk, self.deleted.pk})
        self.assertEqual(self.ids('?deleted_at__isnull=False'), {self.deleted.pk})
