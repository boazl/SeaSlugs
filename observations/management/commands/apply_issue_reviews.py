"""Writes the reviews of the identification issues (observations/data/issue_reviews.json: Claude's recommendation
after examining an issue, the owner's decision, and optionally the issue's state) into the identification-issues table.

An issue is found by its transfer_id (the same in both environments). A recommendation or a decision is written only
where the field is still empty -- text edited on the site is never overwritten; a state is set only while the issue is
still under review (open / checking), never on one that was decided or closed. A dry run by default; --apply backs up
the database first.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from observations.models import IdentificationIssue

DATA = Path(__file__).resolve().parents[2] / 'data' / 'issue_reviews.json'
REVIEW_STATES = (IdentificationIssue.Status.OPEN, IdentificationIssue.Status.CHECKING)


def planned_changes(reviews):
    """[(issue, {field: value})] of the changes the reviews make."""
    out = []
    for review in reviews:
        issue = IdentificationIssue.objects.filter(transfer_id=review['transfer_id']).first()
        if issue is None:
            continue
        changes = {f: review[f] for f in ('recommendation', 'decision') if review.get(f) and not getattr(issue, f).strip()}
        state = review.get('status')
        if state in (IdentificationIssue.Status.CHECKING, IdentificationIssue.Status.DECIDED) and issue.status in REVIEW_STATES \
                and issue.status != state:
            changes['status'] = state
        if changes:
            out.append((issue, changes))
    return out


class Command(BaseCommand):
    help = 'Write the identification-issue reviews (recommendation / decision) from observations/data/issue_reviews.json.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='write the changes (default: only show them)')

    def handle(self, *args, **options):
        reviews = json.loads(DATA.read_text(encoding='utf-8'))
        plan = planned_changes(reviews)
        for issue, changes in plan:
            self.stdout.write(f'#{issue.pk} {issue}: ' + ', '.join(changes))
        if not plan:
            self.stdout.write('Nothing to write.')
            return
        if not options['apply']:
            self.stdout.write('Dry run -- run again with --apply to write.')
            return
        from observations.table_transfer import create_backup
        create_backup()
        for issue, changes in plan:
            for field, value in changes.items():
                setattr(issue, field, value)
            issue.updated_at = timezone.now()
            issue.save()
        self.stdout.write(f'Written: {len(plan)} issues.')
