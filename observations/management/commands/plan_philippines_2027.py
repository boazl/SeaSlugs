"""One-off: the planned Philippines (Visayas) dive trip of February-March 2027 -- a series of three trips (Sipalay, a
liveaboard, Moalboal) and its summary trip -- with a dive-trip planning (planned_trips.py) and an opening forum
message for each, and the schedule as a site-written article attached to the summary trip.

Creates what is missing: a sea for the Visayas, four regions (the Visayas for the summary trip, and one per part),
the liveaboard's dive sites, the trips (codes from trip_naming), the plannings, the messages and the article.
Dry run by default; --apply backs up the database first and writes everything in one transaction. Refuses to run
twice (the summary trip's title is the marker)."""
import sqlite3
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from observations.models import (Article, ArticleBlock, Country, DiveTrip, ForumMessage, Region, Sample, Sea, Site)
from observations.trip_naming import suggest_code

YEAR = 2027
SEA = ('אינדו-פסיפי - ים ויסאיאס', 'Indo Pacific - Visayan Seas', 'visayas')
SUMMARY = {'region': ('פיליפינים - ויסאיאס', 'Philippines - Visayas', 'Vis'), 'title': 'פיליפינים - ויסאיאס 2027',
           'title_en': 'Philippines - Visayas 2027', 'start': date(YEAR, 2, 20), 'days': 21,
           'description': 'מסע מאקרו לאזור ויסאיאס בפיליפינים בשלושה חלקים: סיפלאי, הפלגה ומואלבואל.'}
PARTS = [
    {'region': ('פיליפינים - סיפלאי', 'Philippines - Sipalay', 'Sip'), 'title': 'סיפלאי 2027', 'title_en': 'Sipalay 2027',
     'start': date(YEAR, 2, 21), 'days': 6, 'sites': [],
     'description': 'הגעה מבקולוד ב־21.2, חמישה ימי צלילה בסיפלאי (22–26.2), ארבע צלילות ביום.'},
    {'region': ('פיליפינים - הפלגה בוויסאיאס', 'Philippines - Visayas liveaboard', 'Liv'), 'title': 'הפלגה בוויסאיאס 2027',
     'title_en': 'Visayas liveaboard 2027', 'start': date(YEAR, 2, 27), 'days': 6,
     'sites': [('סיאטון', 'Siaton'), ('דאואין', 'Dauin'), ('האי אפו', 'Apo Island'), ('האי סיקיחור', 'Siquijor Island'),
               ('האי פנגלאו', 'Panglao Island'), ('האי בליקסג', 'Balicasag Island'), ('האי סומילון', 'Sumilon Island'),
               ('לילואן (אוסלוב)', 'Liloan (Oslob)'), ('האי פסקדור', 'Pescador Island')],
     'description': 'הפלגה מסיפלאי למואלבואל (27.2–4.3), שלוש עד ארבע צלילות ביום: סיאטון, דאואין, האי אפו, סיקיחור, '
                    'פנגלאו, בליקסג, סומילון, לילואן (אוסלוב) ופסקדור.'},
    {'region': ('פיליפינים - מואלבואל', 'Philippines - Moalboal', 'Moa'), 'title': 'מואלבואל 2027', 'title_en': 'Moalboal 2027',
     'start': date(YEAR, 3, 5), 'days': 6, 'sites': [],
     'description': 'שישה ימי צלילה במואלבואל (5–10.3), ארבע צלילות ביום עם ספוטר. ב־11.3 הסעה לשדה התעופה בסבו.'},
]
MESSAGES = {
    'summary': ('מסע לפיליפינים, פברואר–מרץ 2027',
                'אני מתכנן מסע מאקרו לאזור ויסאיאס בפיליפינים, 20.2–12.3.2027, בשלושה חלקים:\n'
                '1. סיפלאי (21–26.2): חמישה ימי צלילה, ארבע צלילות ביום.\n'
                '2. הפלגה (27.2–4.3): מסיפלאי דרך סיאטון, דאואין, האי אפו, סיקיחור, פנגלאו, בליקסג וסומילון ועד מואלבואל, '
                'שלוש עד ארבע צלילות ביום.\n'
                '3. מואלבואל (5–10.3): שישה ימי צלילה, ארבע צלילות ביום.\n\n'
                'לוח הזמנים המלא מצורף כמאמר. אפשר להצטרף לכל המסע או לחלק ממנו — כתבו כאן, או בדיון של כל חלק.'),
    0: ('סיפלאי, 21–26.2.2027',
        'החלק הראשון של המסע: טיסה ב־20.2, הסעה מבקולוד לסיפלאי והגעה ב־21.2. ארבעה ימי צלילה מלאים (22–25.2, ארבע '
        'צלילות ביום) ויום חמישי של צלילה או טיול (26.2). כאן מתאמים הצטרפות, לינה וצלילות בסיפלאי.'),
    1: ('הפלגה, 27.2–4.3.2027',
        'החלק השני: הפלגה מסיפלאי למואלבואל, שלוש עד ארבע צלילות ביום.\n'
        '27.2 סיפלאי – סיאטון – דאואין\n28.2 האי אפו – דאואין\n1.3 האי סיקיחור – האי פנגלאו\n2.3 האי בליקסג\n'
        '3.3 האי פנגלאו – האי סומילון – לילואן\n4.3 לילואן (אוסלוב) – האי פסקדור – מואלבואל\n'
        'כאן מתאמים הצטרפות להפלגה ושאלות על המסלול.'),
    2: ('מואלבואל, 5–10.3.2027',
        'החלק השלישי: חמישה ימי צלילה במואלבואל (5–9.3, ארבע צלילות ביום, עם ספוטר) ויום שישי של צלילה או טיול '
        '(10.3). ב־11.3 הסעה לשדה התעופה בסבו וטיסה, חזרה ארצה ב־12.3. כאן מתאמים הצטרפות, לינה וצלילות במואלבואל.'),
}
SCHEDULE = [   # date, day he, day en, activity he, activity en, dives, area, route
    ('20.2.2027', 'ש', 'Sat', 'טיסה', 'Flight', '', '', ''),
    ('21.2.2027', 'א', 'Sun', 'הגעה לסיפלאי', 'Arrival in Sipalay', '', 'Sipalay', ''),
    ('22.2.2027', 'ב', 'Mon', 'יום צלילה 1', 'Dive day 1', '4', 'Sipalay', ''),
    ('23.2.2027', 'ג', 'Tue', 'יום צלילה 2', 'Dive day 2', '4', 'Sipalay', ''),
    ('24.2.2027', 'ד', 'Wed', 'יום צלילה 3', 'Dive day 3', '4', 'Sipalay', ''),
    ('25.2.2027', 'ה', 'Thu', 'יום צלילה 4', 'Dive day 4', '4', 'Sipalay', ''),
    ('26.2.2027', 'ו', 'Fri', 'יום צלילה 5 / טיול', 'Dive day 5 / excursion', '', 'Sipalay', ''),
    ('27.2.2027', 'ש', 'Sat', 'הפלגה 1', 'Liveaboard 1', '3–4', 'Siaton', 'Sipalay - Siaton - Dauin'),
    ('28.2.2027', 'א', 'Sun', 'הפלגה 2', 'Liveaboard 2', '3–4', 'Apo', 'Apo Island - Dauin'),
    ('1.3.2027', 'ב', 'Mon', 'הפלגה 3', 'Liveaboard 3', '3–4', 'Siquijor - Panglao', 'Siquijor Island - Panglao Island'),
    ('2.3.2027', 'ג', 'Tue', 'הפלגה 4', 'Liveaboard 4', '3–4', 'Balicasag', 'Balicasag Island'),
    ('3.3.2027', 'ד', 'Wed', 'הפלגה 5', 'Liveaboard 5', '3–4', 'Panglao - Sumilon', 'Panglao Island - Sumilon Island - Liloan'),
    ('4.3.2027', 'ה', 'Thu', 'סיום ההפלגה והגעה למואלבואל', 'End of the liveaboard, arrival in Moalboal', '', 'Liloan - Pescador',
     'Liloan (Oslob) - Pescador Island - Moalboal'),
    ('5.3.2027', 'ו', 'Fri', 'יום צלילה 1', 'Dive day 1', '4', 'Moalboal', ''),
    ('6.3.2027', 'ש', 'Sat', 'יום צלילה 2', 'Dive day 2', '4', 'Moalboal', ''),
    ('7.3.2027', 'א', 'Sun', 'יום צלילה 3', 'Dive day 3', '4', 'Moalboal', ''),
    ('8.3.2027', 'ב', 'Mon', 'יום צלילה 4', 'Dive day 4', '4', 'Moalboal', ''),
    ('9.3.2027', 'ג', 'Tue', 'יום צלילה 5', 'Dive day 5', '4', 'Moalboal', ''),
    ('10.3.2027', 'ד', 'Wed', 'יום צלילה 6 / טיול', 'Dive day 6 / excursion', '', 'Moalboal', ''),
    ('11.3.2027', 'ה', 'Thu', 'טיסה', 'Flight', '', '', ''),
    ('12.3.2027', 'ו', 'Fri', 'חזרה ארצה', 'Back home', '', '', ''),
]
ARTICLE_SLUG = 'philippines-visayas-2027-schedule'


def isolate_ranges(text):
    """Date and number ranges ("21–26.2", "12.3.2027–20.2") isolated (LRI..PDI), so Hebrew text keeps them in order."""
    import re
    return re.sub(r'(?<![\u2066\d.])(\d[\d.]*–\d[\d.]*\d)', '\u2066\\1\u2069', text)


def schedule_table(lang):
    if lang == 'he':
        # Latin place names and ranges are isolated (LRI..PDI), so a Hebrew page keeps "Apo Island - Dauin" and "3–4"
        # in their own order
        ltr = lambda text: f'\u2066{text}\u2069' if text else ''
        rows = ['תאריך | יום | פעילות | צלילות | אזור | מסלול'] + [
            ' | '.join((d, day, act, ltr(dives), ltr(area), ltr(route))) for d, day, _, act, _, dives, area, route in SCHEDULE]
    else:
        rows = ['Date | Day | Activity | Dives | Area | Route'] + [
            ' | '.join((d, day, act, dives, area, route)) for d, _, day, _, act, dives, area, route in SCHEDULE]
    return '\n'.join(rows)


def make_backup():
    name = settings.DATABASES['default']['NAME']
    backup = Path(settings.DATA_DIR) / 'backups' / f'before-plan-philippines-2027-{timezone.now():%Y%m%d-%H%M%S}.sqlite3'
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(name)) as source, sqlite3.connect(str(backup)) as target:
        source.backup(target)
    return backup


class Command(BaseCommand):
    help = 'Create the planned Philippines (Visayas) 2027 trip series. Dry run unless --apply.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if DiveTrip.objects.filter(title=SUMMARY['title']).exists():
            raise CommandError(f'המסע "{SUMMARY["title"]}" כבר קיים — הפקודה כבר הורצה.')
        if Article.objects.filter(slug=ARTICLE_SLUG).exists():
            raise CommandError(f'המאמר {ARTICLE_SLUG} כבר קיים.')
        owner = User.objects.get(username='boazl')
        country = Country.objects.get(name_en='Philippines')
        if not options['apply']:
            self.stdout.write('Dry run. Would create: the sea, 4 regions, 9 sites, 4 trips, 4 plannings, 4 forum messages '
                              'and the schedule article. Run with --apply.')
            return
        self.stdout.write(f'Backup: {make_backup()}')
        with transaction.atomic():
            sea, made = Sea.objects.get_or_create(name=SEA[0], defaults={'name_en': SEA[1], 'url_code': SEA[2]})
            self.stdout.write(f'{"+" if made else "="} sea {sea.name}')

            def region(names):
                obj, made = Region.objects.get_or_create(name=names[0], country=country,
                                                         defaults={'name_en': names[1], 'sea': sea, 'trip_code': names[2]})
                if not obj.trip_code:      # the region's letters in trip codes (Vis27Feb, Sip27Feb...)
                    Region.objects.filter(pk=obj.pk).update(trip_code=names[2]); obj.trip_code = names[2]
                self.stdout.write(f'{"+" if made else "="} region {obj.name}')
                return obj

            def trip(spec, reg, summary=None):
                start = spec['start']
                obj = DiveTrip(title=spec['title'], kind=DiveTrip.Kind.DIVE, year=start.year, month=start.month,
                               start_day=start.day, duration_days=spec['days'], country=country, region=reg,
                               country_name='Philippines', region_name=reg.name_en, sea_name=sea.name_en,
                               description_he=isolate_ranges(spec['description']), summary_trip=summary,
                               code=suggest_code(owner, reg, start.year, start.month, start.day, persist=True))
                obj.full_clean(); obj.save()
                self.stdout.write(f'+ trip {obj.code} {obj.title} {start:%d.%m.%Y} ({spec["days"]} days)')
                return obj

            def planning(trip_obj, spec):
                s = Sample(kind=Sample.Kind.PLANNED, trip=trip_obj, owner=owner, title=spec['title'],
                           title_en=spec['title_en'], note_he=isolate_ranges(spec['description']))
                s.save_reviewed(actor=owner)
                self.stdout.write(f'+ planning #{s.pk} {s.title} ({s.status})')
                return s

            def message(sample, key):
                subject, text = MESSAGES[key]
                m = ForumMessage.objects.create(observation=sample, user=owner, subject=isolate_ranges(subject), text=isolate_ranges(text))
                self.stdout.write(f'+ forum message #{m.pk} "{subject}"')

            summary_trip = trip(SUMMARY, region(SUMMARY['region']))
            parts = []
            for spec in PARTS:
                reg = region(spec['region'])
                for he, en in spec['sites']:
                    site, made = Site.objects.get_or_create(name=he, region=reg, defaults={'name_en': en})
                    self.stdout.write(f'{"+" if made else "="}   site {site.name} / {site.name_en}')
                parts.append(trip(spec, reg, summary_trip))
            # the parts' plannings first, with their own notes; the summary's planning then finds them in place
            part_plannings = [planning(t, spec) for t, spec in zip(parts, PARTS)]
            summary_planning = planning(summary_trip, SUMMARY)
            message(summary_planning, 'summary')
            for number, sample in enumerate(part_plannings):
                message(sample, number)

            article = Article(slug=ARTICLE_SLUG, title_he='לוח זמנים: פיליפינים - ויסאיאס 2027',
                              title_en='Schedule: Philippines - Visayas 2027', published_on=timezone.localdate(),
                              show_on_home=False)
            article.full_clean(); article.save()
            ArticleBlock.objects.create(article=article, position=10, kind=ArticleBlock.Kind.PARAGRAPH,
                text_he='לוח הזמנים של המסע המתוכנן לאזור ויסאיאס בפיליפינים, 20.2–12.3.2027: סיפלאי, הפלגה ומואלבואל.',
                text_en='The schedule of the planned trip to the Visayas, Philippines, 20.2–12.3.2027: Sipalay, a liveaboard and Moalboal.')
            ArticleBlock.objects.create(article=article, position=20, kind=ArticleBlock.Kind.TABLE,
                                        text_he=schedule_table('he'), text_en=schedule_table('en'))
            summary_trip.articles.add(article)
            self.stdout.write(f'+ article {article.slug} (schedule, {len(SCHEDULE)} days), attached to {summary_trip.code}')
