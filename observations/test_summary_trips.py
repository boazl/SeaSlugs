"""Summary trips (DiveTrip.summary_trip): a series of small trips summed up by one trip."""
import json
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from .article_render import table, table_rows
from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea
from .table_transfer import export_table, plan, apply, fingerprint

TODAY = date.today()


class SummarySetup(TestCase):
    def setUp(self):
        self.manager = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927')
        self.member = User.objects.create_user('member', password='a-valid-password-927')
        self.country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין', name_en='South China Sea')
        self.region = Region.objects.create(name='אנילאו', name_en='Anilao', country=self.country, sea=sea)
        self.other_region = Region.objects.create(name='רומבלון', name_en='Romblon', country=self.country, sea=sea)
        self.summary = DiveTrip.objects.create(title='סדרת 2025', code='S25', year=2025, month=4, country=self.country, region=self.region)
        self.part1 = DiveTrip.objects.create(title='אנילאו 2025', code='A25', year=2025, month=3, country=self.country,
                                             region=self.region, summary_trip=self.summary)
        self.part2 = DiveTrip.objects.create(title='רומבלון 2025', code='R25', year=2025, month=4, country=self.country,
                                             region=self.other_region, summary_trip=self.summary)
        mk = lambda name: Species.objects.create(scientific_name=name, genus=name.split()[0], species=name.split()[1], author='A, 1900')
        self.sp1, self.sp2, self.sp3 = mk('Chromodoris annae'), mk('Phyllidia ocellata'), mk('Hypselodoris apolegma')
        self.obs1 = self.observe(self.part1, self.sp1, '11111111111')
        self.obs2 = self.observe(self.part2, self.sp2, '22222222222')
        self.obs3 = self.observe(self.summary, self.sp3, '33333333333')
        self.collection = Sample(owner=self.manager, kind='collection', trip=self.summary, title='כל המינים בסדרה',
                                 video_url='https://youtu.be/CCCCCCCCCCC')
        self.collection.save_reviewed(actor=self.manager, approve=True)

    def observe(self, trip, species, video):
        s = Sample(owner=self.manager, trip=trip, species=species, video_url=f'https://youtu.be/{video}')
        s.save_reviewed(actor=self.manager, approve=True)
        return s


class SummaryRulesTests(SummarySetup):
    """One level only: the summary trip is one without a summary trip of its own, a trip never sums itself up, and a
    trip that sums up others cannot have a summary trip."""

    def test_rules(self):
        self.summary.summary_trip = self.part1
        with self.assertRaises(ValidationError):
            self.summary.full_clean()          # a summary trip has no summary trip
        self.summary.summary_trip = None
        lone = DiveTrip.objects.create(title='x', code='X1', year=2024)
        lone.summary_trip = self.part1
        with self.assertRaises(ValidationError):
            lone.full_clean()                  # the chosen trip belongs to a series itself
        lone.summary_trip = lone
        with self.assertRaises(ValidationError):
            lone.full_clean()
        lone.summary_trip = self.summary
        lone.full_clean()

    def test_admin_choices(self):
        self.client.force_login(self.manager)
        html = self.client.get(f'/admin/observations/divetrip/{self.part1.pk}/change/').content.decode()
        select = html.split('name="summary_trip"')[1].split('</select>')[0]
        self.assertIn(f'value="{self.summary.pk}"', select)
        self.assertNotIn(f'value="{self.part2.pk}"', select)       # has a summary trip itself
        self.assertNotIn(f'value="{self.part1.pk}"', select)       # itself
        self.assertIn('data-region=', select)
        self.assertIn('data-year="2025"', select)
        self.assertIn('summary_trip_picker.js', html)
        html = self.client.get(f'/admin/observations/divetrip/{self.summary.pk}/change/').content.decode()
        self.assertIn('אנילאו 2025 [A25]', html)                   # the trips it sums up
        self.assertIn('disabled', html.split('name="summary_trip"')[1].split('>')[0])


class SummarySpeciesTests(SummarySetup):
    """The summary trip's species are its own observations plus those of the trips it sums up -- on its trip page (each
    card looked up in its own trip's place), in its species count, in the public trips table and in the gallery's trip
    filter (catalog trips[id].sub_trips)."""

    def test_trip_page(self):
        html = self.client.get('/trip/S25/').content.decode()
        for sample in (self.obs1, self.obs2, self.obs3):
            self.assertIn(f'#obs-{sample.pk}"', html)
        self.assertIn('המסע מסכם את המסעות', html)
        self.assertEqual(self.summary.display_species_count, 3)

    def test_trips_table(self):
        html = self.client.get('/observations/trips/').content.decode()
        row = html.split(f'id="trip-detail-{self.summary.pk}"')[1].split('</tr>')[0]
        for sample in (self.obs1, self.obs2, self.obs3):
            self.assertIn(f'#obs-{sample.pk}', row)

    def test_gallery_catalog(self):
        js = self.client.get('/catalog.js').content.decode()
        data = json.loads(js[js.index('{'):js.rindex('}') + 1])
        self.assertEqual(sorted(data['trips'][str(self.summary.pk)]['sub_trips']), sorted([str(self.part1.pk), str(self.part2.pk)]))
        self.assertIn('function tripFamily', open('dist/app.js', encoding='utf-8').read())


class SummaryTransferTests(SummarySetup):
    """The trips table carries the summary trip by its code; a summary trip that is new in the same file is linked after
    the rows are saved; a file without the field keeps the destination's value."""

    def test_export_and_link_new_summary(self):
        doc = json.loads(json.dumps(export_table('trips')))
        rows = {r['code']: r for r in doc['rows']}
        self.assertEqual(rows['A25']['summary_trip'], 'S25')
        self.assertIsNone(rows['S25']['summary_trip'])
        # the destination knows neither the summary trip nor the link: both arrive with the file
        DiveTrip.objects.filter(code__in=['A25', 'R25']).update(summary_trip=None)
        Sample.objects.filter(trip__code='S25').delete()
        DiveTrip.objects.filter(code='S25').delete()
        doc['rows'] = [rows['A25'], rows['S25']]           # the part before its summary
        apply(doc, fingerprint(), backup=Path('test.sqlite3'))
        self.assertEqual(DiveTrip.objects.get(code='A25').summary_trip.code, 'S25')

    def test_older_file_keeps_the_value(self):
        doc = json.loads(json.dumps(export_table('trips')))
        for r in doc['rows']:
            del r['summary_trip']
        items = plan(doc)
        self.assertTrue(all(i['action'] == 'same' for i in items))


class SeriesPlanningTests(TestCase):
    """A planning on a summary trip opens a planning (a discussion) for each trip of the series that has not ended --
    also for a trip that joins the series later. The planning section shows them inside the series card, the forum links
    the series and its trips' discussions; the series stays open until its last trip ends."""

    def setUp(self):
        self.member = User.objects.create_user('member', password='a-valid-password-927')
        self.manager = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=Sea.objects.create(name='ים סוף'))
        y = TODAY.year + 1
        self.summary = DiveTrip.objects.create(title='סדרת אילת', code='SE', year=y, month=1, country=country, region=region)
        self.part1 = DiveTrip.objects.create(title='אילת ינואר', code='E1', year=y, month=1, country=country, region=region, summary_trip=self.summary)
        self.part2 = DiveTrip.objects.create(title='אילת מרץ', code='E3', year=y, month=3, country=country, region=region, summary_trip=self.summary)
        self.series = Sample(kind='planned', trip=self.summary, owner=self.member, title='סדרת צלילות באילת')
        self.series.save_reviewed()

    def test_trip_plannings_created(self):
        parts = Sample.objects.filter(kind='planned', trip__summary_trip=self.summary)
        self.assertEqual(sorted(p.trip.code for p in parts), ['E1', 'E3'])
        self.assertTrue(all(p.owner == self.member and p.status == 'published' for p in parts))
        self.assertEqual(Sample.objects.get(trip=self.part1).title, 'אילת ינואר')
        self.series.save_reviewed()                          # no duplicates
        self.assertEqual(Sample.objects.filter(kind='planned').count(), 3)

    def test_trip_joining_later(self):
        y = TODAY.year + 1
        late = DiveTrip.objects.create(title='אילת מאי', code='E5', year=y, month=5, region=self.summary.region, country=self.summary.country)
        self.client.force_login(self.manager)
        response = self.client.post(f'/admin/observations/divetrip/{late.pk}/change/', {
            'code': 'E5', 'kind': 'dive', 'title': 'אילת מאי', 'year': y, 'month': 5, 'country': self.summary.country_id,
            'region': self.summary.region_id, 'summary_trip': self.summary.pk, 'source_metadata': '{}'})
        self.assertEqual(response.status_code, 302, response.content.decode()[:3000] if response.status_code != 302 else '')
        self.assertTrue(Sample.objects.filter(kind='planned', trip=late).exists())

    def test_series_open_until_the_last_trip(self):
        DiveTrip.objects.filter(pk=self.summary.pk).update(year=TODAY.year - 1)
        self.series.refresh_from_db()
        self.assertTrue(self.series.planning_open)           # the March trip has not ended

    def test_forum_landing_groups_the_series(self):
        from .models import ForumMessage
        part1, part2 = Sample.objects.get(trip=self.part1), Sample.objects.get(trip=self.part2)
        ForumMessage.objects.create(observation=part2, user=self.member, text='מרץ')       # the latest: the group comes first
        ForumMessage.objects.create(observation=self.series, user=self.member, text='הסדרה')
        ForumMessage.objects.create(observation=part1, user=self.member, text='ינואר')
        html = self.client.get('/forum/?lang=he').content.decode()
        listing = html.split('class="discussion-list"')[1].split('<script>')[0]
        self.assertEqual(listing.count('<li class="discussion" id="discussion-'), 3)
        head = listing.split(f'id="discussion-{self.series.pk}"')[1]
        children = head.split('class="discussion-children"')[1]
        self.assertLess(children.index(f'id="discussion-{part1.pk}"'), children.index(f'id="discussion-{part2.pk}"'))   # by date
        self.assertIn('ינואר', children)
        self.assertIn('הסדרה', head.split('class="discussion-children"')[0])

    def test_trip_discussion_page(self):
        """/forum/trip/<code>/: the series' discussion on its own page, to send to people -- no picker, the trips'
        discussions indented under it by date with their messages open, one writing box with a choice of trip that
        brings the writer back here."""
        from .models import ForumMessage
        part1, part2 = Sample.objects.get(trip=self.part1), Sample.objects.get(trip=self.part2)
        ForumMessage.objects.create(observation=part1, user=self.member, text='ינואר')
        html = self.client.get('/forum/trip/SE/?lang=he').content.decode()
        self.assertNotIn('id="choose"', html)
        self.assertNotIn('<h1>', html.split('<main>')[1])
        children = html.split('class="discussion-children"')[1]
        self.assertLess(children.index(f'id="discussion-{part1.pk}"'), children.index(f'id="discussion-{part2.pk}"'))
        self.assertIn('ינואר', children)
        self.assertIn('/forum/trip/E1/', children)
        self.client.force_login(self.member)
        html = self.client.get('/forum/trip/SE/?lang=he').content.decode()
        select = html.split('name="obs"')[1].split('</select>')[0]
        for sample in (self.series, part1, part2):
            self.assertIn(f'value="{sample.pk}"', select)
        # "only to <the discussion manager's name>" (the series' owner; changes with the chosen trip)
        self.assertIn('רק ל<span class="manager-name">member</span>', html)
        self.assertIn('data-manager="member"', select)
        response = self.client.post('/forum/', {'obs': part2.pk, 'audience': 'all', 'text': 'מצטרף במרץ', 'next': '/forum/trip/SE/'})
        message = ForumMessage.objects.get(text='מצטרף במרץ')
        self.assertEqual((message.observation_id, response['Location']), (part2.pk, f'/forum/trip/SE/#m-{message.pk}'))
        self.assertEqual(self.client.get('/forum/trip/NOPE/').status_code, 404)
        # no copy-link buttons: a trip's row opens its own page, whose address is the link to send
        ForumMessage.objects.create(observation=self.series, user=self.member, text='סדרה')
        landing = self.client.get('/forum/?lang=he').content.decode()
        self.assertIn('class="discussion-row" href="/forum/trip/SE/"', landing)
        for url in ('/forum/trip/SE/', '/forum/?lang=he', '/observations/trips/', '/planning/SE/', f'/forum/?obs={self.series.pk}'):
            self.assertNotIn('data-copy-url', self.client.get(url).content.decode(), url)

    def test_planning_section_and_forum(self):
        html = self.client.get('/observations/trips/?view=planning').content.decode()
        section = html.split('id="planning"')[1].split('</section>')[0]
        card = section.split(f'id="planned-{self.series.pk}"')[1]
        part = Sample.objects.get(trip=self.part1)
        self.assertIn(f'id="planned-{part.pk}"', card)                    # inside the series card
        self.assertEqual(section.count('<article class="planning"'), 1)
        html = self.client.get(f'/forum/?obs={self.series.pk}').content.decode()
        self.assertIn(f'href="/forum/?obs={part.pk}"', html.split('הדיונים במסעות הסדרה')[1])
        html = self.client.get(f'/forum/?obs={part.pk}').content.decode()
        self.assertIn(f'href="/forum/?obs={self.series.pk}"', html.split('חלק מסדרת המסעות')[1])


class ExcelTableTests(TestCase):
    """A table block takes a table copied from Excel and pasted as is: tab-separated cells (a quoted cell may hold a
    line break), rows padded to the widest, trailing empty columns dropped. The | form keeps working."""

    def test_pasted_from_excel(self):
        text = 'יום\tאתר\tהערות\t\n1\tאנילאו\t"צלילת לילה\nבשעה 18:00"\t\n2\tרומבלון\t\t\n'
        self.assertEqual(table_rows(text), [['יום', 'אתר', 'הערות'], ['1', 'אנילאו', 'צלילת לילה\nבשעה 18:00'], ['2', 'רומבלון', '']])
        html = table(text, set())
        self.assertIn('<th>אתר</th>', html)
        self.assertIn('צלילת לילה<br>בשעה 18:00', html)

    def test_pipe_form(self):
        self.assertEqual(table_rows('a | b\n1 | 2 | 3'), [['a', 'b', ''], ['1', '2', '3']])


class PlanPhilippines2027CommandTests(TestCase):
    """The one-off plan_philippines_2027 command: a dry run changes nothing; --apply creates the summary trip and its
    three trips (one series, future dates), a planning and an opening forum message for each, the liveaboard's sites
    and the schedule article attached to the summary trip; it refuses to run twice."""

    def setUp(self):
        User.objects.create_user('boazl', password='a-valid-password-927')
        Country.objects.create(name='פיליפינים', name_en='Philippines')

    def run_command(self, *args):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        with patch('observations.management.commands.plan_philippines_2027.make_backup', return_value='stub'):
            call_command('plan_philippines_2027', *args, stdout=StringIO())

    def test_dry_run_and_apply(self):
        from django.core.management.base import CommandError
        from .models import Article, ForumMessage, Site
        self.run_command()
        self.assertFalse(DiveTrip.objects.exists())
        self.run_command('--apply')
        summary = DiveTrip.objects.get(title='פיליפינים - ויסאיאס 2027')
        self.assertEqual(sorted(t.title for t in summary.sub_trips.all()), ['הפלגה בוויסאיאס 2027', 'מואלבואל 2027', 'סיפלאי 2027'])
        self.assertEqual(summary.series_end_date(), date(2027, 3, 12))
        plannings = Sample.objects.filter(kind='planned', status='published')
        self.assertEqual(plannings.count(), 4)
        self.assertEqual(ForumMessage.objects.filter(observation__in=plannings).count(), 4)
        self.assertEqual(Site.objects.filter(region__name='פיליפינים - הפלגה בוויסאיאס').count(), 9)
        article = Article.objects.get(slug='philippines-visayas-2027-schedule')
        self.assertIn(article, summary.articles.all())
        self.assertEqual(len(table_rows(article.blocks.get(kind='table').text_he)), 22)
        with self.assertRaises(CommandError):
            self.run_command('--apply')


class ArticleLinkThumbTests(TestCase):
    """An article without a picture (a site-written article with no figure, e.g. a schedule) is listed without an
    empty thumbnail box."""

    def test_no_empty_thumbnail(self):
        from .articles import article_links
        from .models import Article, ArticleBlock
        from django.template.loader import render_to_string
        article = Article.objects.create(slug='schedule', title_he='לוח זמנים', published_on=date.today())
        ArticleBlock.objects.create(article=article, kind='table', text_he='א | ב\n1 | 2')
        html = render_to_string('observations/_article_links.html', {'links': article_links([article], 'he'), 'lang': 'he'})
        self.assertIn('לוח זמנים', html)
        self.assertNotIn('class="article-thumb"', html)


class ArticleSiteEditTests(TestCase):
    """A dive trip's organizer (the owner of its planning / collection observation) edits the trip's site-written
    article -- e.g. the schedule -- on the site at /articles/<slug>/edit/, not in the admin: titles and sections in both
    languages, adding and deleting sections; figures stay. Others cannot; staff keep the admin's edit link."""

    def setUp(self):
        from .models import Article, ArticleBlock
        self.ofer = User.objects.create_user('ofer', password='a-valid-password-927')
        self.other = User.objects.create_user('other', password='a-valid-password-927')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=Sea.objects.create(name='ים סוף'))
        self.trip = DiveTrip.objects.create(title='סדרה', code='SR', year=TODAY.year + 1, month=4, country=country, region=region)
        Sample(kind='planned', trip=self.trip, owner=self.ofer, title='סדרה').save_reviewed()
        self.article = Article.objects.create(slug='schedule', title_he='לוח זמנים', published_on=TODAY)
        self.block = ArticleBlock.objects.create(article=self.article, position=10, kind='table', text_he='יום | אתר\n1 | דהב')
        self.trip.articles.add(self.article)

    def data(self, **extra):
        data = {'title_he': 'לוח זמנים מעודכן', 'title_en': 'Schedule', 'subtitle_he': '', 'subtitle_en': '',
                'blocks-TOTAL_FORMS': '2', 'blocks-INITIAL_FORMS': '1', 'blocks-MIN_NUM_FORMS': '0', 'blocks-MAX_NUM_FORMS': '1000',
                'blocks-0-id': str(self.block.pk), 'blocks-0-position': '10', 'blocks-0-kind': 'table',
                'blocks-0-title_he': '', 'blocks-0-title_en': '', 'blocks-0-text_he': 'יום\tאתר\n1\tאילת', 'blocks-0-text_en': '',
                'blocks-1-position': '20', 'blocks-1-kind': 'paragraph', 'blocks-1-title_he': '', 'blocks-1-title_en': '',
                'blocks-1-text_he': 'הערה חדשה', 'blocks-1-text_en': ''}
        data.update(extra)
        return data

    def test_organizer_edits_on_the_site(self):
        self.client.force_login(self.ofer)
        page = self.client.get('/articles/schedule/').content.decode()
        self.assertIn('href="/articles/schedule/edit/"', page)
        self.assertNotIn('/admin/', page.split('<main>')[1])
        response = self.client.post('/articles/schedule/edit/', self.data())
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000] if response.status_code != 302 else '')
        self.article.refresh_from_db()
        self.assertEqual(self.article.title_he, 'לוח זמנים מעודכן')
        self.assertEqual(list(self.article.blocks.order_by('position').values_list('kind', 'text_he')),
                         [('table', 'יום\tאתר\n1\tאילת'), ('paragraph', 'הערה חדשה')])

    def test_delete_a_section_but_not_all(self):
        self.client.force_login(self.ofer)
        response = self.client.post('/articles/schedule/edit/', self.data(**{'blocks-0-DELETE': 'on', 'blocks-1-text_he': ''}))
        self.assertEqual(response.status_code, 200)              # an article needs a section
        self.assertTrue(self.article.blocks.exists())
        self.client.post('/articles/schedule/edit/', self.data(**{'blocks-0-DELETE': 'on'}))
        self.assertEqual(list(self.article.blocks.values_list('kind', flat=True)), ['paragraph'])

    def test_others_cannot(self):
        self.assertEqual(self.client.get('/articles/schedule/edit/').status_code, 302)        # to the login page
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/articles/schedule/edit/').status_code, 404)
        self.assertNotIn('/articles/schedule/edit/', self.client.get('/articles/schedule/').content.decode())
