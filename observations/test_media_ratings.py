"""Ratings and views of an observation's photo and video (observations/ratings.py)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .models import Country, DiveTrip, MediaRating, Region, Sample, Sea, Species
from .ratings import PRIOR_MEAN, PRIOR_WEIGHT, RATER_COOKIE, bayesian
from .table_transfer import TABLES

BROWSER = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Macintosh) Safari/605.1.15'}
APP_JS = Path(settings.BASE_DIR) / 'dist' / 'app.js'


class MediaRatingTests(TestCase):
    """Every observation has six rating fields: the photographer's stars for its photo and its video (the owner
    rating his own observation -- never part of the audience's average), the audience's rating of each (a Bayesian
    average of everyone else's MediaRating rows, members and guests alike -- a guest is the id in his browser's
    cookie) and the number of views of each. A rater has one rating per observation and medium, sees it again and can
    change or clear it (0). Views: the photo opened large / the video played, not counted for the photographer, the
    site owner, an opted-out browser or a bot. All written with update(): updated_at is untouched. Per environment:
    the fields are not in the samples transfer. Only a published, live observation with that medium is rated."""

    def setUp(self):
        self.owner = User.objects.create_user('ofer', password='pw-test-12345')
        self.member = User.objects.create_user('dana', password='pw-test-12345')
        country = Country.objects.create(name='ישראל')
        region = Region.objects.create(name='אילת', country=country, sea=Sea.objects.create(name='ים סוף'))
        self.trip = DiveTrip.objects.create(title='Eilat', year=2025, country=country, region=region, code='e1')
        species = Species.objects.create(scientific_name='Phyllidia ocellata')
        self.sample = Sample(owner=self.owner, trip=self.trip, species=species, video_url='https://youtu.be/aaaaaaaaaaa')
        self.sample.save_reviewed()
        self.url = f'/observations/{self.sample.pk}/rating/'
        self.view_url = f'/observations/{self.sample.pk}/viewed/'

    def rate(self, stars, media='video', client=None):
        return (client or self.client).post(self.url, {'media': media, 'stars': stars}, **BROWSER)

    def fresh(self):
        return Sample.objects.get(pk=self.sample.pk)

    def test_bayesian_average(self):
        self.assertIsNone(bayesian(0, 0))
        self.assertEqual(bayesian(5, 1), round((PRIOR_MEAN * PRIOR_WEIGHT + 5) / (PRIOR_WEIGHT + 1), 3))
        self.assertGreater(bayesian(4.8 * 40, 40), bayesian(5, 1))     # many good ratings beat a single perfect one

    def test_member_rates_sees_changes_and_clears(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url).json(), {'image': None, 'video': None, 'photographer': False})
        self.assertEqual(self.rate(4).json()['video'], 4)
        self.assertEqual(self.fresh().audience_video_rating, bayesian(4, 1))
        self.rate(2)
        self.assertEqual(MediaRating.objects.get().stars, 2)
        self.assertEqual(self.client.get(self.url).json()['video'], 2)
        self.assertEqual(self.fresh().audience_video_rating, bayesian(2, 1))
        self.assertIsNone(self.rate(0).json()['video'])
        self.assertFalse(MediaRating.objects.exists())
        self.assertIsNone(self.fresh().audience_video_rating)

    def test_guests_rate_by_their_browser_cookie(self):
        response = self.rate(5)
        visitor = response.cookies[RATER_COOKIE].value
        self.assertEqual(response.json()['video'], 5)
        self.assertEqual(MediaRating.objects.get().visitor, visitor)
        self.assertEqual(self.client.get(self.url).json()['video'], 5)    # the cookie stays in this client
        self.rate(3)
        self.assertEqual(MediaRating.objects.count(), 1)
        other = self.client_class()
        self.rate(1, client=other)
        self.assertEqual(MediaRating.objects.count(), 2)
        self.assertEqual(self.fresh().audience_video_rating, bayesian(4, 2))

    def test_photographer_rating_is_kept_apart(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.rate(5).json(), {'image': None, 'video': 5, 'photographer': True})
        sample = self.fresh()
        self.assertEqual(sample.photographer_video_rating, 5)
        self.assertIsNone(sample.audience_video_rating)
        self.assertFalse(MediaRating.objects.exists())
        self.rate(0)
        self.assertIsNone(self.fresh().photographer_video_rating)

    def test_only_existing_media_of_published_observations(self):
        self.client.force_login(self.member)
        self.assertEqual(self.rate(3, media='image').status_code, 400)       # no photo
        self.assertEqual(self.rate(6).status_code, 400)
        self.assertEqual(self.client.post(self.url, {'media': 'video', 'stars': 'x'}).status_code, 400)
        Sample.objects.filter(pk=self.sample.pk).update(status='pending')
        self.assertEqual(self.rate(3).status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_views(self):
        self.client.force_login(self.member)
        self.assertTrue(self.client.post(self.view_url, {'media': 'video'}, **BROWSER).json()['counted'])
        self.assertEqual(self.client.post(self.view_url, {'media': 'image'}, **BROWSER).status_code, 400)
        self.client.logout()
        self.client.post(self.view_url, {'media': 'video'}, **BROWSER)
        self.assertEqual(self.fresh().video_views, 2)
        # not counted: a bot, the photographer, the site owner, an opted-out browser
        self.assertFalse(self.client.post(self.view_url, {'media': 'video'}, HTTP_USER_AGENT='Googlebot/2.1').json()['counted'])
        self.client.force_login(self.owner)
        self.assertFalse(self.client.post(self.view_url, {'media': 'video'}, **BROWSER).json()['counted'])
        self.client.force_login(User.objects.create_superuser('boss', password='x'))
        self.assertFalse(self.client.post(self.view_url, {'media': 'video'}, **BROWSER).json()['counted'])
        self.client.logout()
        self.client.cookies['exclude_analytics'] = '1'
        self.assertFalse(self.client.post(self.view_url, {'media': 'video'}, **BROWSER).json()['counted'])
        self.assertEqual(self.fresh().video_views, 2)
        self.assertEqual(self.client.get(self.view_url).status_code, 405)

    def test_counters_never_touch_updated_at_and_never_transfer(self):
        before = self.fresh().updated_at
        self.client.post(self.view_url, {'media': 'video'}, **BROWSER)
        self.rate(4)
        self.assertEqual(self.fresh().updated_at, before)
        fields = set(TABLES['samples'][1])
        for name in ('photographer_image_rating', 'photographer_video_rating', 'audience_image_rating',
                     'audience_video_rating', 'image_views', 'video_views'):
            self.assertNotIn(name, fields)
        self.assertNotIn('mediarating', {model._meta.model_name for model, _ in TABLES.values()})

    def test_a_samples_transfer_keeps_the_targets_ratings_and_views(self):
        # the transfer rebuilds each observation from the file, which has no rating fields: they must stay the
        # target's own (they once came back empty after a transfer)
        from pathlib import Path as _Path
        from unittest.mock import patch
        from .table_transfer import apply, export_table, fingerprint
        doc = export_table('samples')
        doc['rows'][0]['note_he'] = 'הערה'
        doc['media_mode'] = 'separate'
        self.rate(4)
        Sample.objects.filter(pk=self.sample.pk).update(photographer_video_rating=5, video_views=12)
        with patch('observations.table_transfer.create_backup', return_value=_Path('test.sqlite3')):
            apply(doc, fingerprint())
        sample = self.fresh()
        self.assertEqual(sample.note_he, 'הערה')
        self.assertEqual((sample.photographer_video_rating, sample.audience_video_rating, sample.video_views),
                         (5, bayesian(4, 1), 12))

    def test_refresh_command_recomputes_the_averages(self):
        from django.core.management import call_command
        self.rate(4)
        Sample.objects.filter(pk=self.sample.pk).update(audience_video_rating=None, audience_image_rating=2.0)
        call_command('refresh_audience_ratings', stdout=open('/dev/null', 'w'))
        self.assertEqual((self.fresh().audience_video_rating, self.fresh().audience_image_rating), (bayesian(4, 1), None))

    def test_species_page_has_the_stars(self):
        from .models import SpeciesArea
        html = self.client.get(f'/species/{SpeciesArea.objects.get().slug}/').content.decode()
        self.assertIn(f'class="media-rating" data-sample="{self.sample.pk}" data-media="video"', html)
        self.assertIn('id="lightbox-rating"', html)
        self.assertIn(f'data-rated-sample="{self.sample.pk}"', html)
        self.assertIn('csrfmiddlewaretoken', html)
        english = self.client.get(f'/species/{SpeciesArea.objects.get().slug}/?lang=en').content.decode()
        self.assertIn('Your rating:', english)

    def test_catalog_carries_the_values_for_sorting(self):
        Sample.objects.filter(pk=self.sample.pk).update(audience_video_rating=4.2, video_views=7)
        text = self.client.get('/catalog.js').content.decode()
        data = json.loads(text.removeprefix('window.SEASLUGS = ').removesuffix(';'))
        sample = data['species'][0]['samples'][0]
        self.assertEqual((sample['rating_video'], sample['views_video'], sample['rating_image'], sample['views_image']), (4.2, 7, None, 0))

    def test_my_ratings_in_the_catalog(self):
        def mine():
            text = self.client.get('/catalog.js').content.decode()
            return json.loads(text.removeprefix('window.SEASLUGS = ').removesuffix(';'))['my_ratings']
        self.assertEqual(mine(), {})
        self.rate(4)                                    # a guest, by his cookie
        self.assertEqual(mine(), {str(self.sample.pk): {'video': 4}})
        self.client.force_login(self.member)
        self.assertEqual(mine(), {})
        self.rate(2)
        self.assertEqual(mine(), {str(self.sample.pk): {'video': 2}})
        self.client.force_login(self.owner)             # the photographer: his photographer stars
        self.rate(5)
        self.assertEqual(mine(), {str(self.sample.pk): {'video': 5}})


def _function_source(source, name):
    start = source.index(f'function {name}(')
    depth, i = 0, source.index('{', start)
    while True:
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1


@unittest.skipUnless(shutil.which('node'), 'node is needed to run app.js code')
class GalleryMediaSortTests(TestCase):
    """The gallery sorts by the audience rating or the views of the video / photo (rating_video, rating_image,
    views_video, views_image), or by the visitor's own stars (my_rating_video, my_rating_image -- catalog.js
    my_ratings; offered only once he has rated that medium): a species card by its best observation among those the filters leave, highest first;
    cards with no rating (or no views) last; ties and the unrated in taxonomic order. The values are not shown."""

    def sort(self, field):
        source = APP_JS.read_text(encoding='utf-8')
        script = '\n'.join([
            'const scopedSamples = () => null;',
            "const catalog = {my_ratings: {'1': {video: 2}, '3': {video: 5, image: 1}, '4': {image: 4}}};",
            'function speciesSortCompare(a, b) { return a.title.localeCompare(b.title); }',
            source[source.index('const MEDIA_SORTS = '):source.index('\n', source.index('const MEDIA_SORTS = ')) + 1],
            source[source.index('const myRatings = '):source.index('\n', source.index('const myRatings = ')) + 1],
            _function_source(source, 'sortFieldValue'),
            _function_source(source, 'mediaSortValue'),
            _function_source(source, 'mediaValueCompare'),
            _function_source(source, 'speciesMediaCompare'),
            "const list = ["
            " {title: 'A', samples: [{sample_id: 1, rating_video: null, views_video: 0}]},"
            " {title: 'B', samples: [{sample_id: 2, rating_video: 3.4, views_video: 2}, {sample_id: 3, rating_video: 4.6, views_video: 9}]},"
            " {title: 'C', samples: [{sample_id: 4, rating_video: 4.1, views_video: 30}]},"
            " {title: 'D', samples: [{sample_id: 5, rating_video: 4.1, views_video: 0}]}];",
            f"console.log(JSON.stringify(list.sort(speciesMediaCompare(MEDIA_SORTS[{json.dumps(field)}])).map(s => s.title)));",
        ])
        return json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)

    def test_by_rating_best_observation_first_unrated_last(self):
        self.assertEqual(self.sort('rating_video'), ['B', 'C', 'D', 'A'])

    def test_by_my_own_rating(self):
        # my stars only (catalog.js my_ratings): B has a 5-star video of mine, A a 2; C and D none -- last, by name
        self.assertEqual(self.sort('my_rating_video'), ['B', 'A', 'C', 'D'])
        self.assertEqual(self.sort('my_rating_image'), ['C', 'B', 'A', 'D'])

    def test_my_rating_sorts_only_for_a_visitor_who_rated(self):
        source = APP_JS.read_text(encoding='utf-8')
        html = (Path(settings.BASE_DIR) / 'dist' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<option value="my_rating_video">', html)
        self.assertIn('<option value="my_rating_image">', html)
        sync = source.split('function syncSortControl() {')[1].split('\n}')[0]
        self.assertIn('for (const [media, option] of myRatingSortOptions)', sync)
        self.assertIn('option.remove();', sync)

    def test_by_views(self):
        self.assertEqual(self.sort('views_video'), ['C', 'B', 'A', 'D'])

    def test_the_sort_menu_and_links(self):
        source = APP_JS.read_text(encoding='utf-8')
        html = (Path(settings.BASE_DIR) / 'dist' / 'index.html').read_text(encoding='utf-8')
        for value in ('rating_video', 'rating_image', 'views_video', 'views_image'):
            self.assertIn(f'<option value="{value}">', html)
        self.assertIn("const GALLERY_SORTS = ['taxonomic', 'alpha', 'year', 'count', ...Object.keys(MEDIA_SORTS)];", source)
        self.assertNotIn('rating_video', source.split('function buildSpeciesCard(')[1].split('\nfunction ')[0])   # never shown
