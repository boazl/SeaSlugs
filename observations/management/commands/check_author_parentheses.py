"""List the catalogue species whose author's parentheses disagree with their original genus (ICZN: parentheses exactly
when the species now stands in another genus than the one it was described in -- Species.author_parentheses_ok), and
the gallery species whose original genus is not recorded yet. Read-only."""
from django.core.management.base import BaseCommand

from observations.models import Species


class Command(BaseCommand):
    help = 'Check that species authors are in parentheses exactly when the species has left its original genus.'

    def handle(self, *args, **options):
        described = Species.objects.exclude(author='').exclude(species__startswith='sp')
        wrong = [s for s in described.exclude(original_genus='') if s.author_parentheses_ok() is False]
        for s in wrong:
            self.stdout.write(f'{s.scientific_name} | {s.author} | original genus {s.original_genus}')
        missing = described.filter(original_genus='', areas__isnull=False).distinct().order_by('scientific_name')
        self.stdout.write(f'Parentheses that disagree with the original genus: {len(wrong)}.')
        self.stdout.write(f'Gallery species without an original genus: {missing.count()}'
                          + (': ' + ', '.join(s.scientific_name for s in missing) if missing.exists() else '.'))
