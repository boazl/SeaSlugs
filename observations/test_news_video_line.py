"""The progress chart on /news/ also shows the running number of videos."""
from datetime import timedelta

from django.utils import timezone

from .models import Sample
from .test_news_activity import Base, png


class ProgressChartVideoTests(Base):
    """The progress chart counts videos (published observations with a YouTube link, dated by the observation) as a
    running total per day, drawn as one step line in front of the bars; the total appears in the summary line, the
    legend and each day's tooltip, and follows the sea filter."""

    def test_running_total_and_line(self):
        from . import news
        old = self.observe()
        Sample.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=10))
        self.observe(species=self.varicosa, video='', image=png())
        self.observe(species=self.varicosa, video='kkkkkkkkkkk', trip=self.trip_ph)
        chart = news.progress_chart('he')
        bars = chart['bars']
        self.assertEqual([bars[0]['video_value'], bars[-1]['video_value']], [1, 2])
        self.assertEqual(chart['video_total'], 2)
        self.assertEqual(chart['obs_total'], 3)
        path = chart['video_path']
        self.assertTrue(path.startswith('M'))
        self.assertEqual(path.count('H'), len(bars))                               # one stretch a day
        html = self.client.get('/news/').content.decode()
        self.assertEqual(html.count('class="video-line"'), 1)
        self.assertGreater(html.index('class="video-line"'), html.rindex('class="bar"'))   # in front of the bars
        self.assertIn('2 סרטונים', html)
        self.assertIn('סרטונים (2)', html)

    def test_sea_filter_and_english(self):
        self.observe()
        self.observe(species=self.varicosa, trip=self.trip_ph, video='mmmmmmmmmmm')
        red = self.client.get(f'/news/?sea={self.red.pk}').context['chart']
        self.assertEqual(red['video_total'], 1)
        html = self.client.get('/news/?lang=en').content.decode()
        self.assertIn('videos (2)', html)
