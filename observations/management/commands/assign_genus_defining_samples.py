"""Give every order / sub-order / superfamily, family and genus row a defining sample that fits it
(see observations/defining.py): a row whose defining sample is of the wrong level or taxon, deleted,
or shows nothing while another would, gets the first one that fits; an empty row is filled.

Dry run by default; --apply writes (after a database backup)."""
from django.core.management.base import BaseCommand
from django.db import transaction

from observations.models import TaxonGenus, TaxonFamily, TaxonOrder
from observations.table_transfer import create_backup


class Command(BaseCommand):
    help = "Fix every taxonomy row's defining sample to one that fits its level (first that fits)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write to the database (default: dry run report only).')

    def handle(self, *args, **options):
        from observations.defining import repair, fits, first_choice

        def run(apply):
            changed = {'orders': 0, 'families': 0, 'genera': 0}
            for key, model in (('orders', TaxonOrder), ('families', TaxonFamily), ('genera', TaxonGenus)):
                for row in model.objects.select_related('defining_sample'):
                    if apply:
                        changed[key] += repair(row)
                    else:
                        current = row.defining_sample
                        picked = first_choice(row)
                        if (current is None or not fits(row, current)) and (picked.pk if picked else None) != row.defining_sample_id:
                            changed[key] += 1
            return changed

        if options['apply']:
            backup = create_backup()
            with transaction.atomic():
                changed = run(True)
            self.stdout.write(f'Backup created: {backup.name}')
        else:
            changed = run(False)
        self.stdout.write('defining samples changed: ' + ', '.join(f'{k} {v}' for k, v in changed.items()))
