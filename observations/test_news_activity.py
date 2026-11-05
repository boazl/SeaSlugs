"""The activity log (activity.py), the visit counter and the /news/ page (news.py)."""
import io
from datetime import date, timedelta
from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from django.test import TestCase
from django.utils import timezone

from .models import (ActivityEvent as E, Country, DailyPageView, DailyVisitor, DiveTrip, NewsPost, Region, Sample, Sea,
                     Species, SpeciesArea, TaxonFamily, TaxonGenus, TaxonOrder)

def png():
    buffer = io.BytesIO()
    Image.new('RGB', (40, 30), (10, 80, 120)).save(buffer, 'PNG')
    return SimpleUploadedFile('p.png', buffer.getvalue(), content_type='image/png')


UA = 'Mozilla/5.0 (Macintosh) Safari/605'


class Base(TestCase):
    def setUp(self):
        self.member = User.objects.create_user('diver', password='pw-test-12345', first_name='דנה', last_name='ים')
        israel = Country.objects.create(name='ישראל', name_en='Israel')
        phil = Country.objects.create(name='פיליפינים', name_en='Philippines')
        self.red = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        self.scs = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        eilat = Region.objects.create(name='אילת', name_en='Eilat', country=israel, sea=self.red)
        anilao = Region.objects.create(name='אנילאו', name_en='Anilao', country=phil, sea=self.scs)
        self.trip = DiveTrip.objects.create(title='Eilat', year=2026, country=israel, region=eilat, code='e1')
        self.trip_ph = DiveTrip.objects.create(title='Anilao', year=2025, country=phil, region=anilao, code='a1')
        order = TaxonOrder.objects.create(name='Nudibranchia')
        family = TaxonFamily.objects.create(name='Phyllidiidae', order=order)
        TaxonGenus.objects.create(name='Phyllidia', family=family)
        mk = lambda epithet: Species.objects.create(scientific_name=f'Phyllidia {epithet}', genus='Phyllidia', species=epithet,
                                                     author='Author, 1900', family='Phyllidiidae', order='Nudibranchia')
        self.ocellata, self.varicosa = mk('ocellata'), mk('varicosa')

    def observe(self, species=None, trip=None, video='aaaaaaaaaaa', **extra):
        sample = Sample(owner=self.member, trip=trip or self.trip, species=species or self.ocellata,
                        video_url=f'https://youtu.be/{video}' if video else '', **extra)
        sample.save_reviewed()
        return sample

    def events(self, kind):
        return list(E.objects.filter(kind=kind))

    def age(self, sample, minutes=60):
        """Pretend the observation was added a while ago (past the adding grace window)."""
        E.objects.filter(sample_transfer_id=sample.transfer_id).update(created_at=timezone.now() - timedelta(minutes=minutes))


class ObservationLogTests(Base):
    """Publishing logs an observation (and its video) once; a pending one is not logged; a species change is one
    "identification change" line with the old and new names; other edits fold into one daily "updated" line."""

    def test_publishing_logs_the_observation_and_its_video_once(self):
        sample = self.observe()
        self.assertEqual(len(self.events('observation_added')), 1)
        self.assertEqual(self.events('video_added')[0].detail['video'], 'aaaaaaaaaaa')
        sample.soft_delete(self.member)
        sample.deleted_at = None; sample.save_reviewed()          # back again: not a new observation
        self.assertEqual(len(self.events('observation_added')), 1)
        self.assertEqual(len(self.events('video_added')), 1)
        event = self.events('observation_added')[0]
        self.assertEqual((event.user, event.sea, event.name), (self.member, self.red, 'Phyllidia ocellata'))

    def test_a_pending_observation_is_not_logged(self):
        Sample(owner=self.member, trip=self.trip, species_other='Something new', video_url='https://youtu.be/bbbbbbbbbbb').save_reviewed()
        self.assertFalse(E.objects.filter(public=True).exists())

    def test_a_new_video_on_a_public_observation_is_logged(self):
        sample = self.observe(video='', image=png())
        self.assertEqual(self.events('video_added'), [])
        sample.video_url = 'https://youtu.be/ccccccccccc'; sample.save_reviewed()
        self.assertEqual(len(self.events('video_added')), 1)

    def test_a_species_change_is_one_line_with_both_names(self):
        sample = self.observe()
        self.age(sample)
        sample.species = self.varicosa; sample.note_he = 'צולם מחדש'; sample.save_reviewed()
        changed = self.events('species_changed')
        self.assertEqual([(e.old_name, e.name) for e in changed], [('Phyllidia ocellata', 'Phyllidia varicosa')])
        self.assertEqual(self.events('observation_updated'), [])

    def test_edits_fold_into_one_line_a_day_and_saves_while_adding_are_not_edits(self):
        sample = self.observe()
        sample.note_he = 'הערה'; sample.save_reviewed()            # the form's own follow-up save
        self.assertEqual(self.events('observation_updated'), [])
        self.age(sample)
        sample.depth = 12; sample.save_reviewed()
        sample.note_en = 'note'; sample.save_reviewed()
        updated = self.events('observation_updated')
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].count, 2)
        self.assertEqual(updated[0].detail['fields'], ['depth', 'note_en'])

    def test_a_trip_collection_is_logged(self):
        Sample(owner=self.member, trip=self.trip, kind='collection', title='Eilat 2026',
               video_url='https://youtu.be/ddddddddddd').save_reviewed(actor=self.member, approve=True)
        self.assertEqual([e.name for e in self.events('observation_added')], ['Eilat 2026'])


class NewSpeciesLogTests(Base):
    """A new gallery card is a "new species in an area", marked new to the site or only new to that sea; recreating
    the cards (rebuild) logs nothing."""

    def test_new_to_site_then_new_to_another_sea(self):
        self.observe()
        self.observe(trip=self.trip_ph, video='eeeeeeeeeee')
        first, second = sorted(self.events('species_new'), key=lambda e: e.pk)
        self.assertEqual((first.sea, first.detail['new_to_site'], first.detail['new_to_sea']), (self.red, True, True))
        self.assertEqual((second.sea, second.detail['new_to_site'], second.detail['new_to_sea']), (self.scs, False, True))

    def test_rebuild_logs_nothing(self):
        self.observe()
        SpeciesArea.rebuild()
        self.assertEqual(len(self.events('species_new')), 1)


class AccountLogTests(Base):
    """Sign-ups and logins are manager-only lines; the owner's own logins and accounts arriving by transfer
    (no usable password) are not logged."""

    def test_signup_and_login_are_private(self):
        self.assertTrue(E.objects.filter(kind='signup', user=self.member, public=False).exists())
        self.client.login(username='diver', password='pw-test-12345')
        self.assertTrue(E.objects.filter(kind='login', user=self.member, public=False).exists())

    def test_owner_and_transferred_accounts_are_not_logged(self):
        owner = User.objects.create_superuser('boss', password='pw-test-12345')
        guest = User(username='guest'); guest.set_unusable_password(); guest.save()
        self.client.login(username='boss', password='pw-test-12345')
        self.assertFalse(E.objects.filter(user__in=[owner, guest]).exists())


class VisitCounterTests(Base):
    """Public HTML pages are counted per page per day, visitors once a day; bots, the admin tools, the owner and a
    browser with the analytics opt-out are not."""

    def test_views_and_visitors(self):
        self.client.get('/news/', HTTP_USER_AGENT=UA)
        self.client.get('/news/', HTTP_USER_AGENT=UA)
        self.assertEqual(DailyPageView.objects.get(path='/news/').views, 2)
        self.assertEqual(DailyVisitor.objects.count(), 1)

    def test_not_counted(self):
        self.client.get('/news/', HTTP_USER_AGENT='Googlebot/2.1')
        self.client.get('/news/')                                            # no browser
        self.client.cookies['exclude_analytics'] = '1'
        self.client.get('/news/', HTTP_USER_AGENT=UA)
        del self.client.cookies['exclude_analytics']
        User.objects.create_superuser('boss', password='pw-test-12345')
        self.client.login(username='boss', password='pw-test-12345')
        self.client.get('/news/', HTTP_USER_AGENT=UA)
        self.client.get('/admin/', HTTP_USER_AGENT=UA)
        self.assertFalse(DailyPageView.objects.exists())
        self.assertFalse(DailyVisitor.objects.exists())


class NewsPageTests(Base):
    """The page is public, in one language, lists only lines whose observation is still public, filters by sea,
    shows posts and upcoming planned trips, the progress chart, and the management data to managers only."""

    def test_public_page_lists_recent_activity(self):
        self.observe()
        response = self.client.get('/news/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('<i>Phyllidia ocellata</i>', html)
        self.assertIn('class="photo-card"', html)                       # new observations as small picture cards
        self.assertIn('https://i.ytimg.com/vi/aaaaaaaaaaa/mqdefault.jpg', html)
        self.assertIsNotNone(response.context['chart'])
        self.assertNotIn('נתוני ניהול', html)

    def test_new_species_and_new_to_an_area(self):
        # "מינים חדשים" counts species new to the site; "מינים חדשים לאזור" every new species-in-an-area card
        self.observe()
        self.observe(trip=self.trip_ph, video='kkkkkkkkkkk')
        self.observe(species=self.varicosa, trip=self.trip_ph, video='lllllllllll')
        response = self.client.get('/news/')
        self.assertEqual((response.context['new_species_site'], len(response.context['new_species'])), (2, 3))
        # the list shows species new to the site, each once, with its date and name only
        self.assertEqual([line['name'] for line in response.context['species_list']], ['Phyllidia varicosa', 'Phyllidia ocellata'])
        listed = response.content.decode().split('<h3>מינים חדשים</h3>')[1].split('</ul>')[0]
        self.assertNotIn('צילום:', listed)
        self.assertNotIn('badge', listed)
        self.assertIn('class="line-thumb"', listed)                                    # a small picture of the observation
        self.assertIn('https://i.ytimg.com/vi/', listed)
        html = response.content.decode()
        self.assertIn('מינים חדשים לאזור', html)
        self.assertIn('New species in an area', self.client.get('/news/?lang=en').content.decode())

    def test_tiles_with_zero_are_hidden(self):
        self.observe()
        html = self.client.get('/news/').content.decode()
        self.assertIn('תצפיות חדשות</span>', html)
        self.assertNotIn('שינויים בהגדרת המין</span>', html)                     # 0 changes: no tile
        self.assertNotIn('תצפיות שעודכנו</span>', html)
        self.assertNotIn('<b>0</b>', html)

    def test_a_new_video_links_to_its_observation(self):
        self.observe()
        html = self.client.get('/news/').content.decode()
        card = html.split('class="video-card"')[1].split('>')[0]
        self.assertIn('/species/', card)                                               # the observation's page
        self.assertNotIn('youtu', card)

    def test_a_removed_observation_drops_out(self):
        sample = self.observe()
        sample.soft_delete(self.member)
        response = self.client.get('/news/')
        self.assertEqual(response.context['added'], [])
        self.assertEqual(response.context['new_species'], [])

    def test_sea_filter(self):
        self.observe()
        self.observe(species=self.varicosa, trip=self.trip_ph, video='fffffffffff')
        names = [line['name'] for line in self.client.get(f'/news/?sea={self.scs.pk}').context['added']]
        self.assertEqual(names, ['Phyllidia varicosa'])

    def test_english_page(self):
        self.observe()
        html = self.client.get('/news/?lang=en').content.decode()
        for hebrew in ('חדשות ופעילות', 'מינים חדשים', 'תצפיות חדשות', 'צילום:'):
            self.assertNotIn(hebrew, html.split('<main>')[1])
        self.assertIn('News &amp; activity', html)

    def test_posts_and_planned_trips(self):
        today = date.today()
        NewsPost.objects.create(title_he='גרסה חדשה', title_en='New version', kind='development', body_he='**חדש** באתר')
        NewsPost.objects.create(title_he='טיוטה', is_published=False)
        NewsPost.objects.create(title_he='מסע לאנילאו', kind='trip', trip_start=today + timedelta(days=30))
        NewsPost.objects.create(title_he='מסע שעבר', kind='trip', trip_start=today - timedelta(days=30), trip_end=today - timedelta(days=20))
        html = self.client.get('/news/').content.decode()
        self.assertIn('<strong>חדש</strong>', html)
        self.assertIn('מסע לאנילאו', html)
        self.assertNotIn('טיוטה', html)
        self.assertNotIn('מסע שעבר', html)
        self.assertIn('New version', self.client.get('/news/?lang=en').content.decode())

    def test_management_data_for_managers(self):
        User.objects.create_superuser('boss', password='pw-test-12345')
        self.client.login(username='boss', password='pw-test-12345')
        response = self.client.get('/news/')
        self.assertIn('נתוני ניהול', response.content.decode())
        self.assertIn('diver', [u['username'] for u in response.context['users']])

    def test_menu_and_sitemap(self):
        self.assertIn('href="/news/"', self.client.get('/observations/trips/').content.decode())
        self.assertIn('https://seaslugs.org.il/news/', self.client.get('/sitemap.xml').content.decode())


class BackfillMigrationTests(Base):
    """The backfill migration rebuilds the log from existing data: observations, videos, cards and sign-ups."""

    def test_backfill(self):
        self.observe()
        self.observe(trip=self.trip_ph, video='ggggggggggg')
        E.objects.all().delete()
        import_module('observations.migrations.0087_backfill_activity_log').backfill(apps, None)
        self.assertEqual(E.objects.filter(kind='observation_added').count(), 2)
        self.assertEqual(E.objects.filter(kind='video_added').count(), 2)
        marks = sorted((e.detail['new_to_site'], e.detail['new_to_sea']) for e in E.objects.filter(kind='species_new'))
        self.assertEqual(marks, [(False, True), (True, True)])
        self.assertTrue(E.objects.filter(kind='signup', user=self.member).exists())


class PeriodFilterTests(Base):
    """The feed shows the last week by default; the month and year lists choose a calendar month or a whole year, and
    the month list offers only the months of the chosen year that have activity."""

    def test_week_month_and_year(self):
        old = self.observe()
        E.objects.filter(sample_transfer_id=old.transfer_id).update(created_at=timezone.make_aware(timezone.datetime(2025, 3, 15, 12)))
        self.observe(species=self.varicosa, video='iiiiiiiiiii')
        names = lambda query: [line['name'] for line in self.client.get('/news/' + query).context['added']]
        self.assertEqual(names(''), ['Phyllidia varicosa'])
        self.assertEqual(names('?year=2025'), ['Phyllidia ocellata'])
        self.assertEqual(names('?year=2025&month=3'), ['Phyllidia ocellata'])
        # April 2025 has no activity: not offered, so a month kept from another year falls back to the whole year
        self.assertEqual(names('?year=2025&month=4'), ['Phyllidia ocellata'])
        self.assertEqual([m for m, _ in self.client.get('/news/?year=2025').context['month_options']], [3])
        self.assertEqual([m for m, _ in self.client.get('/news/').context['month_options']], [timezone.localdate().month])
        # opening the page: "last week" is pressed
        self.assertRegex(self.client.get('/news/').content.decode(), r'<a class="period"[^>]*aria-current="page">השבוע האחרון</a>')
        self.assertNotIn('aria-current', self.client.get('/news/?year=2025').content.decode().split('class="news-filters"')[1].split('</div>')[0])
        # the last week shows the current month chosen; "all months" (no month, the year kept) is the whole year
        month = timezone.localdate().month
        self.assertIn(f'<option value="{month}" selected>', self.client.get('/news/').content.decode())
        self.assertFalse(self.client.get(f'/news/?month=&year={timezone.localdate().year}').context['period']['week'])
        response = self.client.get('/news/?year=2025&month=3&lang=en')
        self.assertEqual(response.context['period']['label'], 'March 2025')
        self.assertIn(2025, response.context['year_options'])
        self.assertIn('<option value="3" selected>March</option>', response.content.decode())


class ProgressChartTests(Base):
    """The progress chart is one upward bar a day of the running totals (observations behind, species in front, the same
    width, no gaps, the species number only where it changes), follows the
    sea filter; its y axis starts at 0 with grid lines every 20, and its x axis
    shows month names with each year once underneath."""

    def test_bars(self):
        from . import news
        old = self.observe()
        Sample.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
        self.observe(species=self.varicosa, video='jjjjjjjjjjj')
        chart = news.progress_chart('he')
        bars = chart['bars']
        self.assertEqual(len(bars), 41)                                             # one bar a day, 40 days ago to today
        self.assertEqual((bars[0]['obs_value'], bars[-1]['obs_value'], bars[-1]['species_value']), (1, 2, 2))
        self.assertAlmostEqual(bars[-1]['obs']['x'] + bars[-1]['obs']['w'], chart['right'], delta=.5)   # same overall width
        # species numbers only on the days the number changes
        for previous, bar in zip([None] + bars, bars):
            if bar['species_label']:
                self.assertNotEqual(bar['species_value'], previous and previous['species_value'])
        self.assertTrue(bars[-1]['species_label'])                                 # 1 -> 2 species today
        self.assertFalse(any(b['species_label'] for b in bars[1:-1]))              # unchanged days: no number
        for bar in bars:
            self.assertEqual(bar['species']['w'], bar['obs']['w'])                  # the same width
            self.assertEqual(bar['species']['x'], bar['obs']['x'])
            self.assertGreaterEqual(bar['obs']['x'], chart['left'])
            self.assertLessEqual(bar['obs']['x'] + bar['obs']['w'], chart['right'] + .5)
        for a, b in zip(bars, bars[1:]):
            self.assertGreaterEqual(a['obs']['x'] + a['obs']['w'], b['obs']['x'])            # touching: no gap
        html = self.client.get('/news/').content.decode()
        self.assertEqual(html.count('class="bar"'), len(bars))
        # the y axis carries the observation totals the bars reach, outside the plot, drawn after the bars
        self.assertEqual(sorted(t['label'] for t in chart['value_ticks']), sorted({b['obs_value'] for b in bars}))
        self.assertTrue(all(t['label_y'] - t['y'] <= news.LABEL_MAX_SHIFT for t in chart['value_ticks']))
        self.assertGreater(html.index('class="axis-y"'), html.rindex('class="bar"'))
        self.assertIn('class="axis-y" direction="ltr"', html)
        # the number of species inside the species bars that have room for it
        self.assertEqual(html.count('class="bar-value"'), sum(1 for b in bars if b['species_label']))

    def test_the_chart_follows_the_sea_filter(self):
        self.observe()
        self.observe(species=self.varicosa, trip=self.trip_ph, video='hhhhhhhhhhh')
        everything = self.client.get('/news/').context['chart']
        red = self.client.get(f'/news/?sea={self.red.pk}').context
        self.assertEqual((everything['obs_total'], everything['species_total']), (2, 2))
        self.assertEqual((red['chart']['obs_total'], red['chart']['species_total']), (1, 1))
        self.assertEqual(red['chart_sea'], 'ים סוף')

    def test_axes(self):
        from . import news
        self.observe()
        chart = news.progress_chart('he')
        self.assertEqual([t['label'] for t in chart['y_ticks']], [0, 20])
        self.assertEqual(chart['months'][-1]['label'], news.MONTHS['he'][timezone.localdate().month - 1])
        self.assertEqual([y['year'] for y in chart['years']], [timezone.localdate().year])
        # more than 100 as well: the axis starts at 0, in steps of 20
        from collections import Counter
        from unittest.mock import patch
        with patch.object(news, 'Counter', side_effect=lambda items: Counter(list(items) * 130)):   # 130 of each
            chart = news.progress_chart('en')
        labels = [t['label'] for t in chart['y_ticks']]
        ys = sorted(t['label_y'] for t in chart['value_ticks'])
        self.assertTrue(all(b - a >= news.LABEL_GAP for a, b in zip(ys, ys[1:])))   # value labels never overlap
        self.assertEqual(labels[:3], [0, 20, 40])
        self.assertTrue(all(b - a == 20 for a, b in zip(labels, labels[1:])))
        self.assertIn('font-weight:700', self.client.get('/news/').content.decode())


class SlideshowTests(Base):
    """A red play button over the new-videos tile opens /news/slideshow/ for the same period and sea, for everyone.
    Each new video plays from YouTube (www.youtube.com) in a loop; a manager on the Mac plays the offline copy
    wherever there is one on this computer (local_videos.py), and can switch to YouTube for everything."""

    def setUp(self):
        super().setUp()
        import tempfile
        from pathlib import Path
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / 'Phyllidia ocellata.mov').write_bytes(b'video')
        DiveTrip.objects.filter(pk=self.trip.pk).update(local_video_folder=str(self.folder))
        self.trip.refresh_from_db()
        self.with_copy = self.observe(local_video_file='Phyllidia ocellata.mov')
        self.without_copy = self.observe(species=self.varicosa, video='mmmmmmmmmmm')
        self.boss = User.objects.create_superuser('boss', password='pw-test-12345')

    def test_button_for_everyone(self):
        html = self.client.get(f'/news/?sea={self.red.pk}').content.decode()
        self.assertIn(f'class="play-show" href="/news/slideshow/?sea={self.red.pk}"', html)

    def test_visitors_play_everything_from_youtube(self):
        response = self.client.get('/news/slideshow/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual([(i['video_id'], i['src']) for i in response.context['items']],
                         [('aaaaaaaaaaa', ''), ('mmmmmmmmmmm', '')])
        self.assertNotIn('/local-video/', html)
        self.assertIn("tag.src = 'https://www.youtube.com/iframe_api'", html)
        self.assertNotIn('youtube-nocookie', html.split('<main>')[1])
        self.assertIn("if (e.data === YT.PlayerState.ENDED && current === 'yt') next();", html)   # moves on, loops
        self.assertNotIn('source=youtube', html)

    def test_manager_on_the_mac_plays_the_local_copies(self):
        self.client.login(username='boss', password='pw-test-12345')
        response = self.client.get('/news/slideshow/')
        html = response.content.decode()
        self.assertEqual([bool(i['src']) for i in response.context['items']], [True, False])     # the copy, then YouTube
        self.assertIn(f'data-src="/observations/{self.with_copy.pk}/local-video/" data-yt="aaaaaaaaaaa"', html)
        self.assertIn('href="/news/slideshow/?source=youtube"', html)
        forced = self.client.get('/news/slideshow/?source=youtube')
        self.assertFalse(any(i['src'] for i in forced.context['items']))
        self.assertIn('href="/news/slideshow/"', forced.content.decode())

    def test_layout(self):
        # the caption sits under the picture, in the row of buttons: the full-screen stage holds the players alone
        html = self.client.get('/news/slideshow/?lang=en').content.decode()
        self.assertIn('<div class="stage" id="stage" tabindex="-1"><video id="player" playsinline preload="auto" hidden></video>'
                      '<div id="yt-box" hidden><div id="yt"></div></div>', html)
        # arrows on the picture itself, so the next video can be chosen in full screen; where the browser has no
        # element full screen (iPhone) the stage fills the window instead, with a close button
        self.assertIn('id="stage-next" aria-label="Next video"', html)
        self.assertIn('id="stage-prev" aria-label="Previous video"', html)
        self.assertIn('id="stage-close" aria-label="Exit full screen"', html)
        self.assertIn("if (!request) return setPseudo(true);", html)
        self.assertIn("stage.focus({preventScroll: true})", html)                     # keys come back from YouTube
        self.assertIn('.stage-nav{display:none;', html)                               # no arrows outside full screen
        self.assertIn('.stage:fullscreen .stage-nav,.stage:-webkit-full-screen .stage-nav,.stage.pseudo-full .stage-nav{display:flex}', html)
        self.assertIn('.stage-nav:focus,.stage-nav:focus-visible{outline:none}', html)   # no blue frame after a click
        self.assertIn('user-select:none', html)
        self.assertIn('fs: 0', html)                       # YouTube's own full screen would hide the arrows: turned off
        self.assertIn('<div class="show-bar"><div class="caption">', html)
        ActivityEvent = E
        ActivityEvent.objects.filter(kind='video_added').delete()
        self.assertIn('No new videos in this period.', self.client.get('/news/slideshow/?lang=en').content.decode())