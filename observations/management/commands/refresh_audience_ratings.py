"""Recomputes every observation's audience photo / video rating from its stored ratings (MediaRating rows,
ratings.bayesian). Safe to run any time: the averages are derived data, and the individual ratings are untouched.
Used to repair the averages after a samples transfer reset them (fixed in sample_transfer.sample_plan)."""
from django.core.management.base import BaseCommand

from observations.models import MediaRating, Sample
from observations.ratings import MEDIA, refresh_audience


class Command(BaseCommand):
    help = 'Recompute the audience photo / video ratings from the stored ratings.'

    def handle(self, *args, **options):
        rated = set(MediaRating.objects.values_list('sample_id', 'media'))
        stale = {(pk, media) for media in MEDIA
                 for pk in Sample.objects.filter(**{f'audience_{media}_rating__isnull': False}).values_list('pk', flat=True)}
        for sample_id, media in sorted(rated | stale):
            refresh_audience(sample_id, media)
        self.stdout.write(f'Recomputed {len(rated | stale)} audience ratings.')
