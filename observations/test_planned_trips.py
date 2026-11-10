"""Dive-trip planning observations (Sample.Kind.PLANNED, planned_trips.py)."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Country, DiveTrip, ForumMessage, Region, Sample, Sea

TODAY = date.today()
NEXT = date(TODAY.year + 1, 5, 10)


class PlannedSetup(TestCase):
    def setUp(self):
        country = Country.objects.create(name='ישראל', name_en='Israel')
        self.region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=Sea.objects.create(name='ים סוף', name_en='Red Sea'))
        self.future = DiveTrip.objects.create(title='אילת הבא', code='F1', year=NEXT.year, month=NEXT.month, start_day=NEXT.day,
                                              duration_days=5, country=country, region=self.region)
        self.past = DiveTrip.objects.create(title='אילת שעבר', code='P1', year=TODAY.year - 1, month=3, country=country, region=self.region)
        self.manager = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927')
        self.member = User.objects.create_user('member', password='a-valid-password-927', email='m@example.org')

    def planning(self, trip=None, owner=None, **extra):
        sample = Sample(kind=Sample.Kind.PLANNED, trip=trip or self.future, owner=owner or self.member, title='מסע לאילת', **extra)
        sample.save_reviewed()
        return sample

    def close(self, sample):
        """Make the trip end yesterday (as if its date had passed)."""
        end = TODAY - timedelta(days=1)
        DiveTrip.objects.filter(pk=sample.trip_id).update(year=end.year, month=end.month, start_day=end.day, duration_days=1)
        sample.refresh_from_db()


class PlannedModelTests(PlannedSetup):
    """A dive-trip planning has a title, a trip with at least a year and a month, and no media; a member's planning
    publishes itself. Observations with media cannot be added to a trip that has not started; a trip may lie in the
    future. The trip's dates: start day + duration, else the end of its month."""

    def test_member_planning_publishes_itself(self):
        self.assertEqual(self.planning().status, 'published')

    def test_no_media(self):
        with self.assertRaises(ValidationError):
            self.planning(video_url='https://youtu.be/12345678901')

    def test_needs_a_title_and_a_month(self):
        with self.assertRaises(ValidationError):
            Sample(kind=Sample.Kind.PLANNED, trip=self.future, owner=self.member).save_reviewed()
        no_month = DiveTrip.objects.create(title='x', code='Y1', year=NEXT.year, country=self.future.country, region=self.region)
        with self.assertRaises(ValidationError):
            self.planning(trip=no_month)

    def test_no_media_observation_on_a_future_trip(self):
        sample = Sample(kind=Sample.Kind.COLLECTION, trip=self.future, owner=self.member, title='t', video_url='https://youtu.be/12345678901')
        with self.assertRaises(ValidationError) as caught:
            sample.save_reviewed()
        self.assertIn('trip', caught.exception.message_dict)

    def test_trip_dates(self):
        self.assertEqual(self.future.end_date(), NEXT + timedelta(days=4))
        self.assertEqual(self.past.end_date(), date(TODAY.year - 1, 3, 31))
        self.future.full_clean()     # a future trip is valid

    def test_open_until_the_last_day(self):
        sample = self.planning()
        self.assertTrue(sample.planning_open)
        self.close(sample)
        self.assertFalse(sample.planning_open)

    def test_a_closed_planning_still_validates(self):
        # the table transfer must still carry it
        sample = self.planning()
        self.close(sample)
        sample.full_clean()


class PlannedFormTests(PlannedSetup):
    """Any member adds a planning with the observation form (?kind=planned preselects it); a planning whose trip has
    ended cannot be saved -- it can be turned into a regular dive trip by choosing the collection kind and adding
    media, keeping the same row (and so its forum discussion)."""

    def post(self, user, url='/observations/new/', **extra):
        self.client.force_login(user)
        data = {'kind': 'planned', 'title': 'מסע לאילת', 'trip': str(self.future.pk), 'site': '', 'next': '/'}
        data.update(extra)
        return self.client.post(url, data)

    def test_member_adds_a_planning(self):
        self.client.force_login(self.member)
        self.assertContains(self.client.get('/observations/new/?kind=planned'), '<option value="planned" selected>')
        response = self.post(self.member)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        sample = Sample.objects.get(kind='planned')
        self.assertEqual((sample.status, sample.owner, sample.video_url), ('published', self.member, ''))

    def test_past_trip_refused(self):
        response = self.post(self.member, trip=str(self.past.pk))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Sample.objects.exists())

    def test_turned_into_a_dive_trip(self):
        sample = self.planning()
        message = ForumMessage.objects.create(observation=sample, user=self.manager, text='מצטרף')
        self.close(sample)
        response = self.post(self.manager, url=f'/observations/{sample.pk}/edit/', kind='collection',
                             trip=str(sample.trip_id), video_url='https://youtu.be/12345678901')
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['form'].errors)
        sample.refresh_from_db()
        self.assertEqual((sample.kind, sample.status), ('collection', 'published'))
        message.refresh_from_db()
        self.assertEqual(message.observation_id, sample.pk)


class PlannedPagesTests(PlannedSetup):
    """A planning never shows in the gallery; it shows in the "תכנון מסעות צלילה" section of the dive trips page and in
    the forum while it is open. When its date has passed it is closed: gone from both, and nobody can write in its
    discussion; its owner and the managers still reach the discussion by its address."""

    def test_trips_page_section(self):
        sample = self.planning()
        html = self.client.get('/observations/trips/').content.decode()
        section = html.split('id="planning"')[1].split('</section>')[0]
        self.assertIn('מסע לאילת', section)
        self.assertIn('href="/forum/trip/F1/"', section)
        self.assertIn(f'href="/forum/new/?obs={sample.pk}"', section)
        self.close(sample)
        html = self.client.get('/observations/trips/').content.decode()
        self.assertNotIn('מסע לאילת', html.split('id="planning"')[1].split('</section>')[0])

    def test_not_in_the_gallery(self):
        self.planning()
        self.assertNotIn('מסע לאילת', self.client.get('/catalog.js').content.decode())

    def test_forum(self):
        sample = self.planning()
        self.client.force_login(self.manager)
        self.client.post('/forum/', {'obs': sample.pk, 'audience': 'all', 'text': 'מי מצטרף?'})
        self.client.logout()
        html = self.client.get('/forum/?kind=planned').content.decode()
        self.assertIn('מי מצטרף?', html)
        self.assertIn('href="/planning/F1/"', self.client.get(f'/forum/?obs={sample.pk}').content.decode())
        self.close(sample)
        self.assertNotIn('מי מצטרף?', self.client.get('/forum/').content.decode())
        self.assertEqual(self.client.get(f'/forum/?obs={sample.pk}').status_code, 404)
        self.client.force_login(self.member)          # the owner
        html = self.client.get(f'/forum/?obs={sample.pk}').content.decode()
        self.assertIn('מי מצטרף?', html)
        self.assertIn('הדיון נסגר', html)
        self.client.post('/forum/', {'obs': sample.pk, 'audience': 'all', 'text': 'עוד הודעה'})
        self.assertEqual(ForumMessage.objects.count(), 1)


class PlanningPagesTests(PlannedSetup):
    """Each planning has its own address, /planning/<trip code>/ (the trip's permanent code), and /planning/ lists the
    open ones; the planning section, the forum and the sitemap link there. A trip has one planning. A closed planning
    is shown to its owner and the managers only; once it became a dive trip with a page, its address leads there (301)."""

    def test_page_and_list(self):
        sample = self.planning(note_he='מחפשים צוללים')
        from .models import ForumMessage
        ForumMessage.objects.create(observation=sample, user=self.manager, text='אני בפנים')
        html = self.client.get('/planning/F1/').content.decode()
        self.assertIn('<h1>מסע לאילת</h1>', html)
        self.assertIn('מחפשים צוללים', html)
        self.assertIn('אני בפנים', html)
        self.assertIn(f'href="/forum/new/?obs={sample.pk}"', html)
        self.assertIn('Discussion', self.client.get('/planning/F1/?lang=en').content.decode())
        listing = self.client.get('/planning/?lang=he').content.decode()
        self.assertIn('href="/planning/F1/"', listing)
        self.assertIn('href="/planning/F1/"', self.client.get('/observations/trips/?lang=he').content.decode())
        self.assertIn('href="/planning/F1/"', self.client.get(f'/forum/?obs={sample.pk}&lang=he').content.decode())
        sitemap = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('/planning/F1/</loc>', sitemap)
        self.assertIn('/planning/</loc>', sitemap)

    def test_one_planning_per_trip(self):
        self.planning()
        with self.assertRaises(ValidationError):
            self.planning(owner=self.manager)

    def test_closed_and_converted(self):
        sample = self.planning()
        self.close(sample)
        self.assertEqual(self.client.get('/planning/F1/').status_code, 404)
        self.client.force_login(self.member)
        self.assertContains(self.client.get('/planning/F1/'), 'התכנון נסגר')
        self.client.logout()
        sample.kind = Sample.Kind.COLLECTION
        sample.video_url = 'https://youtu.be/12345678901'
        sample.save_reviewed(actor=self.manager, approve=True)
        response = self.client.get('/planning/F1/')
        self.assertEqual((response.status_code, response['Location']), (301, '/trip/F1/'))
        self.assertEqual(self.client.get('/planning/NOPE/').status_code, 404)


class PlannedListingTests(PlannedSetup):
    """A dive-trip planning has no photographer: its card in the observations listing shows no "צילום:" line, and the
    place line skips the empty site (no "· ·")."""

    def test_listing_card(self):
        sample = self.planning()
        self.client.force_login(self.member)
        html = self.client.get('/observations/?mine=1').content.decode()
        card = html.split('מסע לאילת')[1].split('</article>')[0]
        self.assertNotIn('צילום:', card)
        self.assertNotIn('· ·', card)
        self.assertIn('ישראל · אילת · ', card)
